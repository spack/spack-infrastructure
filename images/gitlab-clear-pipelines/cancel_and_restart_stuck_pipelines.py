#!/usr/bin/env python

import argparse
import json
import os
import urllib.parse
from datetime import datetime

import requests


GITLAB_API_URL = "https://gitlab.spack.io/api/v4/projects/2"
TIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
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
    print(f"    running new pipeline for {pipeline_ref}")
    print_response(requests.post(run_url, headers=AUTH_HEADER), "      ")


def cancel_downstream_pipelines(pipeline_id):
    """Given a pipeline id, query gitlab for its downstream pipelines
    and cancel them one at a time.  Once all the child pipelines are
    canceled, also cancel the parent pipeline."""
    bridges_url = f"{GITLAB_API_URL}/pipelines/{pipeline_id}/bridges"
    bridge_jobs = paginate(bridges_url)

    for bridge in bridge_jobs:
        if "downstream_pipeline" in bridge and bridge["downstream_pipeline"]:
            child_pipeline = bridge["downstream_pipeline"]
            child_pid = child_pipeline["id"]
            print(f"    canceling child pipeline {child_pid}")
            cancel_url = f"{GITLAB_API_URL}/pipelines/{child_pid}/cancel"
            print_response(requests.post(cancel_url, headers=AUTH_HEADER), "      ")

    print(f"    canceling parent pipeline {pipeline_id}")
    cancel_url = f"{GITLAB_API_URL}/pipelines/{pipeline_id}/cancel"
    print_response(requests.post(cancel_url, headers=AUTH_HEADER), "      ")


def cancel_and_restart_stuck_pipelines(num_days=0):
    """Query gitlab for all running pipelines.  For any pipeline that is
    more than 1 day old, run a new pipeline on the assocatied ref/branch,
    and then  cancel the pipeline as well as its downstream child
    pipelines.  Any pipeolines created fewer than num_days ago will
    be ignored."""
    print(f"Attempting to cancel and retry pipelines older than {num_days} days")

    time_now = datetime.utcnow()

    pipelines_url = f"{GITLAB_API_URL}/pipelines?status=running"
    running_pipelines = paginate(pipelines_url)

    print(f"Retrieved {len(running_pipelines)} pipelines:")
    for pipeline in running_pipelines:
        p_id = pipeline["id"]
        p_ref = pipeline["ref"]
        p_created = pipeline["created_at"]

        time_pipeline = datetime.strptime(p_created, TIME_FORMAT)
        elapsed_days = (time_now - time_pipeline).days

        if elapsed_days > num_days:
            print(f"  Cleaning up stuck pipeline {p_id} created at {p_created}")
            run_new_pipeline(p_ref)
            cancel_downstream_pipelines(p_id)
        else:
            print(f"  Ignoring pipeline {p_id} created at {p_created}")


if __name__ == "__main__":
    if "GITLAB_TOKEN" not in os.environ:
        raise Exception("GITLAB_TOKEN environment is not set")

    parser = argparse.ArgumentParser(description="Find stuck pipelines to cancel and restart")
    parser.add_argument("--num-days", default=0, type=int,
                        help="Ignore pipelines created fewer than this many days ago")
    args = parser.parse_args()

    try:
        cancel_and_restart_stuck_pipelines(args.num_days)
    except Exception as inst:
        print("Caught unhandled exception:")
        print(inst)
