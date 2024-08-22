#!/usr/bin/env python3

from datetime import datetime, timezone
from github import Github, InputGitAuthor
import json
import os
import sentry_sdk
import urllib.request

sentry_sdk.init(
    # This cron job only runs once weekly,
    # so just record all transactions.
    traces_sample_rate=1.0,
)


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

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ref_name = f"develop-{date_str}"

    # Use the GitHub API to create a tag for this commit of develop.
    github_token = os.environ.get('GITHUB_TOKEN')
    py_github = Github(github_token)
    py_gh_repo = py_github.get_repo("spack/spack", lazy=True)
    print(f"Pushing ref {ref_name} for commit {sha}")

    # Create a ref for this sha using the date stamp
    py_gh_repo.create_git_ref(
        ref=f"refs/snapshots/{ref_name}",
        sha=sha)

    # Create a ref for this sha using the `develop-latest` tag for the GH-GL sync script
    py_gh_repo.create_git_ref(
        ref="refs/snapshots/develop-latest",
        sha=sha)

    print("Push done!")
