import argparse
import os
import re
import shutil
import stat
import subprocess

from concurrent.futures import as_completed, ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional

import botocore.exceptions
import boto3.session
import gitlab
import requests
import sentry_sdk
from boto3.s3.transfer import TransferConfig

from .common import (
    clone_spack,
    get_workdir_context,
    list_prefix_contents,
    BuiltSpec,
)

sentry_sdk.init(traces_sample_rate=1.0)

GITLAB_URL = "https://gitlab.spack.io"
GITLAB_PROJECT = "spack/spack"
PREFIX_REGEX = re.compile(r"/build_cache/(.+)$")
PROTECTED_REF_REGEXES = [
    re.compile(r"^develop$"),
    re.compile(r"^v[\d]+\.[\d]+\.[\d]+$"),
    re.compile(r"^releases/v[\d]+\.[\d]+$"),
    re.compile(r"^develop-[\d]{4}-[\d]{2}-[\d]{2}$"),
]
MB = 1024 ** 2
MULTIPART_THRESHOLD = 100 * MB
MULTIPART_CHUNKSIZE=20 * MB
MAX_CONCURRENCY=10
USE_THREADS=True
SPACK_PUBLIC_KEY_LOCATION = "https://spack.github.io/keys"
SPACK_PUBLIC_KEY_NAME = "spack-public-binary-key.pub"





################################################################################
# Check if the given ref matches one of the expected protected refs above.
def is_ref_protected(ref):
    for regex in PROTECTED_REF_REGEXES:
        m = regex.match(ref)
        if m:
            return True
    return False


################################################################################
# Thread worker function
def publish_missing_spec(built_spec, bucket, ref, force, gpg_home, tmpdir):
    hash = built_spec.hash
    meta_suffix = built_spec.meta
    archive_suffix = built_spec.archive

    specfile_path = os.path.join(tmpdir, f"{hash}.spec.json.sig")

    session = boto3.session.Session()
    s3_resource = session.resource('s3')
    s3_client = s3_resource.meta.client

    if not os.path.isfile(specfile_path) or force is True:
        # First we have to download the file locally
        try:
            with open(specfile_path, "wb") as f:
                s3_client.download_fileobj(bucket, meta_suffix, f)
        except botocore.exceptions.ClientError as error:
            error_msg = getattr(error, "message", error)
            error_msg = f"Failed to download {meta_suffix} due to {error_msg}"
            return False, error_msg

    # Verify the signature of the locally downloaded metadata file
    try:
        env = {"GNUPGHOME": gpg_home}
        subprocess.run(["gpg", "--verify", specfile_path], env=env, check=True)
    except subprocess.CalledProcessError as cpe:
        error_msg = getattr(cpe, "message", cpe)
        print(f"Failed to verify signature of {meta_suffix} due to {error_msg}")
        return False, error_msg

    config = TransferConfig(
        multipart_threshold=MULTIPART_THRESHOLD,
        multipart_chunksize=MULTIPART_CHUNKSIZE,
        max_concurrency=MAX_CONCURRENCY,
        use_threads=USE_THREADS,
    )

    # Finally, copy the files directly from source to dest, starting with the tarball
    for suffix in [archive_suffix, meta_suffix]:
        m = PREFIX_REGEX.search(suffix)
        if m:
            dest_prefix = f"{ref}/build_cache/{m.group(1)}"
            try:
                copy_source = {
                    'Bucket': bucket,
                    'Key': suffix,
                }
                s3_client.copy(copy_source, bucket, dest_prefix, Config=config)
            except botocore.exceptions.ClientError as error:
                error_msg = getattr(error, "message", error)
                error_msg = f"Failed to copy_object({suffix}) due to {error_msg}"
                return False, error_msg

    return True, f"Published {meta_suffix} and {archive_suffix} to s3://{bucket}/{ref}/"


################################################################################
# Main steps of the publish algorithm:
#
#     1) Get a listing of the bucket contents.  This will include entries for
#        metadata and archive files for all specs at the root as well as in all
#        stacks
#     2) Use regular expressions to build dictionaries of all hashes in the
#        stack mirrors, as well as all hashes at the root.  Stored information
#        for each includes url (path) to metadata and archive file.
#     3) Determine which specs are missing from the root (should contain union
#        of all specs in stacks)
#     4) If no specs are missing from the top level, quit
#     5) Download and trust the public part of the reputational signing key
#     6) In parallel, publish any missing specs:
#         6a) Download meta file from stack mirror
#         6b) Verify signature of metadata file
#         6c) If not valid signature, QUIT
#         6d) Try to copy archive file from src to dst, and quit if you can't
#         6e) Try to copy metadata file from src to dst
#     7) Once all threads complete, rebuild the remote mirror index
#
def publish(
    bucket: str,
    ref: str,
    exclude: List[str],
    force: bool = False,
    parallel: int = 8,
    workdir: str = "/work",
):
    list_url = f"s3://{bucket}/{ref}/"
    listing_file = os.path.join(workdir, "full_listing.txt")
    tmp_storage_dir = os.path.join(workdir, "specfiles")

    if not os.path.isdir(tmp_storage_dir):
        os.makedirs(tmp_storage_dir)

    if not os.path.isfile(listing_file) or force:
        list_prefix_contents(list_url, listing_file)

    # Build dictionaries of specs existing at the root and within stacks
    all_stack_specs, top_level_specs = generate_spec_catalogs(
        ref, listing_file, exclude
    )

    # Build dictionary of specs in stacks but missing from the root
    missing_at_top = find_top_level_missing(all_stack_specs, top_level_specs)

    print_summary(missing_at_top)

    if not missing_at_top:
        print(f"No specs missing from s3://{bucket}/{ref}, nothing to do.")
        return

    gnu_pg_home = os.path.join(workdir, ".gnupg")
    local_key_path = download_and_import_key(gnu_pg_home, workdir, force)

    # Build a list of tasks for threads
    task_list = [
        (
            # Duplicates are effectively identical, just take the "first" one
            next(iter(stacks_dict.values())),
            bucket,
            ref,
            force,
            gnu_pg_home,
            tmp_storage_dir,
        )
        for (_, stacks_dict) in missing_at_top.items()
    ]

    # Dispatch work tasks
    with ThreadPoolExecutor(max_workers=parallel) as executor:
        futures = [executor.submit(publish_missing_spec, *task) for task in task_list]
        for future in as_completed(futures):
            try:
                result = future.result()
            except Exception as exc:
                print(f"Exception: {exc}")
            else:
                if not result[0]:
                    print(f"Publishing failed: {result[1]}")
                else:
                    print(result[1])

    mirror_url = f"s3://{bucket}/{ref}"

    if local_key_path:
        publish_key(local_key_path, f"{mirror_url}/build_cache/_pgp/{SPACK_PUBLIC_KEY_NAME}")

    # When all the tasks are finished, rebuild the top-level index
    clone_spack(ref)
    print(f"Publishing complete, rebuilding index at {mirror_url}")
    subprocess.run(
        ["/spack/bin/spack", "buildcache", "update-index", "--keys", mirror_url],
        check=True,
    )


################################################################################
#
def publish_key(local_key_path: str, remote_key_url: str):
    cp_cmd = ["aws", "s3", "cp", local_key_path, remote_key_url]
    subprocess.run(cp_cmd, check=True)


################################################################################
#
def download_and_import_key(gpg_home: str, tmpdir: str, force: bool) -> str | None:
    if os.path.isdir(gpg_home):
        if force is True:
            shutil.rmtree(gpg_home)
        else:
            return None

    mode_owner_rwe = stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR
    os.makedirs(gpg_home, mode=mode_owner_rwe)

    public_key_url = f"{SPACK_PUBLIC_KEY_LOCATION}/{SPACK_PUBLIC_KEY_NAME}"
    public_key_id = "2C8DD3224EF3573A42BD221FA8E0CA3C1C2ADA2F"

    # Fetch the public key and write it to a file to be imported
    tmp_key_path = os.path.join(tmpdir, SPACK_PUBLIC_KEY_NAME)
    response = requests.get(public_key_url)
    with open(tmp_key_path, "w") as f:
        f.write(response.text)

    # Also write an ownertrust file to be imported
    ownertrust_path = os.path.join(tmpdir, "trustfile")
    with open(ownertrust_path, "w") as f:
        f.write(f"{public_key_id}:6:\n")

    env = {"GNUPGHOME": gpg_home}

    # Import the key
    subprocess.run(["gpg", "--no-tty", "--import", tmp_key_path], env=env, check=True)

    # Trust it ultimately
    subprocess.run(
        ["gpg", "--no-tty", "--import-ownertrust", ownertrust_path],
        env=env,
        check=True,
    )

    return tmp_key_path


################################################################################
# Return a dictionary keyed by hashes missing from the top-level mirror, along
# with all the stacks that contain each missing hash:
#
#     missing_at_top = {
#         <hash>: {
#             <stack>: <BuiltSpec>,
#             ...
#         },
#         ...
#     },
#
def find_top_level_missing(
    all_stack_specs: Dict[str, Dict[str, BuiltSpec]],
    top_level_specs: Dict[str, BuiltSpec],
) -> Dict[str, Dict[str, BuiltSpec]]:
    missing_at_top = {}

    for hash, stack_specs in all_stack_specs.items():
        if hash not in top_level_specs:
            for stack, built_spec in stack_specs.items():
                # Only if at least one stack has a "complete" (both
                # meta and archive are present) version of the spec
                # do we really consider it missing from the root.
                if built_spec.meta and built_spec.archive:
                    viables = find_or_add(hash, missing_at_top, dict)
                    viables[stack] = built_spec

    return missing_at_top


################################################################################
#
def print_summary(missing_at_top: Dict[str, Dict[str, BuiltSpec]]):
    total_missing = len(missing_at_top)
    incomplete_pairs = {}

    print(f"There are {total_missing} specs missing from the top-level:")
    for hash, stacks_dict in missing_at_top.items():
        viable_stacks = []
        nonviable_stacks = []
        for stack, built_spec in stacks_dict.items():
            if built_spec.meta and built_spec.archive:
                viable_stacks.append(stack)
            else:
                nonviable_stacks.append(stack)

        if viable_stacks:
            viables = ",".join(viable_stacks)
            print(f"  {hash} is available from {viables}")

        if nonviable_stacks:
            incomplete_pairs[hash] = nonviable_stacks

    if incomplete_pairs:
        print(f"Stacks with incomplete pairs, by hash:")
        for hash, stacks in incomplete_pairs.items():
            borked_stacks = ",".join(stacks)
            print(f"  {hash}: {borked_stacks}")


################################################################################
# If d doesn't have a value associated with key, use the ctor to create a new
# value and store it under key.  Then return the value associated with key.
def find_or_add(key: str, d: dict, ctor: Callable):
    if key not in d:
        d[key] = ctor()
    return d[key]


################################################################################
# Read the listing file, populate and return a tuple of dicts indicating which
# specs exist in stacks, and which exist in the top-level buildcache.
#
#     (
#         # First element of tuple is the stack specs
#         {
#             <hash>: {
#                 <stack>: <BuiltSpec>,
#                 ...
#             },
#             ...
#         },
#         # Followed by specs at the top level
#         {
#             <hash>: <BuiltSpec>,
#             ...
#         }
#     )
#
def generate_spec_catalogs(
    ref: str, listing_path: str, exclude: List[str]
) -> tuple[Dict[str, Dict[str, BuiltSpec]], Dict[str, BuiltSpec]]:
    stack_specs = {}
    top_level_specs = {}

    top_level_meta_regex = re.compile(rf"{ref}/build_cache/.+-([^\.]+).spec.json.sig$")
    top_level_archive_regex = re.compile(rf"{ref}/build_cache/.+-([^\.]+).spack$")
    stack_meta_regex = re.compile(
        rf"{ref}/([^/]+)/build_cache/.+-([^\.]+).spec.json.sig$"
    )
    stack_archive_regex = re.compile(rf"{ref}/([^/]+)/build_cache/.+-([^\.]+).spack$")

    with open(listing_path) as f:
        for line in f:
            m = top_level_meta_regex.search(line)

            if m:
                hash = m.group(1)
                spec = find_or_add(hash, top_level_specs, BuiltSpec)
                spec.hash = hash
                spec.meta = m.group(0)
                continue

            m = top_level_archive_regex.search(line)
            if m:
                hash = m.group(1)
                spec = find_or_add(hash, top_level_specs, BuiltSpec)
                spec.hash = hash
                spec.archive = m.group(0)
                continue

            m = stack_meta_regex.search(line)
            if m:
                stack = m.group(1)
                if stack not in exclude:
                    hash = m.group(2)
                    hash_dict = find_or_add(hash, stack_specs, dict)
                    spec = find_or_add(stack, hash_dict, BuiltSpec)
                    spec.hash = hash
                    spec.stack = stack
                    spec.meta = m.group(0)
                continue

            m = stack_archive_regex.search(line)
            if m:
                stack = m.group(1)
                if stack not in exclude:
                    hash = m.group(2)
                    hash_dict = find_or_add(hash, stack_specs, dict)
                    spec = find_or_add(stack, hash_dict, BuiltSpec)
                    spec.hash = hash
                    spec.stack = stack
                    spec.archive = m.group(0)
                continue

            # else it must be a public key, an index, or a hash of an index

    return stack_specs, top_level_specs





################################################################################
# Filter through pipelines updated over the last_n_days to find all protected
# branches that had a pipeline run.
def get_recently_run_protected_refs(last_n_days):
    gl = gitlab.Gitlab(GITLAB_URL)
    project = gl.projects.get(GITLAB_PROJECT)
    now = datetime.now()
    previous = now - timedelta(days=last_n_days)
    recent_protected_refs = set()
    print(f"Piplines in the last {last_n_days} day(s):")
    for pipeline in project.pipelines.list(
        iterator=True, updated_before=now, updated_after=previous
    ):
        print(f"  {pipeline.id}: {pipeline.ref}")
        if is_ref_protected(pipeline.ref):
            recent_protected_refs.add(pipeline.ref)
    return list(recent_protected_refs)


################################################################################
# Entry point
def main():
    start_time = datetime.now()
    print(f"Publish script started at {start_time}")

    parser = argparse.ArgumentParser(
        prog="publish.py",
        description="Publish specs from stack-specific mirrors to the root",
    )

    parser.add_argument(
        "-b", "--bucket", default="spack-binaries", help="Bucket to operate on"
    )
    parser.add_argument(
        "-r",
        "--ref",
        default="develop",
        help=(
            "A single protected ref to publish, or else 'recent', to "
            "publish any protected refs that had a pipeline recently"
        ),
    )
    parser.add_argument(
        "-d",
        "--days",
        type=int,
        default=1,
        help=(
            "Number of days to look backward for recent protected "
            "pipelines (only used if `--ref recent` is provided)"
        ),
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
    parser.add_argument(
        "-w",
        "--workdir",
        default=None,
        help="A scratch directory, defaults to a tmp dir",
    )
    parser.add_argument(
        "-x",
        "--exclude",
        nargs="+",
        default=[],
        help="Optional list of stacks to exclude",
    )

    args = parser.parse_args()

    if args.ref == "recent":
        refs = get_recently_run_protected_refs(args.days)
    else:
        refs = [args.ref]

    exceptions = []

    for ref in refs:
        # If the cli didn't provide a working directory, we will create (and clean up)
        # a temporary directory using this workdir context
        with get_workdir_context(args.workdir) as workdir:
            print(f"Publishing missing specs for {args.bucket} / {ref}")
            try:
                publish(
                    args.bucket, ref, args.exclude, args.force, args.parallel, workdir
                )
            except Exception as e:
                # Swallow exceptions here so we can proceed with remaining refs,
                # but save the exceptions to raise at the end.
                print(f"Error publishing specs for {args.bucket} / {ref} due to {e}")
                exceptions.append(e)

    end_time = datetime.now()
    elapsed = end_time - start_time
    print(f"Publish script finished at {end_time}, elapsed time: {elapsed}")

    if exceptions:
        # Re-raise the first exception encountered, so we can see it in Sentry.
        raise exceptions[0]


################################################################################
#
if __name__ == "__main__":
    main()
