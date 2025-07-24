import argparse
import json
import os
import urllib.parse
from datetime import datetime, timedelta, timezone
from requests import Session
from requests.adapters import HTTPAdapter, Retry

import sentry_sdk


sentry_sdk.init(traces_sample_rate=0.01)

GITLAB_API_URL = "https://gitlab.spack.io/api/v4/projects/"


def paginate(session, query_url):
    """Helper method to get all pages of paginated query results"""
    results = []

    while query_url:
        resp = session.get(query_url)

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


def retry_trigger_jobs(last_n_hours, projectid):
    """Analyze pipelines updated over the last_n_hours to find and retry
    child pipelines whose generate jobs failed initially but succeeded
    upon retry."""

    # Set up a Requests session with backoff, retries, and credentials.
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
    session.headers.update({
        'PRIVATE-TOKEN': os.environ.get("GITLAB_TOKEN", None)
    })

    # Iterate over recent pipelines.
    dt = datetime.now(timezone.utc) - timedelta(hours=last_n_hours)
    time_threshold = urllib.parse.quote_plus(dt.isoformat(timespec="seconds"))
    pipelines_url = f"{GITLAB_API_URL}/{projectid}/pipelines?updated_after={time_threshold}"
    pipelines = paginate(session, pipelines_url)
    for pipeline in pipelines:
        print(f"Checking pipeline {pipeline['id']}: {pipeline['ref']}")
        # Iterate over the trigger jobs ("bridges") for this parent pipeline.
        parent_id = pipeline['id']
        bridges_url = f"{GITLAB_API_URL}/{projectid}/pipelines/{parent_id}/bridges"
        bridges = paginate(session, bridges_url)
        for bridge in bridges:
            if not bridge["downstream_pipeline"]:
                continue
            child_pipeline = bridge["downstream_pipeline"]
            child_id = child_pipeline["id"]
            # Carefully try to detect the particular failure case we're interested in here.
            #
            # 1) The child pipeline failed.
            if child_pipeline["status"] != "failed":
                continue

            # 2) The trigger job reports an "unknown_failure".
            if bridge["failure_reason"] != "unknown_failure":
                continue

            # 3) The child pipeline does not have any jobs.
            child_jobs_url = f"{GITLAB_API_URL}/{projectid}/pipelines/{child_id}/jobs"
            child_jobs = paginate(session, child_jobs_url)
            if len(child_jobs) != 0:
                continue

            # 4) The generate job failed but succeeded upon retry.
            # GitLab API unfortunately doesn't provide a clean way to
            # find the relevant generate job for a given trigger job,
            # so we get all the jobs for the parent pipeline and look
            # for those with a particular name.
            generate_job_name = bridge["name"].replace("-build", "-generate")
            found_success = False
            found_failed = False
            parent_jobs_url = f"{GITLAB_API_URL}/{projectid}/pipelines/{parent_id}/jobs?include_retried=true"
            parent_jobs = paginate(session, parent_jobs_url)
            for job in parent_jobs:
                if job["name"] == generate_job_name:
                    if job["status"] == "success":
                        found_success = True
                    elif job["status"] == "failed":
                        found_failed = True
                    if found_success and found_failed:
                        # If we found at least one success and one failed
                        # generate job, retry the trigger job to fix the
                        # child pipeline.
                        print(f"!!! Retrying job #{bridge['id']} to fix pipeline {child_id}")
                        retry_url = f"{GITLAB_API_URL}/{projectid}/jobs/{bridge['id']}/retry"
                        print_response(session.post(retry_url))
                        break


def main():
    """Script entrypoint"""
    if "GITLAB_TOKEN" not in os.environ:
        raise Exception("GITLAB_TOKEN environment is not set")

    parser = argparse.ArgumentParser(
        prog="retry_trigger_jobs.py",
        description="Retry child pipelines that failed to generate initially",
    )
    parser.add_argument(
        "--hours",
        type=int,
        required=True,
        help="Number of hours to look back for failed child pipelines"
    )
    parser.add_argument(
        "--projectid",
        type=int,
        required=True,
        help="Gitlab project ID to search"
    )

    args = parser.parse_args()

    retry_trigger_jobs(args.hours, args.projectid)


################################################################################
#
if __name__ == "__main__":
    main()
