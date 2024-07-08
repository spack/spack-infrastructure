#!/usr/bin/env python

import json
import os
import re
import urllib.parse
from datetime import datetime, timedelta, timezone

from requests import Session
from requests.adapters import HTTPAdapter, Retry
import sentry_sdk

sentry_sdk.init(
    # This cron job only runs every 30 mins,
    # so just record all transactions.
    traces_sample_rate=1.0,
)


GITLAB_API_URL = "https://gitlab.spack.io/api/v4/projects/2"
AUTH_HEADER = {
    "PRIVATE-TOKEN": os.environ.get("GITLAB_TOKEN", None)
}

session = Session()
session.mount(
    "https://",
    HTTPAdapter(
        max_retries=Retry(
            total=5,
            backoff_factor=2,
            backoff_jitter=1,
        ),
    ),
)


def paginate(query_url):
    """Helper method to get all pages of paginated query results"""
    results = []

    while query_url:
        try:
            resp = session.get(query_url, headers=AUTH_HEADER, timeout=10)
        except OSError as e:
            print(f"Request to {query_url} failed")
            sentry_sdk.capture_exception(e)
            return []

        if resp.status_code == 401:
            print(" !!! Unauthorized to make request, check GITLAB_TOKEN !!!")
            return []

        next_batch = json.loads(resp.content)

        for result in next_batch:
            results.append(result)

        if "next" in resp.links:
            query_url = resp.links["next"]["url"]
        else:
            query_url = None

    return results


def print_response(resp, padding=''):
    """Helper method to print response status code and content"""
    print(f"{padding}response code: {resp.status_code}")
    print(f"{padding}response value: {resp.text}")


def run_new_pipeline(pipeline_ref):
    """Given a ref (branch name), run a new pipeline for that ref.  If
    the branch has already been deleted from gitlab, this will generate
    an error and a 400 response, but we probably don't care."""
    enc_ref = urllib.parse.quote_plus(pipeline_ref)
    run_url = f"{GITLAB_API_URL}/pipeline?ref={enc_ref}"
    print(f"    !!!! running new pipeline for {pipeline_ref}")
    try:
        resp = session.post(run_url, headers=AUTH_HEADER, timeout=10)
    except OSError as e:
        print(f"Request to {run_url} failed")
        sentry_sdk.capture_exception(e)
        return None
    print_response(resp, "      ")


def find_and_run_skipped_pipelines():
    """Query gitlab for all branches. Start a pipeline for any branch whose
    HEAD commit does not already have one.
    """

    pr_branch_regex = re.compile("pr([0-9]+)")

    now = datetime.now(timezone.utc)
    two_days_ago = now - timedelta(days=2)
    one_hour_ago = now - timedelta(hours=1)

    after_param = datetime.strftime(two_days_ago, '%Y-%m-%d')
    events_url = f"{GITLAB_API_URL}/events?action=pushed&after={after_param}"
    print(f"Getting push events from GitLab from the past two days")
    events = paginate(events_url)
    print(f"Found {len(events)} push events")

    recently_pushed_branches = []

    for event in events:
        if "created_at" not in event or "push_data" not in event or "commit_to" not in event["push_data"]:
            continue

        branch_name = event["push_data"]["ref"]
        if branch_name is None:
            continue

        head_commit = event["push_data"]["commit_to"]
        if head_commit is None:
            continue

        m = pr_branch_regex.search(branch_name)
        if not m:
            continue

        pushed_at_str = event["created_at"]
        # strptime only support microseconds (not milliseconds).
        # Time for some string massaging.
        pushed_at_str = pushed_at_str.split(".")[0]
        pushed_at_str += "Z+0000"
        pushed_at = datetime.strptime(pushed_at_str, "%Y-%m-%dT%H:%M:%SZ%z")
        if pushed_at > one_hour_ago:
            recently_pushed_branches.append(branch_name)

    print(f"Attempting to find & fix skipped pipelines")
    branches_url = f"{GITLAB_API_URL}/repository/branches"
    branches = paginate(branches_url)
    print(f"Found {len(branches)} branches")

    for branch in branches:
        branch_name = branch["name"]
        m = pr_branch_regex.search(branch_name)
        if not m:
            print(f"Not a PR branch: {branch_name}")
            continue

        if branch_name in recently_pushed_branches:
            print(f"Skip {branch_name} since it was pushed to GitLab within the last hour")
            continue

        branch_commit = branch["commit"]["id"]
        pipelines_url = f"{GITLAB_API_URL}/pipelines?sha={branch_commit}"
        pipelines = paginate(pipelines_url)
        if len(pipelines) == 0:
            run_new_pipeline(branch_name)
        else:
            print(f"no need to run a new pipeline for {branch_name}")


if __name__ == "__main__":
    if "GITLAB_TOKEN" not in os.environ:
        raise Exception("GITLAB_TOKEN environment is not set")
    try:
        find_and_run_skipped_pipelines()
    except Exception as inst:
        print("Caught unhandled exception:")
        print(inst)
