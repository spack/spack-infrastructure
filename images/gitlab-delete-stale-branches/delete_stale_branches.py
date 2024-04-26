#!/usr/bin/env python

import json
import os
import re
import urllib.parse
from datetime import datetime, timedelta, timezone

import requests
import sentry_sdk

sentry_sdk.init(
    # This cron job only runs once a week,
    # so just record all transactions.
    traces_sample_rate=1.0,
)


GITLAB_API_URL = "https://gitlab.spack.io/api/v4/projects/2"
AUTH_HEADER = {
    "PRIVATE-TOKEN": os.environ.get("GITLAB_TOKEN", None)
}


def paginate(query_url):
    """Helper method to get all pages of paginated query results"""
    results = []

    while query_url:
        resp = requests.get(query_url, headers=AUTH_HEADER)
        if resp.status_code == 401:
            print(" !!! Unauthorized to make request, check GITLAB_TOKEN !!!")

        resp.raise_for_status()


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


def delete_branch(branch_name):
    """Delete the given branch from GitLab"""
    branch_name_encoded = urllib.parse.quote_plus(branch_name)
    del_url = f"{GITLAB_API_URL}/repository/branches/{branch_name_encoded}"
    print_response(requests.delete(del_url, headers=AUTH_HEADER), "      ")


def delete_stale_branches():
    """Delete any unprotected branches that have not been updated for 100 days"""

    pr_branch_regex = re.compile("pr([0-9]+)")

    now = datetime.now(timezone.utc)
    stale_threshold = now - timedelta(days=100)

    print(f"Querying for stale branches to delete")
    branches_url = f"{GITLAB_API_URL}/repository/branches"
    branches = paginate(branches_url)
    print(f"Found {len(branches)} branches")

    for branch in branches:
        branch_name = branch["name"]

        if branch["protected"]:
            print(f"Not considering {branch_name} for deletion because it is a protected branch")
            continue

        m = pr_branch_regex.search(branch_name)

        if not m:
            print(f"Not a PR branch: {branch_name}")
            continue

        updated_at_str = branch["commit"]["created_at"]

        # strptime only support microseconds (not milliseconds).
        # Time for some string massaging.
        updated_at_str = updated_at_str.split(".")[0]
        updated_at_str += "Z+0000"
        updated_at = datetime.strptime(updated_at_str, "%Y-%m-%dT%H:%M:%SZ%z")
        if updated_at < stale_threshold:
            print(f"Deleting {branch_name} because it was last updated more than 100 days ago ({updated_at})")
            delete_branch(branch_name)
        else:
            print(f"Not deleting {branch_name} because it was updated more recently than 100 days ago ({updated_at})")


if __name__ == "__main__":
    if "GITLAB_TOKEN" not in os.environ:
        raise Exception("GITLAB_TOKEN environment is not set")

    delete_stale_branches()
