import argparse
from datetime import datetime, timedelta, timezone
import urllib.parse

import requests

import gitlab_api


"""
Set the GITLAB_PRIVATE_TOKEN environment variable to a valid personal access token

Provide UTC/Zulu times (for MST, just add 7 hours, for MDT, add 6)

Example usage:

    $ python cancel_pipelines.py https://gitlab.spack.io spack/spack \
        --updated-before 2021-09-23T15:16:00Z
        --updated-after 2021-09-21T15:16:00Z

"""


if __name__ == "__main__":
    start_time = datetime.now()

    parser = argparse.ArgumentParser(description="""Retrieve information on project pipelines""")
    parser.add_argument("gitlab_host", type=str,
        help="URL of gitlab instance, e.g. https://my.gitlab.com")
    parser.add_argument("gitlab_project", type=str,
        help="""Project ID (either numeric value or org/proj string, e.g. "spack/spack")""")
    parser.add_argument("-b", "--updated-before", type=str, default=None,
        help="""Only retrieve pipelines updated before this date (ISO 8601 format
e.g. "2019-03-15T08:00:00Z").  If none is provided, the default is the current time.""")
    parser.add_argument("-a", "--updated-after", type=str, default=None,
        help="""Only retrieve pipelines updated after this date (ISO 8601 format
e.g. "2019-03-15T08:00:00Z").  If none is provided, the default is 24 hrs before the current time.""")

    args = parser.parse_args()

    gitlab_host = args.gitlab_host
    gitlab_project = urllib.parse.quote_plus(args.gitlab_project)

    before = args.updated_before
    if not before:
        before_time = datetime.now(timezone.utc)
        before = before_time.strftime(gitlab_api.QUERY_TIME_FORMAT)
        print("Using updated_before={0}".format(before))

    after = args.updated_after
    if not after:
        after_time = datetime.now(timezone.utc) + timedelta(hours=-24)
        after = after_time.strftime(gitlab_api.QUERY_TIME_FORMAT)
        print("Using updated_after={0}".format(after))

    try:
        pipelines = gitlab_api.get_pipelines(gitlab_host,
                                             gitlab_project,
                                             updated_before=before,
                                             updated_after=after)

        print("Target pipelines:")

        for pipeline in pipelines:
            pipeline_id = pipeline["id"]
            pipeline_status = pipeline["status"]
            pipeline_ref = pipeline["ref"]

            print(f"    {pipeline_ref}: {pipeline_id} ({pipeline_status})")

            if pipeline_status != "pending" and pipeline_status != "running":
                print("        skip")
                continue

            # Now get the "bridge" jobs, which is the only way to find the generated
            # downstream pipelines.
            bridge_jobs_query = gitlab_api.GET_BRIDGE_JOBS.format(gitlab_project, pipeline_id)
            bridge_jobs_url = "{0}/{1}".format(gitlab_host, bridge_jobs_query)
            bridge_jobs = gitlab_api.paginate_query_url(bridge_jobs_url)

            # Each bridge job represents a generated downstream pipeline
            for bridge_job in bridge_jobs:
                bridge_job_name = bridge_job["name"]
                if "downstream_pipeline" not in bridge_job or not bridge_job["downstream_pipeline"]:
                    print(f"        ! {bridge_job_name} has no downstream pipeline")
                    continue

                downstream_pipeline = bridge_job["downstream_pipeline"]
                downstream_pid = downstream_pipeline["id"]
                downstream_status = downstream_pipeline['status']

                print(f"        {bridge_job_name}: {downstream_pid}")

                if downstream_status != "pending" and downstream_status != "running":
                    print("            skip")
                    continue

                cancel_query = gitlab_api.POST_CANCEL_PIPELINE.format(gitlab_project, downstream_pid)
                cancel_url = '{0}/{1}'.format(gitlab_host, cancel_query)
                resp = requests.post(cancel_url, headers=gitlab_api.get_common_headers())
                print(f"            posted cancel, response: {resp.text}")

            cancel_query = gitlab_api.POST_CANCEL_PIPELINE.format(gitlab_project, pipeline_id)
            cancel_url = '{0}/{1}'.format(gitlab_host, cancel_query)
            resp = requests.post(cancel_url, headers=gitlab_api.get_common_headers())
            print(f"        posted cancel, response: {resp.text}")

    finally:
        done_time = datetime.now()
        delta = done_time - start_time
        elapsed_seconds = delta.total_seconds()
        print("Finished in {0} seconds".format(elapsed_seconds))
