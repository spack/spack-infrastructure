#!/usr/bin/env python3

from datetime import datetime, timezone
from github import Auth, Github, InputGitAuthor, GithubException
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
        latest_ref.edit(sha, force=True)
    else:
        repo.create_git_ref(
            ref=f"refs/{ref}",
            sha=sha)

    return True



if __name__ == "__main__":
    if "GITHUB_TOKEN" not in os.environ:
        raise Exception("GITHUB_TOKEN environment is not set")

    github_token = os.environ.get('GITHUB_TOKEN')
    py_github = Github(auth=Auth.Token(github_token))

    # Use the GitLab API to get the most recent successful develop pipeline.
    print("Searching for latest passing Gitlab pipeline")
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

    repo = py_github.get_repo("spack/spack-packages", lazy=True)
    # If the latest develop snapshot is updated, also push a new date snapshot
    if create_or_update_ref(repo, "snapshots/develop-latest", sha):
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        ref_name = f"snapshots/develop-{date_str}"

        print(f"Creating ref {ref_name} with commit {sha}")
        create_or_update_ref(repo, ref_name, sha)

    print("Push done!")
