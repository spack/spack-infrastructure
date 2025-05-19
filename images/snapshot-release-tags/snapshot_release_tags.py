#!/usr/bin/env python3

from datetime import datetime, timezone
from github import Github, InputGitAuthor
from typing import Optional
import contextlib as ctx
import json
import os
import re
import sys
import sentry_sdk
import shutil
import subprocess
import tempfile
import time
import urllib.request

sentry_sdk.init(
    # This cron job only runs once weekly,
    # so just record all transactions.
    traces_sample_rate=1.0,
)


GITHUB_REPO = os.environ.get("GITHUB_REPO", "spack/spack-packages")
spackbot_author = InputGitAuthor("spackbot", "noreply@spack.io")


def _durable_subprocess_run(*args, **kwargs):
    """
    Calls subprocess.run with retries/exponential backoff on failure.
    """
    max_attempts = 5
    for attempt_num in range(max_attempts):
        try:
            return subprocess.run(*args, **kwargs, check=True)
        except subprocess.CalledProcessError as e:
            if attempt_num == max_attempts - 1:
                raise e
            print(
                f"Subprocess failed ({e}), retrying ({attempt_num+1}/{max_attempts})",
                file=sys.stderr,
            )
            time.sleep(2 ** (1 + attempt_num))


if __name__ == "__main__":
    if "GITHUB_TOKEN" not in os.environ:
        raise Exception("GITHUB_TOKEN environment is not set")

    # Use the GitLab API to get the most recent successful develop pipeline.
    gitlab_api_url = "https://gitlab.spack.io/api/v4/projects/2"
    pipeline_api_url = f"{gitlab_api_url}/pipelines?ref=develop&status=success"
    request = urllib.request.Request(pipeline_api_url)
    response = urllib.request.urlopen(request)
    response_data = response.read()
    try:
        pipelines = json.loads(response_data)
    except json.decoder.JSONDecodeError:
        raise Exception("Failed to parse response as json ({0})".format(response_data))

    if len(pipelines) == 0:
        raise Exception("No successful develop pipelines found!")

    sha = pipelines[0]["sha"]

    _durable_subprocess_run

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    tag_name = f"develop-{date_str}"
    tag_msg = f"Snapshot release {date_str}"

    # Use the GitHub API to create a tag for this commit of develop.
    github_token = os.environ.get('GITHUB_TOKEN')
    py_github = Github(github_token)
    py_gh_repo = py_github.get_repo("spack/spack", lazy=True)
    print(f"Pushing tag {tag_name} for commit {sha}")

    tag = py_gh_repo.create_git_tag(
        tag=tag_name,
        message=tag_msg,
        object=sha,
        type="commit",
        tagger=spackbot_author)

    py_gh_repo.create_git_ref(
        ref=f"refs/tags/{tag_name}",
        sha=tag.sha)

    #####################################
    # Setup the package repo to update the sha
    spackages = "spack-packages"
    os.makedirs(spackages)

    branch_id = f"snapshot-update/{tag.name}"
    with ctx.chdir(spackages):
        _durable_subprocess_run(["git", "init"])
        _durable_subprocess_run(["git", "config", "user.email", "noreply@spack.io"])
        _durable_subprocess_run(["git", "config", "user.name", "spackbot"])
        _durable_subprocess_run(["git", "config", "advice.detachedHead", "false"])
        _durable_subprocess_run(["git", "remote", "add", "github", f"git@github.com:{GITHUB_REPO}"])
        _durable_subprocess_run(["git", "fetch", "--depth", "1", "develop"])
        _durable_subprocess_run(["git", "checkout", "-b", branch_id])

    gitlab_ci_yml = os.path.join(spackages, ".ci", "gitlab", ".gitlab-ci.yml")
    shasum_re = re.compile(r"SPACK_CHECKOUT_VERSION:( )*\"([a-z0-9]{40})\"")
    try:
        # Update the commit if possible
        with tempfile.TemporaryFile() as tmp:
            shutil.copy(gitlab_ci_yml, tmp)
            with open(tmp, "r") as ifd, open(gitlab_ci_yml, "w") as ofd:
                for line in ifd:
                    old_sha_match = re.search(shasum_re, line)
                    if old_sha_match:
                        old_sha = old_sha_match[2]
                        # The if shas match, don't update
                        if old_sha == tag.sha:
                            raise RuntimeError("sha has not changed")
                        old_date = py_gh_repo.get_commit(old_sha).commit.committer.date
                        new_date = py_gh_repo.get_commit(tag.sha).commit.committer.date
                        # The if new sha is older than the old sha, don't update
                        if old_date > new_date:
                            raise RuntimeError("snapshot sha is older than current sha")
                        line = re.sub(shasum_re, line, tag.sha)
                    ofd.write(line)

            with ctx.chdir(spackages):
                commit_msg = f"""Snapshot Sync: {tag.name} {tag.sha}"""
                _durable_subprocess_run(["git", "commit", "-a", "-m", commit_msg])
                _durable_subprocess_run(["git", "push", "-u", "github", ])

            spackages_repo = py_github.get_repo("spack/spack-packages", lazy=True)
            # Create the PR
            pr = spackages_repo.create_pull(
                base="develop",
                head=branch_id,
                body="""
Automated sync commit created by the snapshot release tags cron.

@spack/maintainers
"""
            )
            last_commit = pr.get_commits()[pr.commits - 1]
            # Trigger a rebuild everything on the PR to be reviewed by maintainers
            pr.create_comment("@spackbot rebuild everything", last_commit, "", 0)
    except Exception as e:
        print(f"Skipping spack-packages SPACK_CHECKOUT_VERSION update\nReason: {e}")
        pass

    print("Push done!")
