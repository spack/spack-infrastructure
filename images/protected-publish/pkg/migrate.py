import argparse
import json
import os
import re
import subprocess
import sys
from concurrent.futures import as_completed, ThreadPoolExecutor
from datetime import datetime

import sentry_sdk

from .common import (
    BuiltSpec,
    TaskResult,
    bucket_name_from_s3_url,
    clone_spack,
    get_workdir_context,
    list_prefix_contents,
    s3_copy_file,
    s3_download_file,
    s3_upload_file,
    spec_catalogs_from_listing_v2,
)

sentry_sdk.init(traces_sample_rate=1.0)

CONTENT_ADDRESSABLE_TARBALLS_REPO = "https://github.com/scottwittenburg/spack.git"
CONTENT_ADDRESSABLE_TARBALLS_REF = "content-addressable-tarballs-2"


################################################################################
# For each thread...
#
def _migrate_spec(
    built_spec: BuiltSpec,
    listing_path: str,
    bucket: str,
    target_prefix: str,
    working_dir: str,
    force: bool,
) -> TaskResult:
    if not built_spec.meta:
        return TaskResult(False, f"Found no metadata url for {built_spec.hash}")

    if not built_spec.archive:
        return TaskResult(False, f"Found no archive url for {built_spec.hash}")

    if not built_spec.meta.endswith(".sig"):
        return TaskResult(False, "We will only migrate signed signed binaries")

    signed_specfile_path = os.path.join(working_dir, f"{built_spec.hash}.spec.json.sig")
    verified_specfile_path = os.path.join(working_dir, f"{built_spec.hash}.spec.json")

    # Download the spec metadata file
    try:
        s3_download_file(bucket, built_spec.meta, signed_specfile_path, force)
    except Exception as e:
        error_msg = getattr(e, "message", e)
        error_msg = f"Failed to download {built_spec.hash} metadata due to {error_msg}"
        return TaskResult(False, error_msg)

    # Verify the signature of the locally downloaded metadata file
    try:
        subprocess.run(["gpg", "--quiet", signed_specfile_path], check=True)
    except subprocess.CalledProcessError as cpe:
        error_msg = getattr(cpe, "message", str(cpe))
        print(f"Failed to verify signature of {built_spec.meta} due to {error_msg}")
        return TaskResult(False, error_msg)

    # Extract the spec dictionary from within the signature
    with open(verified_specfile_path) as fd:
        # spec_dict = extract_json_from_signature(fd.read())
        spec_dict = json.load(fd)

    # Retrieve the algorithm and checksum from the json data
    hash_alg = spec_dict["binary_cache_checksum"]["hash_algorithm"]
    checksum = spec_dict["binary_cache_checksum"]["hash"]

    # Assemble the expected prefix of the tarball under the new layout
    new_layout_tarball_prefix = f"{target_prefix}/blobs/{hash_alg}/{checksum[:2]}/{checksum}"

    # Check the listing to see if we already migrated this one, in which case,
    # we're done and we consider this spec migration successful
    grep_cmd = ["grep", new_layout_tarball_prefix, listing_path]
    grep_result = subprocess.run(grep_cmd)
    if grep_result.returncode == 0:
        mirror_url = f"s3://{bucket}/{target_prefix}"
        print(f"{mirror_url} / {built_spec.hash} is already migrated, exiting.")
        return TaskResult(True, f"{mirror_url} / {hash} previously migrated")

    # If tarball was not already migrated, neither was the metadata, so update
    # it and write it to disk
    spec_dict["buildcache_layout_version"] = 3
    with open(verified_specfile_path, 'w') as fd:
        json.dump(spec_dict, fd)

    # Re-sign the updated spec dict, and first remove the previous signed file to
    # avoid gpg asking us if we're sure we want to overwrite it.
    os.remove(signed_specfile_path)
    sign_cmd = ["gpg", "--no-tty", "--output", f"{signed_specfile_path}", "--clearsign", verified_specfile_path]

    try:
        subprocess.run(sign_cmd, check=True)
    except subprocess.CalledProcessError as cpe:
        error_msg = getattr(cpe, "message", str(cpe))
        print(f"Failed to resign {verified_specfile_path} due to {error_msg}")
        return TaskResult(False, error_msg)

    # copy the archive from the original prefix into the prefix under the new layout
    copy_source = {
        'Bucket': bucket,
        'Key': built_spec.archive,
    }

    print(f"Copying s3://{bucket}/{built_spec.archive} to s3://{bucket}/{new_layout_tarball_prefix}")

    try:
        s3_copy_file(copy_source, bucket, new_layout_tarball_prefix)
    except Exception as error:
        error_msg = getattr(error, "message", error)
        error_msg = f"Failed to migrate {built_spec.archive} due to {error_msg}"
        return TaskResult(False, error_msg)

    # upload the locally updated and re-signed meta to the correct prefix under the new layout
    spec_name = spec_dict["spec"]["nodes"][0]["name"]
    spec_version = spec_dict["spec"]["nodes"][0]["version"]
    spec_hash = spec_dict["spec"]["nodes"][0]["hash"]

    # This mismatch isn't likely, but check just in case
    if spec_hash != built_spec.hash:
        return TaskResult(False, f"Old layout filname/hash mismatch ({built_spec.hash}/{spec_hash})")

    new_layout_meta_prefix = f"{target_prefix}/v3/specs/{spec_name}-{spec_version}-{spec_hash}.spec.json.sig"

    print(f"Uploading {signed_specfile_path} to s3://{bucket}/{new_layout_meta_prefix}")

    try:
        s3_upload_file(signed_specfile_path, bucket, new_layout_meta_prefix)
    except Exception as e:
        error_msg = getattr(e, "message", e)
        error_msg = (
            f"Migrattion failed: unable to upload re-signed metadata for "
            f"{built_spec.hash} due to {error_msg}"
        )
        return TaskResult(False, error_msg)

    return TaskResult(True, f"{built_spec.hash} successfully migrated")


################################################################################
# Migrate method
#
# Expects public and secret parts of whatever key was used to sign the existing
# binaries in the mirror to be already imported and ready to use for verifying
# and subsequent re-signing.
def migrate(mirror_url: str, workdir: str, force: bool = False, parallel: int = 8):
    listing_file = os.path.join(workdir, "full_listing.txt")
    tmp_storage_dir = os.path.join(workdir, "specfiles")

    if not os.path.isdir(tmp_storage_dir):
        os.makedirs(tmp_storage_dir)

    if not os.path.isfile(listing_file) or force:
        list_prefix_contents(f"{mirror_url}/", listing_file)

    all_catalogs = spec_catalogs_from_listing_v2(listing_file)
    target_prefix = None

    print(f"Looking for {mirror_url} in the catalogs...")
    for prefix in all_catalogs:
        if mirror_url.endswith(prefix):
            target_prefix = prefix
            break
    else:
        print(f"Unable to find an old-layout binary mirror at {mirror_url}")
        return

    target_catalog = all_catalogs[target_prefix]
    total_count = len(target_catalog)
    print(f"Found mirror: {target_prefix} has {total_count} specs to migrate")

    for spec_hash, built_spec in target_catalog.items():
        print(f"  {spec_hash}:")
        print(f"    meta: {built_spec.meta}")
        print(f"    archive: {built_spec.archive}")

    bucket = bucket_name_from_s3_url(mirror_url)

    # Build a list of tasks for threads
    task_list = [
        (
            built_spec,
            listing_file,
            bucket,
            target_prefix,
            tmp_storage_dir,
            force,
        )
        for (_, built_spec) in target_catalog.items()
    ]

    total_tasks = len(task_list)
    completed_successfully = 0

    # Dispatch work tasks
    with ThreadPoolExecutor(max_workers=parallel) as executor:
        futures = [executor.submit(_migrate_spec, *task) for task in task_list]
        for future in as_completed(futures):
            try:
                result = future.result()
            except Exception as exc:
                print(f"Exception: {exc}")
            else:
                if result and result.success:
                    completed_successfully += 1
                else:
                    print(f"Migration of {built_spec.hash} failed: {result.message}")

    print(f"All migration threads finished, {completed_successfully}/{total_tasks} completed successfully")

    # Migrate any signing keys
    old_keys_prefix = f"{mirror_url}/build_cache/_pgp"
    new_keys_prefix = f"{mirror_url}/v3/keys/_pgp"
    key_sync_cmd = ["aws", "s3", "sync", old_keys_prefix, new_keys_prefix]

    try:
        subprocess.run(key_sync_cmd, check=True)
    except Exception as e:
        print(f"Failed to migrate gpg verification keys due to {e}")

    if completed_successfully > 0:
        # When all the tasks are finished, rebuild the top-level index
        clone_spack(ref=CONTENT_ADDRESSABLE_TARBALLS_REF, repo=CONTENT_ADDRESSABLE_TARBALLS_REPO, clone_dir=workdir)
        print(f"Publishing complete, rebuilding index at {mirror_url}")
        subprocess.run(
            [f"{workdir}/spack/bin/spack", "-d", "buildcache", "update-index", "--keys", mirror_url],
            check=True,
        )


################################################################################
# Entry point
def main():
    start_time = datetime.now()
    print(f"Migrate script started at {start_time}")

    parser = argparse.ArgumentParser(
        prog="publish.py",
        description="Publish specs from stack-specific mirrors to the root",
    )

    parser.add_argument(
        "mirror", type=str, default=None, help="URL of mirror to migrate."
    )

    parser.add_argument(
        "-w",
        "--workdir",
        default=None,
        help="A scratch directory, defaults to a tmp dir",
    )

    parser.add_argument(
        "-f",
        "--force",
        default=False,
        action="store_true",
        help="Refetch files if they already exist",
    )

    parser.add_argument(
        "-p", "--parallel", default=8, type=int, help="Thread parallelism level"
    )

    args = parser.parse_args()
    if not args.mirror:
        print("Missing required mirror argument")
        sys.exit(1)

    # If the cli didn't provide a working directory, we will create (and clean up)
    # a temporary directory using this workdir context
    with get_workdir_context(args.workdir) as workdir:
        migrate(args.mirror, workdir=workdir, force=args.force, parallel=args.parallel)

    end_time = datetime.now()
    elapsed = end_time - start_time
    print(f"Migrate script finished at {end_time}, elapsed time: {elapsed}")


################################################################################
#
if __name__ == "__main__":
    main()
