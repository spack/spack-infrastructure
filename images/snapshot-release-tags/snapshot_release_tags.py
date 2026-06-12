#!/usr/bin/env python3

from datetime import datetime, timezone
from github import Github, InputGitAuthor, GithubException
import json
import os
import sys
import urllib.request

try:
    import sentry_sdk
    sentry_sdk.init(
        # This cron job only runs once weekly,
        # so just record all transactions.
        traces_sample_rate=1.0,
    )
except ImportError:
    print("Running without sentry")


if __name__ == "__main__":
    if "GITHUB_TOKEN" not in os.environ:
        raise Exception("GITHUB_TOKEN environment is not set")

    github_token = os.environ.get('GITHUB_TOKEN')
    py_github = Github(github_token)

    # Use the GitLab API to get the most recent successful develop pipeline.
    gitlab_api_url = "https://gitlab.spack.io/api/v4/projects/57"
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
    print(f"Gitlab pipeline: {sha}")

    # Check if this sha is already the latest snapshot
    py_gh_repo = py_github.get_repo("spack/spack-packages", lazy=True)
    try:
        latest_ref = py_gh_repo.get_git_ref("snapshots/develop-latest")
        if latest_ref.object.sha == sha:
            print("Latest ref is already latest snapshot")
            sys.exit(0)
    except GithubException:
        # Failure to get the latest_ref means it doesn't exist and needs to be recreated.
        latest_ref = None
        pass

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ref_name = f"develop-{date_str}"

    # Use the GitHub API to create a tag for this commit of develop.
    print(f"Pushing ref {ref_name} for commit {sha}")

    print(f"snapshots/{ref_name}: {sha}")
    # Create a ref for this sha using the date stamp
    py_gh_repo.create_git_ref(
        ref=f"refs/snapshots/{ref_name}",
        sha=sha)

    # Create a ref for this sha using the `develop-latest` tag for the GH-GL sync script
    print(f"snapshots/develop-latest: {sha}")
    if latest_ref is not None:
        latest_ref.edit(sha, force=True)
    else:
        py_gh_repo.create_git_ref(
            ref="refs/snapshots/develop-latest",
            sha=sha)

    print("Push done!")
