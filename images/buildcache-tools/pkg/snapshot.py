#!/usr/bin/env python3

import argparse
import github
import json
import os
import re
import subprocess
import tempfile
import urllib.request
import logging

from datetime import datetime, timezone
from concurrent.futures import as_completed, ThreadPoolExecutor
from github import Github, InputGitAuthor
from gitlab import Gitlab

from pkg.common import (
    download_and_import_key,
    generate_spec_catalogs_v3,
    s3_create_client,
    s3_object_exists,
    tag_source_branch,
    SNAPSHOT_TAG_REGEXES,
    PROTECTED_BRANCH_REGEXES,
)

from .publish import (
    publish_spec_v3,
    publish,
    publish_keys,
)


DRYRUN = False
WORKDIR = os.environ.get("SNAPSHOT_WORKDIR")

GL = Gitlab("https://gitlab.spack.io")
DEFAULT_GITLAB_PROJECT = os.environ.get("SNAPSHOT_GITLAB_REPO", "spack/spack-packages")

GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
GH = Github(auth=github.Auth.Token(GITHUB_TOKEN))
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


def create_develop_snapshot_tag(project):
    global DRYRUN
    gl_project = GL.projects.get(DEFAULT_GITLAB_PROJECT, lazy=True)

    # Get the sha to snapshot
    sha = gl_last_successful_pipeline(gl_project, "develop")
    if not sha:
        LOGGER.warning("No successful develop pipelines found!")

    # Check to see if this ref has already been used as a snapshot
    commit = gl_project.commits.get(sha)
    tags = commit.refs("tag")
    snapshot_tag = None
    for t in tags:
        print(t)
        if re.match(t.get("name", ""), "develop-.*"):
            snapshot_tag = t
            break

    if snapshot_tag:
        LOGGER.warning(f"Skipping SHA ({sha}) already associated with snapshot tag {snapshot_tag}")
        return

    # Now that we found a new commit, tag it for snapshot
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    tag_name = f"develop-{date_str}"
    tag_msg = f"Snapshot release {date_str}"

    # Use the GitHub API to create a tag for this commit of develop.
    py_gh_repo = GH.get_repo(project, lazy=True)
    spackbot_author = InputGitAuthor("spackbot", "noreply@spack.io")
    LOGGER.info(f"Pushing tag {tag_name} for commit {sha} ({project})")

    if not DRYRUN:
        try:
            tag = py_gh_repo.create_git_tag(
                tag=tag_name,
                message=tag_msg,
                object=sha,
                type="commit",
                tagger=spackbot_author)

            py_gh_repo.create_git_ref(
                ref=f"refs/tags/{tag_name}",
                sha=tag.sha)

            LOGGER.info("Push done!")
        except github.GithubException as e:
            LOGGER.info(str(e))
    else:
        LOGGER.info("DRYRUN: No tags pushed!")


def create_snapshot(bucket: str, tag: github.GitTag, workdir: str, parallel: int = 8):
    """Create a snapshot mirror associated with a tag and branch"""
    global DRYRUN

    branch = tag_source_branch(t.name)
    if not branch:
        LOGGER.warning(f"Skipping snapshot for {tag.name}, cannot determine base branch")
        return False

    if s3_object_exists(bucket, "{tag.name}/v3/layout.json"):
        LOGGER.info(f"Skipping snapshot for {tag.name} as it already exists")
        return True

    gl_project = DEFAULT_GITLAB_PROJECT
    if isinstance(gl_project, str):
        gl_project = GL.projects.get(gl_project, lazy=True)

    pipeline = gl_project.pipelines.list(get_all=False, per_page=1, sha=tag.commit.sha, ref=branch, status="success")
    if not pipeline:
        LOGGER.warning(f"Skipping {tag.name}: Could not find corresponding successful pipeline for {branch}")
        return False

    LOGGER.info(f"Creating snapshot for: {t.name} from {branch} using pipeline {pipeline[0].id}")

    # Assuming all snapshots are v3 only now
    include_stacks = ["windows-vis"]
    all_specs_catalog, _ = generate_spec_catalogs_v3(bucket, branch, workdir=workdir, include=include_stacks)

    gnu_pg_home = os.path.join(workdir, ".gnupg")
    if not DRYRUN:
        download_and_import_key(gnu_pg_home, workdir, False)

    # Get the lockfile artifacts for the generate jobs
    for j in pipeline[0].jobs.list(iterator=True, scope="success"):
        if not j.stage == 'generate':
            continue

        stack = j.name.replace("-generate", "")

        if include_stacks and stack not in include_stacks:
            continue

        if s3_object_exists(bucket, "{tag.name}/{stack}/v3/layout.json"):
            LOGGER.info(f"Skipping snapshot for {tag.name}/{stack} as it already exists")
            continue

        # Get the lockfile/concrete hashes to sync to snapshot mirror
        job = gl_project.jobs.get(j.id, lazy=True)
        artifact_path = f"jobs_scratch_dir/{stack}/concrete_environment/spack.lock"
        LOGGER.info(f"Fetching artifacts for job {j.id}: {artifact_path}")
        artifact = job.artifact(artifact_path)
        lockfile = json.loads(artifact)

        snapshot_hashes = list(iter(lockfile["concrete_specs"].keys()))

        task_list = [
            (
                built_spec,
                bucket,
                f"{branch}/{stack}",
                f"{tag.name}/{stack}",
                False,
                None, #gnu_pg_home,
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
    prefix: {spec.prefix}
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

        mirror_url = f"s3://{bucket}/{tag.name}/{stack}"
        if DRYRUN:
            LOGGER.info("DRYRUN: Skipping key publish")
        else:
            publish_keys(mirror_url, gnu_pg_home)

    return True


if __name__ == "__main__":

    parser = argparse.ArgumentParser()

    parser.add_argument("-n", "--dryrun",
        action="store_true",
        help="Bucket to create snapshot mirrors in",
    )
    parser.add_argument("-b", "--bucket",
        default="spack-binaries",
        help="Bucket to create snapshot mirrors in",
    )
    parser.add_argument("-t" ,"--tag",
        action="append",
        help="Tags to snapshot",
    )
    parser.add_argument("-p", "--project",
        default=DEFAULT_GITHUB_PROJECT,
        help="Github project to get/push snapshot tags",
    )

    logging.basicConfig(level=logging.INFO)
    logging.getLogger("botocore").setLevel(logging.ERROR)

    args = parser.parse_args()

    if args.dryrun:
        DRYRUN=True

    # Create a new develop snapshot if one is created
    if not args.tag:
        create_develop_snapshot_tag(args.project)

    # Iterate all of the project tags and attempt to create a
    # snaptshot if it is needed
    py_gh_repo = GH.get_repo(args.project)
    tempdir = WORKDIR or tempfile.mkdtemp()
    for t in py_gh_repo.get_tags():
        if args.tag and t.name not in args.tag:
            LOGGER.debug("Skipping tag {t.name}")
            continue

        try:
            if create_snapshot(args.bucket, t, tempdir):
                # Now use publish to create the top level mirror if the snapshot exists
                # Don't re-verify everything, it was already done by create_snapshot
                publish(args.bucket, t.name, verify=False, workdir=tempdir)
        except Exception as e:
            raise Exception from e
            LOGGER.error(f"Failed to create snapshot for {t.name}: {e}")
