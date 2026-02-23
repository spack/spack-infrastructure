import argparse
import gzip
import io
import json
import os
import re
import subprocess
import sys
from concurrent.futures import as_completed, ThreadPoolExecutor
from contextlib import closing
from datetime import datetime
from typing import NamedTuple

from pkg.common import (
    BuiltSpec,
    TIMESTAMP_AND_SIZE,
    TIMESTAMP_PATTERN,
    compute_checksum,
    bucket_name_from_s3_url,
    clone_spack,
    get_workdir_context,
    list_prefix_contents,
    s3_copy_file,
    s3_download_file,
    s3_upload_file,
    spec_catalogs_from_listing_v2,
)


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

    if not built_spec.hash:
        return MigrationResult(False, "Could not parse hash from listing")

    # Check the listing to see if we already migrated this spec, in which case,
    # we're done.
    if not force:
        already_migrated_pattern = (
            rf"/v3/manifests/spec/.+{built_spec.hash}.spec.manifest.json$"
        )
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

    archive_size = None

    # We need to read the size of the compressed archive from the listing file
    result = subprocess.run(
        ["grep", "-E", built_spec.archive, listing_path], capture_output=True
    )
    if result.returncode == 0:
        matching_line = result.stdout.decode("utf-8")
        regex = re.compile(rf"({TIMESTAMP_AND_SIZE})")
        m = regex.search(matching_line)
        if m:
            parts = re.split(r"\s+", m.group(1))
            archive_size = int(parts[2])

    if not archive_size:
        error_msg = f"Unable to parse archive size for {built_spec.hash} from listing"
        return MigrationResult(False, error_msg)

    # Read the verified spec file
    with open(verified_specfile_path) as fd:
        spec_dict = json.load(fd)

    # Retrieve the algorithm and checksum from the json data, so we can
    # assemble the expected prefix of the tarball under the new layout
    bcs = spec_dict.pop("binary_cache_checksum", None)
    if not bcs:
        error_msg = f"Metadata for {built_spec.hash} missing 'binary_cache_checksum'"
        return MigrationResult(False, error_msg)

    hash_alg = bcs["hash_algorithm"]
    checksum = bcs["hash"]
    new_layout_tarball_prefix = (
        f"{target_prefix}/blobs/{hash_alg}/{checksum[:2]}/{checksum}"
    )

    # This shouldn't be changing, but make sure it's there
    spec_dict["buildcache_layout_version"] = 2

    # Compress the spec dict and write it to disk
    with open(verified_specfile_path, "wb") as writable:
        with closing(
            gzip.GzipFile(
                filename="", mode="wb", compresslevel=6, mtime=0, fileobj=writable
            )
        ) as f_bin:
            with io.TextIOWrapper(f_bin, encoding="utf-8") as f_txt:
                json.dump(spec_dict, f_txt, indent=0, separators=(",", ":"))

    specfile_checksum = compute_checksum(verified_specfile_path)
    specfile_size = os.stat(verified_specfile_path).st_size
    specfile_checksum_alg = "sha256"

    # Build the manifest
    manifest_dict = {
        "version": 3,
        "data": [
            {
                "contentLength": archive_size,
                "mediaType": "application/vnd.spack.install.v2.tar+gzip",
                "compression": "gzip",
                "checksumAlgorithm": hash_alg,
                "checksum": checksum,
            },
            {
                "contentLength": specfile_size,
                "mediaType": "application/vnd.spack.spec.v5+json",
                "compression": "gzip",
                "checksumAlgorithm": specfile_checksum_alg,
                "checksum": specfile_checksum,
            }
        ]
    }

    manifest_path_unsigned = os.path.join(working_dir, f"{built_spec.hash}_unsigned.spec.manifest.json")
    manifest_path_signed = os.path.join(working_dir, f"{built_spec.hash}.spec.manifest.json")

    # Create and write a manifest
    with open(manifest_path_unsigned, "w", encoding="utf-8") as fd:
        json.dump(manifest_dict, fd, indent=0, separators=(",", ":"))

    # Sign the manifest
    sign_cmd = [
        "gpg",
        "--no-tty",
        "--output",
        f"{manifest_path_signed}",
        "--clearsign",
        manifest_path_unsigned,
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

    # Upload the compressed spec dict as blog
    new_layout_meta_prefix = (
        f"{target_prefix}/blobs/{specfile_checksum_alg}/{specfile_checksum[:2]}/{specfile_checksum}"
    )

    print(f"Uploading {verified_specfile_path} to s3://{bucket}/{new_layout_meta_prefix}")

    try:
        s3_upload_file(verified_specfile_path, bucket, new_layout_meta_prefix)
    except Exception as e:
        error_msg = getattr(e, "message", e)
        error_msg = (
            f"Migration failed: unable to upload compressed metadata for "
            f"{built_spec.hash} due to {error_msg}"
        )
        return MigrationResult(False, error_msg)

    # Upload the manifest
    new_layout_manifest_prefix = (
        f"{target_prefix}/v3/manifests/spec/{spec_name}/{spec_name}-{spec_version}-{spec_hash}.spec.manifest.json"
    )

    print(f"Uploading {manifest_path_signed} to s3://{bucket}/{new_layout_manifest_prefix}")

    try:
        s3_upload_file(manifest_path_signed, bucket, new_layout_manifest_prefix)
    except Exception as e:
        error_msg = getattr(e, "message", e)
        error_msg = (
            f"Migration failed: unable to upload re-signed manifest for "
            f"{built_spec.hash} due to {error_msg}"
        )
        return MigrationResult(False, error_msg)

    return MigrationResult(True, f"{built_spec.hash} successfully migrated")


################################################################################
#
def migrate_keys(bucket: str, target_prefix: str, listing_file: str, tmpdir: str):
    """Migrate the _pgp directory to the new layout"""
    print("Migrating public keys")
    original_key_prefixes = []

    key_id_regex = re.compile(r"_pgp/([^/]+)\.pub$")
    public_key_pattern = r"\.pub$"
    grep_cmd = ["grep", "-E", public_key_pattern, listing_file]
    proc = subprocess.Popen(grep_cmd, stdout=subprocess.PIPE)

    for matching_line in io.TextIOWrapper(proc.stdout, encoding="utf-8"):
        regex = re.compile(rf"^{TIMESTAMP_AND_SIZE}([^\s]+)$")
        line = matching_line.strip()
        m = regex.match(line)

        if not m:
            print(f"Unable to migrate key due to parse failure: {line}")
            continue

        original_key_prefixes.append(m.group(1))

    for original_key_prefix in original_key_prefixes:
        local_key_path = os.path.join(tmpdir, os.path.basename(original_key_prefix))

        # Download the key file
        try:
            s3_download_file(bucket, original_key_prefix, local_key_path)
        except Exception as e:
            error_msg = getattr(e, "message", e)
            error_msg = f"Failed to download {bucket}/{original_key_prefix} due to {error_msg}"
            print(error_msg)
            continue

        # Compute the checksum and size on disk
        key_checksum = compute_checksum(local_key_path)
        key_checksum_algo = "sha256"
        key_size = os.stat(local_key_path).st_size
        key_blob_prefix = f"{target_prefix}/blobs/{key_checksum_algo}/{key_checksum[:2]}/{key_checksum}"

        m = key_id_regex.search(original_key_prefix)
        if not m:
            print(f"Could not parse key id from {original_key_prefix}")
            continue

        key_id = m.group(1)
        key_manifest_prefix = f"{target_prefix}/v3/manifests/key/{key_id}.key.manifest.json"

        # Create and write a manifest
        key_manifest_dict = {
            "version": 3,
            "data" : [
                {
                    "contentLength": key_size,
                    "mediaType": "application/pgp-keys",
                    "compression": "none",
                    "checksumAlgorithm": key_checksum_algo,
                    "checksum": key_checksum,
                },
            ],
        }

        local_manifest_path = os.path.join(tmpdir, f"{key_id}.key.manifest.json")
        with open(local_manifest_path, "w", encoding="utf-8") as fd:
            json.dump(key_manifest_dict, fd, indent=0, separators=(",", ":"))

        # Push the key blob
        print(f"Uploading {local_key_path} to s3://{bucket}/{key_blob_prefix}")

        try:
            s3_upload_file(local_key_path, bucket, key_blob_prefix)
        except Exception as e:
            print(f"Failed to upload {local_key_path} to s3://{bucket}/{key_blob_prefix}")
            continue

        # Push the key blob manifest
        print(f"Uploading {local_manifest_path} to s3://{bucket}/{key_manifest_prefix}")

        try:
            s3_upload_file(local_manifest_path, bucket, key_manifest_prefix)
        except Exception as e:
            print(f"Failed to upload {local_manifest_path} to s3://{bucket}/{key_manifest_prefix}")
            continue


################################################################################
#
def update_mirror_index(mirror_url: str, clone_spack_dir: str):
    """Clone spack and update the index for the new layout"""
    print(f"Rebuilding index at {mirror_url}")

    clone_spack(clone_dir=clone_spack_dir)

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
        migrate_keys(bucket, target_prefix, listing_file, tmp_storage_dir)

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
