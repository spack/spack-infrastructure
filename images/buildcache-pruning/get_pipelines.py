import argparse
from datetime import datetime, timedelta, timezone
import json
import os
import re
import urllib.parse
import zipfile

import requests


"""
Set the GITLAB_PRIVATE_TOKEN environment variable to a valid personal access token

Run with:

    $ python get_pipelines.py https://gitlab.spack.io spack/spack [--updated-before <blah>] [--updated-after <bleh>]

"""


GITLAB_PRIVATE_TOKEN = os.environ.get("GITLAB_PRIVATE_TOKEN", None)

GET_PIPELINES   = "/api/v4/projects/{0}/pipelines?ref=develop&per_page=100"
GET_JOBS        = "/api/v4/projects/{0}/pipelines/{1}/jobs?per_page=100"
GET_ARTIFACTS   = "/api/v4/projects/{0}/jobs/{1}/artifacts"

QUERY_TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
GENERATE_JOB_REGEX = re.compile(r"(.+)-generate")


def get_common_headers():
    headers = {}

    if GITLAB_PRIVATE_TOKEN:
        headers["PRIVATE-TOKEN"] = GITLAB_PRIVATE_TOKEN

    return headers


def paginate_query_url(query_url):
    results = []

    while query_url:
        resp = requests.get(query_url, headers=get_common_headers())
        next_batch = json.loads(resp.content)

        if "message" in next_batch:
            msg = next_batch["message"]
            print(f"Query resulted in: {msg}")
            raise Exception

        for result in next_batch:
            results.append(result)

        if "next" in resp.links:
            query_url = resp.links["next"]["url"]
        else:
            query_url = None

    return results


def fetch_query_url(query_url):
    resp = requests.get(query_url, headers=get_common_headers())
    if resp.headers["Content-Type"] == "text/plain":
        return resp.content
    return json.loads(resp.content)


def get_pipelines(base_url, project_id, updated_before=None, updated_after=None):
    pipelines_query = GET_PIPELINES.format(project_id)
    pipelines_url = "{0}/{1}".format(base_url, pipelines_query)

    if updated_after:
        pipelines_url = "{0}&updated_after={1}".format(pipelines_url, updated_after)

    if updated_before:
        pipelines_url = "{0}&updated_before={1}".format(pipelines_url, updated_before)

    return paginate_query_url(pipelines_url)


def download_file(url, save_path):
    if os.path.exists(save_path):
        print(f"skipping {url} because we already have {save_path}")
        return

    os.makedirs(os.path.dirname(save_path), exist_ok=True)

    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        with open(save_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)


if __name__ == "__main__":
    start_time = datetime.now()

    parser = argparse.ArgumentParser(description="""Download artifacts for develop pipelines""")
    parser.add_argument("gitlab_host", type=str,
        help="URL of gitlab instance, e.g. https://my.gitlab.com")
    parser.add_argument("gitlab_project", type=str,
        help="""Project ID (either numeric value or org/proj string, e.g. "spack/spack")""")
    parser.add_argument("-b", "--updated-before", type=str, default=None,
        help="""Only retrieve pipelines updated before this date (ISO 8601 format
e.g. "2019-03-15T08:00:00Z").  If none is provided, the default is the current time.""")
    parser.add_argument("-a", "--updated-after", type=str, default=None,
        help="""Only retrieve pipelines updated after this date (ISO 8601 format
e.g. "2019-03-15T08:00:00Z").  If none is provided, the default is 2 weeks before the current time.""")
    parser.add_argument("-r", "--artifacts-dir", type=str, default=os.getcwd(),
        help="Directory to store downloaded artifacts, default is current directory")

    args = parser.parse_args()


    gitlab_host = args.gitlab_host
    gitlab_project = urllib.parse.quote_plus(args.gitlab_project)

    before = args.updated_before
    if not before:
        before_time = datetime.now(timezone.utc)
        before = before_time.strftime(QUERY_TIME_FORMAT)
        print("Using updated_before={0}".format(before))

    after = args.updated_after
    if not after:
        after_time = datetime.now(timezone.utc) + timedelta(weeks=-2)
        after = after_time.strftime(QUERY_TIME_FORMAT)
        print("Using updated_after={0}".format(after))

    download_dir = args.artifacts_dir
    if not os.path.exists(download_dir):
        os.makedirs(download_dir)

    print(f"Artifacts will be downloaded to: {download_dir}")

    all_pipeline_ids = []
    pipelines = None

    try:
        pipelines = get_pipelines(gitlab_host, gitlab_project, updated_before=before, updated_after=after)
    except Exception as e_inst:
        print("Caught exception getting pipelines")
        print(e_inst)

    if pipelines:
        for pipeline in pipelines:
            pipeline_id = pipeline["id"]
            all_pipeline_ids.append(pipeline_id)

            # Get the child pipeline generation jobs for this pipelline
            jobs_query = GET_JOBS.format(gitlab_project, pipeline_id)
            jobs_url = "{0}/{1}".format(gitlab_host, jobs_query)

            pipeline_jobs = None

            try:
                pipeline_jobs = paginate_query_url(jobs_url)
            except Exception as e_inst:
                print(f"Caught exception getting jobs for pipeline {pipeline_id}")
                print(e_inst)

            if pipeline_jobs:
                for p_job in pipeline_jobs:
                    job_name = p_job["name"]
                    job_status = p_job["status"]
                    job_id = p_job["id"]

                    m = GENERATE_JOB_REGEX.search(job_name)

                    if m and job_status == "success":
                        stack_name = m.group(1)

                        # Download and extract artifacts to <download_dir>/<pipeline_id>/<job_id>
                        artifacts_query = GET_ARTIFACTS.format(gitlab_project, job_id)
                        artifacts_url = "{0}/{1}".format(gitlab_host, artifacts_query)
                        artifacts_dir = os.path.join(download_dir, str(pipeline_id), str(job_id))
                        zip_file_path = os.path.join(artifacts_dir, "artifacts.zip")

                        try:
                            download_file(artifacts_url, zip_file_path)
                        except Exception as excp:
                            print(f"Caught exception downloading artifacts for pipeline/job: {pipeline_id}/{job_id}")
                            print(excp)
                            continue

                        try:
                            zip_file = zipfile.ZipFile(zip_file_path)
                            zip_file.extractall(os.path.join(artifacts_dir, stack_name))
                            zip_file.close()
                        except Exception as ex:
                            print(f"Cauht exception extractin artifacts for pipeline/job: {pipeline_id}/{job_id}")
                            print(ex)
                            continue
                    else:
                        print(f"pipeline {pipeline_id}: skipping {job_status} job {job_name}")

    done_time = datetime.now()
    delta = done_time - start_time
    elapsed_seconds = delta.total_seconds()

    print(f"Processed {len(all_pipeline_ids)} develop pipelines in {elapsed_seconds} seconds")
