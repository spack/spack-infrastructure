#!/usr/bin/env python3

from datetime import datetime, timezone
from github import Github, InputGitAuthor
import json
import os
import re
import subprocess
import tempfile
import urllib.request

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
    tag_name = f"develop-{date_str}"
    tag_msg = f"Snapshot release {date_str}"

    # Use the GitHub API to create a tag for this commit of develop.
    github_token = os.environ.get('GITHUB_TOKEN')
    py_github = Github(github_token)
    py_gh_repo = py_github.get_repo("spack/spack", lazy=True)
    spackbot_author = InputGitAuthor("spackbot", "noreply@spack.io")
    print(f"Pushing tag {tag_name} for commit {sha}")
    py_gh_repo.create_git_tag_and_release(
        tag=tag_name,
        tag_message=tag_msg,
        release_name=tag_name,
        release_message=tag_msg,
        object=sha,
        type="commit",
        tagger=spackbot_author)
    print("Push done!")
