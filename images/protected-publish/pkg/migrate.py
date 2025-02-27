import argparse
import json
import os
import re
import subprocess
import sys
from concurrent.futures import as_completed, ThreadPoolExecutor
from datetime import datetime
from typing import NamedTuple

import sentry_sdk

from .common import (
    BuiltSpec,
    TIMESTAMP_AND_SIZE,
    TIMESTAMP_PATTERN,
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


class MigrationResult(NamedTuple):
    #: False unless a spec was actually migrated
    migrated: bool
    #: Any message about the cause of error or success conditions
    message: str


################################################################################
#
def _migrate_spec(
    built_spec: BuiltSpec,
    listing_path: str,
    bucket: str,
    target_prefix: str,
    working_dir: str,
    force: bool,
) -> MigrationResult:
    """Migrate a single spec from the old layout to the new one

    First checks if the spec has already been migrated by looking in the file
    listing for the presence of the spec metadata file.  If the spec hash is
    already present under the new layout, do nothing further, but return an
    object indicating no migration was performed.  If the spec has not yet
    been migrated, fetch the spec metadat, verify the signature, use the info
    in the spec dict to compute the name and location of the metadata and the
    compresed archive under the new layout, update the metadata so it reflects
    the new layout version number, resign the updated metadata, copy the
    compressed archive directly from it's old layout location to the new one,
    and lastly, push the updated and re-signed metadata to its location under
    the new layout.

    Args:
        built_spec: Object containing spec info under old layout
        listing_path: Path to listing file from "aws s3 ls --recursive ..."
        bucket: The S3 bucket name
        target_prefix: The bits between bucket name and "build_cache"
        working_dir: Location to download files, clone spack, etc.
        force: Re-migrate the spec, even if it has already been done

    Returns: A MigrationResult indicating whether spec was migrated and why.
    """
    if not built_spec.meta:
        return MigrationResult(False, f"Found no metadata url for {built_spec.hash}")

    if not built_spec.archive:
        return MigrationResult(False, f"Found no archive url for {built_spec.hash}")

    if not built_spec.meta.endswith(".sig"):
        return MigrationResult(False, "We will only migrate signed signed binaries")

    if not built_spec.hash:
        return MigrationResult(False, "Could not parse hash from listing")

    # Check the listing to see if we already migrated this spec, in which case,
    # we're done.
    if not force:
        already_migrated_pattern = rf"/v3/specs/.+{built_spec.hash}.spec.json.sig$"
        grep_cmd = ["grep", "-E", already_migrated_pattern, listing_path]
        grep_result = subprocess.run(grep_cmd)
        if grep_result.returncode == 0:
            mirror_url = f"s3://{bucket}/{target_prefix}"
            return MigrationResult(
                False, f"{built_spec.hash} previously migrated in {mirror_url}"
            )

    signed_specfile_path = os.path.join(working_dir, f"{built_spec.hash}.spec.json.sig")
    verified_specfile_path = os.path.join(working_dir, f"{built_spec.hash}.spec.json")

    # Download the spec metadata file
    try:
        s3_download_file(bucket, built_spec.meta, signed_specfile_path, force)
    except Exception as e:
        error_msg = getattr(e, "message", e)
        error_msg = f"Failed to download {built_spec.hash} metadata due to {error_msg}"
        return MigrationResult(False, error_msg)

    if os.path.exists(verified_specfile_path) and force:
        os.remove(verified_specfile_path)

    if not os.path.exists(verified_specfile_path):
        # Verify the signature of the locally downloaded metadata file, it seems
        # when you let gpg deduce what to do from the arguments, it not only
        # verifies, but also strips the signature material and writes the file
        # back to disk with the .sig extension removed.
        try:
            subprocess.run(["gpg", "--quiet", signed_specfile_path], check=True)
        except subprocess.CalledProcessError as cpe:
            error_msg = getattr(cpe, "message", str(cpe))
            print(f"Failed to verify signature of {built_spec.meta} due to {error_msg}")
            return MigrationResult(False, error_msg)
    else:
        print(f"Verification of {built_spec.hash} skipped as it was already done.")

    # Read the verified spec file
    with open(verified_specfile_path) as fd:
        spec_dict = json.load(fd)

    # Retrieve the algorithm and checksum from the json data, so we can
    # assemble the expected prefix of the tarball under the new layout
    hash_alg = spec_dict["binary_cache_checksum"]["hash_algorithm"]
    checksum = spec_dict["binary_cache_checksum"]["hash"]
    new_layout_tarball_prefix = (
        f"{target_prefix}/blobs/{hash_alg}/{checksum[:2]}/{checksum}"
    )

    # Update the buildcache_layout_version and add the new attributes
    spec_dict["buildcache_layout_version"] = 3
    spec_dict["archive_compression"] = "gzip"
    spec_dict["archive_size"] = 0
    spec_dict["archive_timestamp"] = datetime.now().astimezone().isoformat()

    # To populate the new layout fields recording the size and timestamp
    # of the buildcache entry, we can read them out of the listing file
    result = subprocess.run(
        ["grep", "-E", built_spec.archive, listing_path], capture_output=True
    )
    if result.returncode == 0:
        matching_line = result.stdout.decode("utf-8")
        regex = re.compile(rf"({TIMESTAMP_AND_SIZE})")
        m = regex.search(matching_line)
        if m:
            parts = re.split(r"\s+", m.group(1))
            timestamp = datetime.strptime(f"{parts[0]} {parts[1]}", TIMESTAMP_PATTERN)
            spec_dict["archive_size"] = int(parts[2])
            spec_dict["archive_timestamp"] = timestamp.astimezone().isoformat()

    # Write the updated spec dict back to disk, the extra args to json.dump()
    # are to prevent a single long line, which gpg will silently truncate.
    with open(verified_specfile_path, "w", encoding="utf-8") as fd:
        json.dump(spec_dict, fd, indent=0, separators=(",", ":"))

    # Re-sign the updated spec dict, and first remove the previous signed file to
    # avoid gpg asking us if we're sure we want to overwrite it.
    os.remove(signed_specfile_path)
    sign_cmd = [
        "gpg",
        "--no-tty",
        "--output",
        f"{signed_specfile_path}",
        "--clearsign",
        verified_specfile_path,
    ]

    try:
        subprocess.run(sign_cmd, check=True)
    except subprocess.CalledProcessError as cpe:
        error_msg = getattr(cpe, "message", str(cpe))
        print(f"Failed to resign {verified_specfile_path} due to {error_msg}")
        return MigrationResult(False, error_msg)

    # Copy the archive from the original prefix into the prefix under the new layout
    copy_source = {
        "Bucket": bucket,
        "Key": built_spec.archive,
    }

    print(
        f"Copying s3://{bucket}/{built_spec.archive} to s3://{bucket}/{new_layout_tarball_prefix}"
    )

    try:
        s3_copy_file(copy_source, bucket, new_layout_tarball_prefix)
    except Exception as error:
        error_msg = getattr(error, "message", error)
        error_msg = f"Failed to migrate {built_spec.archive} due to {error_msg}"
        return MigrationResult(False, error_msg)

    # Upload the locally updated and re-signed meta to the correct prefix under the new layout
    root_node = spec_dict["spec"]["nodes"][0]
    spec_name = root_node["name"]
    spec_version = root_node["version"]
    spec_hash = root_node["hash"]

    # This mismatch isn't likely, but check just in case
    if spec_hash != built_spec.hash:
        return MigrationResult(
            False, f"Old layout filname/hash mismatch ({built_spec.hash}/{spec_hash})"
        )

    new_layout_meta_prefix = (
        f"{target_prefix}/v3/specs/{spec_name}-{spec_version}-{spec_hash}.spec.json.sig"
    )

    print(f"Uploading {signed_specfile_path} to s3://{bucket}/{new_layout_meta_prefix}")

    try:
        s3_upload_file(signed_specfile_path, bucket, new_layout_meta_prefix)
    except Exception as e:
        error_msg = getattr(e, "message", e)
        error_msg = (
            f"Migration failed: unable to upload re-signed metadata for "
            f"{built_spec.hash} due to {error_msg}"
        )
        return MigrationResult(False, error_msg)

    return MigrationResult(True, f"{built_spec.hash} successfully migrated")


################################################################################
#
def migrate_keys(mirror_url: str):
    """Migrate the _pgp directory to the new layout"""
    print("Migrating signing keys")
    old_keys_prefix = f"{mirror_url}/build_cache/_pgp"
    new_keys_prefix = f"{mirror_url}/v3/keys/_pgp"
    key_sync_cmd = ["aws", "s3", "sync", old_keys_prefix, new_keys_prefix]

    try:
        subprocess.run(key_sync_cmd, check=True)
    except Exception as e:
        print(f"Failed to migrate gpg verification keys due to {e}")


################################################################################
#
def update_mirror_index(mirror_url: str, clone_spack_dir: str):
    """Clone spack and update the index for the new layout"""
    print(f"Rebuilding index at {mirror_url}")

    clone_spack(
        ref=CONTENT_ADDRESSABLE_TARBALLS_REF,
        repo=CONTENT_ADDRESSABLE_TARBALLS_REPO,
        clone_dir=clone_spack_dir,
    )

    try:
        subprocess.run(
            [
                f"{clone_spack_dir}/spack/bin/spack",
                "-d",
                "buildcache",
                "update-index",
                "--keys",
                mirror_url,
            ],
            check=True,
        )
    except Exception as e:
        print(f"Updating index failed due to {e}")


################################################################################
#
def migrate(mirror_url: str, workdir: str, force: bool = False, parallel: int = 8):
    """Migrate all specs in the given mirror

    When ``force`` is False, avoids do any work for specs that appear in the
    new layout format already.  Otherwise, migrates all specs in the mirror
    to the new layout.

    Arguments:
        mirror_url: URL of mirror containing specs to migrate
        workdir: Path where working files can be stored (for possible re-use)
        force: Determines whether to migrate already-migrate specs
        parallel: The number of concurrent threads to use in processing
    """
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

    migrated_specs = 0

    # Dispatch work tasks
    with ThreadPoolExecutor(max_workers=parallel) as executor:
        futures = [executor.submit(_migrate_spec, *task) for task in task_list]
        for future in as_completed(futures):
            try:
                result = future.result()
            except Exception as exc:
                print(f"Exception: {exc}")
            else:
                if result and result.migrated:
                    migrated_specs += 1
                else:
                    print(f"Spec was not migrated due to: {result.message}")

    print("All migration threads finished")

    if migrated_specs > 0:
        # Migrate any signing keys
        migrate_keys(mirror_url=mirror_url)

        # Rebuild the top-level index
        update_mirror_index(mirror_url=mirror_url, clone_spack_dir=workdir)


################################################################################
# Entry point
def main():
    start_time = datetime.now()
    print(f"Migrate script started at {start_time}")

    parser = argparse.ArgumentParser(
        prog="migrate.py",
        description="Migrate specs in a mirror to content addressable layout",
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
