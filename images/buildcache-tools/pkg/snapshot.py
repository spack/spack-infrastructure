#!/usr/bin/env python3

import argparse
import contextlib
import json
import logging
import os
import re
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Dict, List

import github
from github import Github, InputGitAuthor
from gitlab import Gitlab

from pkg.common import (
    clone_spack,
    download_and_import_key,
    generate_spec_catalogs_v3,
    get_workdir_context,
    s3_object_exists,
    tag_source_branch,
)
from pkg.publish import publish, publish_keys, publish_spec_v3

DRYRUN = False
WORKDIR = os.environ.get("SNAPSHOT_WORKDIR")

GL = Gitlab("https://gitlab.spack.io")
DEFAULT_GITLAB_PROJECT = os.environ.get("SNAPSHOT_GITLAB_REPO", "spack/spack-packages")

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
DEFAULT_GITHUB_PROJECT = os.environ.get("SNAPSHOT_GITHUB_REPO", "spack/spack-packages")

LOGGER = logging.getLogger("snapshot.__main__" if __name__ == "__main__" else "snapshot")


def gl_last_successful_pipeline(project, branch):
    """Return the commit sha associated with the last successful pipeline for
    a given branch in a project.

        project: project slug (ie. spack/spack)
        branch: name of the branch (ie. develop)
    """
    if isinstance(project, str):
        project = GL.projects.get(project, lazy=True)

    pipeline = project.pipelines.list(get_all=False, per_page=1, ref=branch, status="success")

    if pipeline:
        return pipeline[0].sha

    return None


def create_or_update_ref(repo, ref: str, sha: str):
    """Create or update the sha for a ref

    Return:
        True: The ref was created or updated
        False: The ref was already up to date

    Raises:
        GithubException for all get ref errors that are not 404 Not Found
    """
    try:
        latest_ref = repo.get_git_ref(ref)
        if latest_ref.object.sha == sha:
            print(f"Ref {ref} is already pointing at {sha}")
            return False
    except GithubException as e:
        if e.status != 404:
            raise
        # 404 means the ref doesn't exist and needs to be created.
        latest_ref = None

    # Update or create the ref
    if latest_ref is not None:
        LOGGER.info(f"Updating ref {ref}")
        latest_ref.edit(sha, force=True)
    else:
        LOGGER.info(f"Creaing ref {ref}")
        repo.create_git_ref(
            ref=f"refs/{ref}",
            sha=sha)

    return True


def create_develop_snapshot_ref(py_gh_repo: github.Repository):
    global DRYRUN
    gl_project = GL.projects.get(DEFAULT_GITLAB_PROJECT, lazy=True)

    # Get the sha to snapshot
    sha = gl_last_successful_pipeline(gl_project, "develop")
    if not sha:
        LOGGER.warning("No successful develop pipelines found!")

    LOGGER.debug(f"Found successful pipeline at gitlab sha: {sha}")

    # Now that we found a new commit, tag it for snapshot
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ref_name = f"snapshots/develop-{date_str}"

    # Check to see if this ref has already been used as a snapshot
    commit = gl_project.commits.get(sha)
    snapshots = py_gh_repo.get_git_matching_refs("snapshots")
    current_snapshot_ref = None
    for ref in snapshots:
        LOGGER.debug(f"Found snapshot: {ref.ref}")
        if ref.object.sha == sha:
            current_snapshot_ref = ref
            break

    if current_snapshot_ref:
        LOGGER.warning(f"Skipping SHA ({sha}): equivalent snapshot {current_snapshot_ref.ref} already exists")
        return

    # Use the GitHub API to create a tag for this commit of develop.
    LOGGER.info(f"Pushing tag {ref_name} for commit {sha} ({py_gh_repo.full_name})")
    if not DRYRUN:
        try:
            # If the latest develop snapshot is updated, also push a new date snapshot
            if create_or_update_ref(py_gh_repo, "snapshots/develop-latest", sha):
                create_or_update_ref(py_gh_repo, ref_name, sha)

            LOGGER.info("Push done!")
        except github.GithubException as e:
            LOGGER.info(str(e))
    else:
        LOGGER.info("DRYRUN: No snapshots pushed!")


def load_stacks(
    branch: str,
    ref: github.GitRef,
    workdir: str,
    include_stacks: List[str],
    exclude_stacks: List[str],
) -> Dict[str, str]:
    """Create a snapshot mirror associated with a ref and branch.

    Args:
        branch: Branch CI was run.
        ref: Git ref in remote with CI pipeline run on branch.
        workdir: working dir to write stack environments to.
        include_stacks: Stacks to include when loading from CI. Empty list means all.
        exclude_stacks: Stacks to exclude when loading from CI. Empty list means none.

    Returns:
        Mapping from stack name to local stack concrete environment.
    """
    gl_project = DEFAULT_GITLAB_PROJECT
    if isinstance(gl_project, str):
        gl_project = GL.projects.get(gl_project, lazy=True)

    pipeline = gl_project.pipelines.list(
        get_all=False, per_page=1, sha=ref.object.sha, ref=branch, status="success"
    )
    if not pipeline:
        LOGGER.warning(
            f"Skipping {ref.ref}: Could not find corresponding successful pipeline for {branch}"
        )
        return {}

    LOGGER.info(f"Creating snapshot for: {ref.ref} from {branch} using pipeline {pipeline[0].id}")

    stacks = {}
    # Get the lockfile artifacts for the generate jobs
    for j in pipeline[0].jobs.list(iterator=True, scope="success"):
        if not j.stage == "generate":
            continue

        stack = j.name.replace("-generate", "")

        if include_stacks and stack not in include_stacks:
            continue

        if exclude_stacks and stack in exclude_stacks:
            continue

        # Write a local env with the job lock file
        stack_root = os.path.join(workdir, ref.object.sha, stack)
        os.makedirs(stack_root, exist_ok=True)

        lock_path = os.path.join(stack_root, "spack.lock")
        if not os.path.exists(lock_path):
            # Get the lockfile/concrete hashes to sync to snapshot mirror
            job = gl_project.jobs.get(j.id, lazy=True)
            artifact_path = f"jobs_scratch_dir/{stack}/concrete_environment/spack.lock"
            LOGGER.info(f"Fetching artifacts for job {j.id}: {artifact_path}")
            artifact = job.artifact(artifact_path)

            with open(lock_path, "wb") as fd:
                fd.write(artifact)

            env_file = os.path.join(stack_root, "spack.yaml")
            with open(env_file, "w", encoding="utf-8") as fd:
                fd.write("spack: {}")

        stacks[stack] = os.path.realpath(stack_root)

    return stacks


def create_snapshot_view(
    bucket: str, stacks: Dict[str, str], branch: str, ref_name: str, workdir: str
):
    spack_exe = clone_spack(
        # Can be useful for testing to clone a custom spack to somewhere other than "/"
        # spack_ref="content-addressable-tarballs-2",
        # spack_repo="https://github.com/scottwittenburg/spack.git",
        packages_ref="develop",
        clone_dir=workdir,
    )

    snapshot_mirror = "snapshot_mirror"
    snapshots = {
        ref_name: list(stacks.values())
    }

    if False:
        for stack, stack_env in stacks.items():
            stack_snapshot = "/".join(ref_name, stack) if ref_name != branch_name else stack
            snapshots[stack_snapshot]: [stack_env]

    for name in snapshots:
        snapshot_safename = name.replace("/", "-")

        spack_create_mirror = [
            spack_exe,
            "mirror",
            "add",
            "--name",
            name,
            "--signed",
            "--type",
            "binary",
            snapshot_safename,
            f"s3://{bucket}/{branch}/"
        ]

        # Update the view
        spack_view_command = [
            spack_exe,
            "buildcache",
            "update-index",
            "--force",  # Override whatever was in the snapshot view before
            snapshot_safename,
        ] + snapshots[name]

        if DRYRUN:
            print(spack_create_mirror)
            print(spack_view_command)
        else:
            try:
                subprocess.run(spack_create_mirror, check=True)
                subprocess.run(spack_view_command, check=True)
            finally:
                # Cleanup the mirror
                subprocess.run(
                    [
                        spack_exe,
                        "mirror",
                        "remove",
                        snapshot_safename,
                    ],
                    check=True
                )

def snapshot_view_index_already_exists(bucket: str, branch: str, ref: str) -> bool:
    # The latest snapshot never exists (for this check)
    # ie. it is always regenerated
    if "snapshots/develop-latest" == ref:
        return False
    return s3_object_exists(bucket, f"{branch}/v3/manifests/index/{ref}/index.manifest.json")


def create_snapshot(
    bucket: str,
    stacks: Dict[str, str],
    branch: str,
    ref_name: str,
    workdir: str,
    gnu_pg_home: str,
    parallel: int = 8,
):
    """Create a snapshot mirror associated with a tag and branch"""
    global DRYRUN

    if s3_object_exists(bucket, "{ref_name}/v3/layout.json"):
        LOGGER.info(f"Skipping snapshot for {ref_name} as it already exists")
        return True

    # Assuming all snapshots are v3 only now
    all_specs_catalog, _ = generate_spec_catalogs_v3(bucket, branch, workdir=workdir)

    # Get the lockfile artifacts for the generate jobs
    for stack in stacks:
        if s3_object_exists(bucket, "{ref_name}/{stack}/v3/layout.json"):
            LOGGER.info(f"Skipping snapshot for {ref_name}/{stack} as it already exists")
            continue

        with open(stacks[stack], "r") as fd:
            lockfile = json.load(fd)

        snapshot_hashes = list(iter(lockfile["concrete_specs"].keys()))

        task_list = [
            (
                built_spec,
                bucket,
                f"{branch}/{stack}",
                f"{ref_name}/{stack}",
                False,
                None,  # gnu_pg_home,
                workdir,
            )
            for hash, built_spec in all_specs_catalog[stack].items()
            if hash in snapshot_hashes
        ]

        publish_fn = publish_spec_v3
        if DRYRUN:

            def dryrun_publish(spec, bucket, source, dest, force, gpg_home, workdir):
                LOGGER.debug(f"""
DRYRUN: publish
    prefix: {spec.manifest_prefix}
    bucket: {bucket}
    source: {source}
    dest: {dest}
""")
                return True, None

            publish_fn = dryrun_publish

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
                        if result[1]:
                            LOGGER.debug(result[1])

        mirror_url = f"s3://{bucket}/{ref_name}/{stack}"
        if DRYRUN:
            LOGGER.info("DRYRUN: Skipping key publish")
        else:
            publish_keys(mirror_url, gnu_pg_home, workdir=workdir)

    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument("-d", "--debug", action="store_true", help="Show debug info")
    parser.add_argument("-n", "--dryrun", action="store_true", help="Dryrun mode")
    parser.add_argument(
        "-b", "--bucket", default="spack-binaries", help="Bucket to create snapshot mirrors in"
    )
    parser.add_argument("--ref", action="append", help="Tags to snapshot")
    parser.add_argument(
        "--create-snapshot-ref",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Do not create new snapshot ref."
    )
    parser.add_argument(
        "--copy",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Snapshot stacks and tag as a view",
    )
    parser.add_argument(
        "--view",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Snapshot stacks and tag as a view"
    )
    parser.add_argument(
        "-p",
        "--project",
        default=DEFAULT_GITHUB_PROJECT,
        help="Github project to get/push snapshot tags",
    )
    parser.add_argument("-I", "--include-stack", action="append", help="Stacks to include")
    parser.add_argument("-E", "--exclude-stack", action="append", help="Stacks to exclude")
    parser.add_argument("--workdir", action="store")

    logging.basicConfig(level=logging.INFO)
    logging.getLogger("boto3").setLevel(logging.ERROR)
    logging.getLogger("botocore").setLevel(logging.ERROR)
    logging.getLogger("urllib3").setLevel(logging.ERROR)

    args = parser.parse_args()

    if args.debug or args.dryrun:
        logging.basicConfig(level=logging.DEBUG)
        LOGGER.setLevel(logging.DEBUG)

    if args.dryrun:
        DRYRUN = True
        LOGGER.info(f"==== DRYRUN ====")

    LOGGER.info(f"Github Project: {args.project}")
    LOGGER.info(f"Gitlab Project: {DEFAULT_GITLAB_PROJECT}")
    LOGGER.info(f"Copy: {args.copy}")
    LOGGER.info(f"View: {args.view}")
    LOGGER.info(f"Create Ref: {args.create_snapshot_ref}")

    LOGGER.info("Including stacks: " + ("\n\t- " if args.include_stack else "ALL"))
    LOGGER.info("\n\t- ".join(args.include_stack or []))
    LOGGER.info("Excluding stacks: " + ("\n\t- " if args.exclude_stack else "NONE"))
    LOGGER.info("\n\t- ".join(args.exclude_stack or []))

    # Create a new develop snapshot if one is created
    gh_host = Github(auth=github.Auth.Token(GITHUB_TOKEN))
    py_gh_repo = gh_host.get_repo(args.project)
    if args.create_snapshot_ref:
        create_develop_snapshot_ref(py_gh_repo)

    # Iterate all of the project tags and attempt to create a
    # snaptshot if it is needed
    if workdir := args.workdir or WORKDIR:
        if not os.path.exists(workdir):
            os.makedirs(workdir)


    if not args.ref:
        args.ref = ["snapshots", "tags"]

    snapshot_refs = [ref for match_ref in args.ref for ref in py_gh_repo.get_git_matching_refs(match_ref)]
    if not snapshot_refs:
        snapshot_refs = [py_gh_repo.get_get_ref(ref)]

    LOGGER.info("Creating snapshots for refs: \n\t-" + "\n\t- ".join(ref.ref for ref in snapshot_refs))

    with get_workdir_context(workdir) as tempdir:
        gnu_pg_home = os.path.join(tempdir, ".gnupg")
        if not DRYRUN:
            download_and_import_key(gnu_pg_home, tempdir, False)
        else:
            LOGGER.info("DRYRUN: download_and_import_key...")

        LOGGER.info(f"workdir: {tempdir}")
        toplevel_branch = set()
        for ref in snapshot_refs:
            # /refs/snapshots/develop-12-01-01
            # /refs/tags/v2026.06.0
            # /refs/heads/develop
            _, ref_type, ref_name = ref.ref.split("/", 2)

            try:
                # Get the source branch for this tag
                if ref_type == "tags":
                    branch = tag_source_branch(ref_name)
                else:  # If it isn't a tag it is a develop snapshot
                    branch = "develop"

                toplevel_branch.add(branch)

                if not branch:
                    LOGGER.warning(
                        f"Skipping snapshot for {ref_type}/{ref_name}, cannot determine base branch"
                    )
                    continue

                if ref_type == "snapshots":
                    ref_name = f"{ref_type}/{ref_name}"

                if args.view and snapshot_view_index_already_exists(args.bucket, branch, ref_name):
                    LOGGER.debug(f"Skipping snapshot for {ref_name} as it already exists.")
                    continue

                # Get the stacks from the pipeline
                stacks = load_stacks(branch, ref, tempdir, args.include_stack, args.exclude_stack)

                # Download the reputational signing key
                if args.view:
                    # publish(args.bucket, branch, verify=False, workdir=tempdir)
                    create_snapshot_view(args.bucket, stacks, branch, ref_name, tempdir)

                if args.copy:
                    if create_snapshot(args.bucket, stacks, branch, ref_name, tempdir, gnu_pg_home):
                        # Now use publish to create the top level mirror if the snapshot exists
                        # Don't re-verify everything, it was already done by create_snapshot
                        publish(args.bucket, ref_name, verify=False, workdir=tempdir)
            except Exception as e:
                LOGGER.error(f"Failed to create snapshot for {ref_name}: {e}")
                continue

        # Only do this once at the end per toplevel branch mirror
        for branch in toplevel_branch:
            publish_keys(f"s3://{args.bucket}/{branch}", gnu_pg_home, workdir=tempdir, dryrun=args.dryrun)
