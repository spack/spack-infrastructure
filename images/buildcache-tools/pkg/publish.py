import argparse
import logging
import os
import re
import shutil
import stat
import subprocess
import tempfile

from collections import defaultdict
from concurrent.futures import as_completed, ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from typing import Callable, Dict, List, Optional

import botocore.exceptions

import github

from boto3.s3.transfer import TransferConfig

from pkg.common import (
    clone_spack,
    download_and_import_key,
    extract_json_from_clearsig,
    get_workdir_context,
    list_prefix_contents,
    s3_copy_file,
    s3_create_client,
    s3_download_file,
    generate_spec_catalogs_v2,
    generate_spec_catalogs_v3,
    BuiltSpec,
    MalformedManifestError,
    NoSuchMediaTypeError,
    UnexpectedURLFormatError,
    SNAPSHOT_TAG_REGEXES,
    PROTECTED_BRANCH_REGEXES,
)

GITHUB_PROJECT = "spack/spack-packages"
PREFIX_REGEX_V2 = re.compile(r"/(build_cache/.+)$")
PROTECTED_REF_REGEXES = SNAPSHOT_TAG_REGEXES + PROTECTED_BRANCH_REGEXES

LOGGER = logging.getLogger(__name__)

################################################################################
#
def is_ref_protected(ref):
    """Check if given ref matches expected protected ref pattern

    Returns: True if ref matches a protected ref pattern, False otherwise
    """
    for regex in PROTECTED_REF_REGEXES:
        m = regex.match(ref)
        if m:
            return True
    return False


################################################################################
#
def publish_spec_v2(built_spec, bucket, prefix_from, prefix_to, force, gpg_home, tmpdir):
    """Publish a single spec from a stack to the root"""
    hash = built_spec.hash
    meta_suffix = built_spec.meta
    archive_suffix = built_spec.archive

    specfile_path = os.path.join(tmpdir, f"{hash}.spec.json.sig")

    try:
        s3_download_file(bucket, meta_suffix, specfile_path, force=force)
    except Exception as error:
        error_msg = getattr(error, "message", error)
        error_msg = f"Failed to download {meta_suffix} due to {error_msg}"
        return False, error_msg

    # Verify the signature of the locally downloaded metadata file
    if gpg_home:
        try:
            env = {"GNUPGHOME": gpg_home}
            subprocess.run(["gpg", "--verify", specfile_path], env=env, check=True)
        except subprocess.CalledProcessError as cpe:
            error_msg = getattr(cpe, "message", cpe)
            LOGGER.error(f"Failed to verify signature of {meta_suffix} due to {error_msg}")
            return False, error_msg

    # Finally, copy the files directly from source to dest, starting with the tarball
    for suffix in [archive_suffix, meta_suffix]:
        m = PREFIX_REGEX_V2.search(suffix)
        if m:
            dest_prefix = f"{prefix_to}/{m.group(1)}"
            try:
                copy_source = {
                    "Bucket": bucket,
                    "Key": suffix,
                }
                s3_copy_file(copy_source, bucket, dest_prefix)
            except Exception as error:
                error_msg = getattr(error, "message", error)
                error_msg = f"Failed to copy_object({suffix}) due to {error_msg}"
                return False, error_msg

    return True, f"Published {meta_suffix} and {archive_suffix} to s3://{bucket}/{ref}/"


################################################################################
#
def publish_spec_v3(built_spec, bucket, prefix_from, prefix_to, force, gpg_home, tmpdir):
    """Publish a single spec from a stack to the root"""
    spec_hash = built_spec.hash
    stack_manifest_prefix = built_spec.manifest_prefix
    stack_meta_prefix = built_spec.meta
    stack_archive_prefix = built_spec.archive

    # In v3 land, we already had to download this file in order to access
    # the content-address of the tarball and metadata.
    manifest_path = built_spec.manifest_path

    # Verify the signature of the previously downloaded manifest file
    if gpg_home:
        try:
            env = {"GNUPGHOME": gpg_home}
            subprocess.run(
                ["gpg", "--verify", manifest_path],
                env=env,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except subprocess.CalledProcessError as cpe:
            error_msg = getattr(cpe, "message", cpe)
            LOGGER.error(f"Failed to verify signature of {stack_meta_prefix} due to {error_msg}")
            return False, error_msg

    from_regex = re.compile(rf"^{prefix_from}/(.+)$")

    m = from_regex.match(stack_manifest_prefix)
    if not m:
        raise UnexpectedURLFormatError(stack_manifest_prefix)
    top_level_manifest_prefix = f"{prefix_to}/{m.group(1)}"

    m = from_regex.match(stack_meta_prefix)
    if not m:
        raise UnexpectedURLFormatError(stack_meta_prefix)
    top_level_meta_prefix = f"{prefix_to}/{m.group(1)}"

    m = from_regex.match(stack_archive_prefix)
    if not m:
        raise UnexpectedURLFormatError(stack_archive_prefix)
    top_level_archive_prefix = f"{prefix_to}/{m.group(1)}"

    things_to_copy = [
        (stack_archive_prefix, top_level_archive_prefix),
        (stack_meta_prefix, top_level_meta_prefix),
        (stack_manifest_prefix, top_level_manifest_prefix),
    ]

    s3_client = s3_create_client()

    # Finally, copy the files directly from source to dest, starting with the tarball
    errs = []
    for src_prefix, dest_prefix in things_to_copy:
        try:
            copy_source = {"Bucket": bucket, "Key": src_prefix}
            s3_copy_file(copy_source, bucket, dest_prefix, client=s3_client)
        except Exception as error:
            error_msg = getattr(error, "message", error)
            error_msg = f"Failed to copy_object({src_prefix}) due to {error_msg}"
            errs.append(error_msg)

    if errs:
        msg = f"Failed to publish /{built_spec.hash}"
        for err in errs:
            msg = msg + f"\n\t{err}"
        return False, msg

    return (
        True,
        f"Published {stack_manifest_prefix}, {stack_meta_prefix}, and {stack_archive_prefix} to s3://{bucket}/{prefix_to}/",
    )


################################################################################
#
def publish(
    bucket: str,
    ref: str,
    exclude: List[str] = [],
    verify: bool = True,
    force: bool = False,
    parallel: int = 8,
    workdir: str = "/work",
    layout_version: int = 3,
):
    """Publish all specs present in stacks but missing at the root

    Main steps of the publish algorithm:
        1) Get a listing of the bucket contents.  This will include entries for
           metadata and archive files for all specs at the root as well as in all
           stacks
        2) Use regular expressions to build dictionaries of all hashes in the
           stack mirrors, as well as all hashes at the root.  Stored information
           for each includes url (path) to metadata and archive file.
        3) Determine which specs are missing from the root (should contain union
           of all specs in stacks)
        4) If no specs are missing from the top level, quit
        5) Download and trust the public part of the reputational signing key
        6) In parallel, publish any missing specs:
            6a) Download meta file from stack mirror
            6b) Verify signature of metadata file
            6c) If not valid signature, QUIT
            6d) Try to copy archive file from src to dst, and quit if you can't
            6e) Try to copy metadata file from src to dst
        7) Once all threads complete, rebuild the remote mirror index
    """
    tmp_storage_dir = os.path.join(workdir, "specfiles")

    if not os.path.isdir(tmp_storage_dir):
        os.makedirs(tmp_storage_dir)

    # Build dictionaries of specs existing at the root and within stacks

    if layout_version == 2:
        all_stack_specs, top_level_specs = generate_spec_catalogs_v2(
            bucket, ref, exclude=exclude
        )
        publish_fn = publish_spec_v2
    elif layout_version == 3:
        all_stack_specs, top_level_specs = generate_spec_catalogs_v3(
            bucket, ref, exclude=exclude, parallel=parallel
        )
        publish_fn = publish_spec_v3
    else:
        LOGGER.error(f"Unrecognized layout version: {layout_version}")
        return

    # Build dictionary of specs in stacks but missing from the root
    missing_at_top = find_top_level_missing(all_stack_specs, top_level_specs)

    print_summary(missing_at_top)

    if not missing_at_top:
        LOGGER.info(f"No specs missing from s3://{bucket}/{ref}, nothing to do.")
        return

    gnu_pg_home = os.path.join(workdir, ".gnupg")
    download_and_import_key(gnu_pg_home, workdir, force)
    publish_keys(f"s3://{bucket}/{ref}", gnu_pg_home)

    # Build a list of tasks for threads
    task_list = [
        (
            # Duplicates are effectively identical, just take the "first" one
            next(iter(stacks_dict.values())),
            bucket,
            f"{ref}/{next(iter(stacks_dict.values())).stack}",
            ref,
            force,
            gnu_pg_home if verify else "",
            tmp_storage_dir,
        )
        for (_, stacks_dict) in missing_at_top.items()
    ]

    # Dispatch work tasks
    with ThreadPoolExecutor(max_workers=parallel) as executor:
        futures = [executor.submit(publish_fn, *task) for task in task_list]
        for future in as_completed(futures):
            try:
                result = future.result()
            except Exception as exc:
                LOGGER.error(f"Exception: {exc}")
            else:
                if not result[0]:
                    LOGGER.error(f"Publishing failed: {result[1]}")
                else:
                    LOGGER.info(result[1])

    # When all the tasks are finished, rebuild the top-level index
    LOGGER.info("Publishing complete")


def publish_keys(mirror_url, gnu_pg_home, ref: str = "develop"):
    # Clone spack version appropriate to what we're publishing
    with tempfile.TemporaryDirectory() as workdir:
        spack_root = os.environ.get("SPACK_ROOT")
        if not spack_root:
            clone_spack(packages_ref="develop", clone_dir=workdir)
            spack_root = f"{workdir}/spack"

        spack_exe = f"{spack_root}/bin/spack"

        gnu_pg_home = os.path.abspath(gnu_pg_home)
        # Can be useful for testing to clone a custom spack to somewhere other than "/"
        # clone_spack(
        #     packages_ref=ref,
        #     spack_ref="content-addressable-tarballs-2",
        #     spack_repo="https://github.com/scottwittenburg/spack.git",
        #     clone_dir=workdir,
        # )
        # spack_exe = f"{workdir}/spack/bin/spack"

        # Publish the key used for verification
        LOGGER.info(f"Publishing trusted keys to {mirror_url} ({gnu_pg_home})")
        my_env = os.environ.copy()
        my_env["SPACK_GNUPGHOME"] = gnu_pg_home
        subprocess.run(
            [spack_exe, "gpg", "publish", "--mirror-url", mirror_url],
            env=my_env,
            check=True,
        )

        # Rebuild the package and key index
        LOGGER.info(f"Rebuilding index at {mirror_url}")
        subprocess.run(
            [spack_exe, "buildcache", "update-index", "--keys", mirror_url],
            stdout=subprocess.DEVNULL,
            check=True,
        )


################################################################################
#
################################################################################
#
def find_top_level_missing(
    all_stack_specs: Dict[str, Dict[str, BuiltSpec]],
    top_level_specs: Dict[str, BuiltSpec],
) -> Dict[str, Dict[str, BuiltSpec]]:
    """Return a dictionary of all specs missing at the top level

    Return a dictionary keyed by hashes missing from the top-level mirror, along
    with all the stacks that contain each missing hash.  Only complete entries
    (i.e. those with both metadata and compressed archive) within the stacks
    are considered missing at the top level.

        missing_at_top = {
            <hash>: {
                <stack>: <BuiltSpec>,
                ...
            },
            ...
        }
    """
    missing_at_top: Dict[str, Dict[str, BuiltSpec]] = defaultdict(
        lambda: defaultdict(BuiltSpec)
    )

    for stack, stack_specs in all_stack_specs.items():
        for hash, built_spec in stack_specs.items():
            if hash not in top_level_specs:
                # Only if at least one stack has a "complete" (both
                # meta and archive are present) version of the spec
                # do we really consider it missing from the root.
                if built_spec.meta and built_spec.archive:
                    missing_at_top[hash][stack] = built_spec

    return missing_at_top


################################################################################
#
def print_summary(missing_at_top: Dict[str, Dict[str, BuiltSpec]]):
    total_missing = len(missing_at_top)
    incomplete_pairs = {}

    LOGGER.info(f"There are {total_missing} specs missing from the top-level:")
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
            LOGGER.info(f"  {hash} is available from {viables}")

        if nonviable_stacks:
            incomplete_pairs[hash] = nonviable_stacks

    if incomplete_pairs:
        LOGGER.info(f"Stacks with incomplete pairs, by hash:")
        for hash, stacks in incomplete_pairs.items():
            borked_stacks = ",".join(stacks)
            LOGGER.info(f"  {hash}: {borked_stacks}")


################################################################################
#
def get_recently_run_protected_refs(last_n_days):
    """Query Github for recently updated refs

    Filter through pipelines updated over the last_n_days to find all protected
    branches that had a pipeline run.
    """
    gh = github.Github()
    repo = gh.get_repo(GITHUB_PROJECT)

    recent_protected_refs = set()
    now = datetime.now(timezone.utc)
    previous = now - timedelta(days=last_n_days)
    for branch in repo.get_branches():
        if not branch.protected:
            continue
        if branch.commit.commit.author.date < previous:
            continue
        recent_protected_refs.add(branch.name)

    for tag in repo.get_tags():
        if tag.last_modified_datetime < previous:
            continue
        recent_protected_refs.add(tag.name)

    return list(recent_protected_refs)


################################################################################
#
def main():
    start_time = datetime.now()
    LOGGER.info(f"Publish script started at {start_time}")

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
        action="append",
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
        "-v",
        "--version",
        type=int,
        default=3,
        help=("Target layout version to publish (either 2 or 3, defaults to 2)"),
    )
    parser.add_argument(
        "-x",
        "--exclude",
        nargs="+",
        default=[],
        help="Optional list of stacks to exclude",
    )

    args = parser.parse_args()

    refs = []
    if not args.ref:
        refs = ["develop"]

    if "recent" in args.ref:
        refs = get_recently_run_protected_refs(args.days)
        args.ref.remove("recent")

    if args.ref:
        refs.extend(list(args.ref))

    exceptions = []

    for ref in refs:
        # If the cli didn't provide a working directory, we will create (and clean up)
        # a temporary directory using this workdir context
        with get_workdir_context(args.workdir) as workdir:
            LOGGER.info(f"Publishing missing specs for {args.bucket} / {ref}")
            try:
                publish(
                    args.bucket,
                    ref,
                    args.exclude,
                    args.force,
                    args.parallel,
                    workdir,
                    args.version,
                )
            except Exception as e:
                # Swallow exceptions here so we can proceed with remaining refs,
                # but save the exceptions to raise at the end.
                LOGGER.error(f"Error publishing specs for {args.bucket} / {ref} due to {e}")
                exceptions.append(e)

    end_time = datetime.now()
    elapsed = end_time - start_time
    LOGGER.info(f"Publish script finished at {end_time}, elapsed time: {elapsed}")

    if exceptions:
        # Re-raise the first exception encountered, so we can see it in Sentry.
        raise exceptions[0]


################################################################################
#
if __name__ == "__main__":
    main()
