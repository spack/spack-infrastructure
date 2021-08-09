import argparse
import base64
from datetime import datetime, timedelta, timezone
import json
import os
import re
import urllib.parse
import zlib

import boto3
from botocore.exceptions import ClientError
import requests


"""
Set the GITLAB_PRIVATE_TOKEN environment variable to a valid personal access token

Provide UTC/Zulu times (for MST, just add 7 hours, for MDT, add 6)

Examples:

    Retrieve the first handful of pipelines in the project history:

        $ python examples/gitlab_api.py spack/spack --updated-before

"""


GITLAB_PRIVATE_TOKEN = os.environ.get('GITLAB_PRIVATE_TOKEN', None)

GET_PIPELINES   = '/api/v4/projects/{0}/pipelines?per_page=100'
GET_JOBS        = '/api/v4/projects/{0}/pipelines/{1}/jobs?per_page=100'
GET_BRIDGE_JOBS = '/api/v4/projects/{0}/pipelines/{1}/bridges?per_page=100'
GET_JOB_TRACE   = '/api/v4/projects/{0}/jobs/{1}/trace'
GET_ARTIFACTS   = '/api/v4/projects/{0}/jobs/{1}/artifacts'

QUERY_TIME_FORMAT = '%Y-%m-%dT%H:%M:%SZ'

PIPELINE_IGNORE_KEYS = [
    # 'web_url'
]

JOB_IGNORE_KEYS = [
    'allow_failure',
    'artifacts',
    'artifacts_expire_at',
    'artifacts_file',
    'coverage',
    'pipeline',
    'user'
]

COMMIT_IGNORE_KEYS = [
    'author_email',
    'author_name',
    'authored_date',
    'committed_date',
    'committer_email',
    'committer_name',
    'created_at',
    'short_id',
    'title',
    'web_url'
]

FAILURE_CATEGORIES = {
    'TLS_INTERNAL_ERROR': re.compile(r"error dialing backend: remote error: tls: internal error"),
    'HELPER_CONTAINER_NOT_FOUND': re.compile(r"unable to upgrade connection: container not found \(\"[^\"]+\"\)"),
    'TCP_CONNECTION_REFUSED': re.compile(r"error dialing backend: dial tcp \d+\.\d+\.\d+\.\d+:\d+: connect: connection refused"),
    'COULD_NOT_FIND_REMOTE_REF': re.compile(r"fatal: couldn't find remote ref"),
    'POD_NOT_FOUND': re.compile(r"prepare environment: pods \"[^\"]+\" not found"),
    'RUNNER_COULD_NOT_RESOLVE_HOST': re.compile(r"Could not resolve host: gitlab.next.spack.io"),
    'RUNNER_RESOURCE_PRESSURE': re.compile("ERROR: Job failed: command terminated with exit code 137"),
    'BROKEN_SPACK': re.compile(r"ERROR: Job failed: command terminated with exit code 1")
}


def get_common_headers():
    headers = {}

    if GITLAB_PRIVATE_TOKEN:
        headers['PRIVATE-TOKEN'] = GITLAB_PRIVATE_TOKEN

    return headers


def paginate_query_url(query_url):
    results = []

    while query_url:
        resp = requests.get(query_url, headers=get_common_headers())
        next_batch = json.loads(resp.content)

        for result in next_batch:
            results.append(result)

        if 'next' in resp.links:
            query_url = resp.links['next']['url']
        else:
            query_url = None

    return results


def fetch_query_url(query_url):
    resp = requests.get(query_url, headers=get_common_headers())
    if resp.headers['Content-Type'] == 'text/plain':
        return resp.content
    return json.loads(resp.content)


def get_pipelines(base_url, project_id, updated_before=None, updated_after=None):
    pipelines = []
    pipelines_query = GET_PIPELINES.format(project_id)
    pipelines_url = '{0}/{1}'.format(base_url, pipelines_query)

    if updated_after:
        pipelines_url = '{0}&updated_after={1}'.format(pipelines_url, updated_after)

    if updated_before:
        pipelines_url = '{0}&updated_before={1}'.format(pipelines_url, updated_before)

    return paginate_query_url(pipelines_url)


def trim_job_keys(job):
    for ignore_job_key in JOB_IGNORE_KEYS:
        job.pop(ignore_job_key, None)
        if 'commit' in job:
            for ignore_commit_key in COMMIT_IGNORE_KEYS:
                job['commit'].pop(ignore_commit_key, None)


def trim_pipeline_keys(pipeline):
    for pipeline_ignore_key in PIPELINE_IGNORE_KEYS:
        pipeline.pop(pipeline_ignore_key, None)


def categorize_trace(job_trace):
    for category in FAILURE_CATEGORIES:
        regex = FAILURE_CATEGORIES[category]
        m = regex.search(str(job_trace))
        if m:
            return category
    return 'UNKNOWN'

def add_job_trace(base_url, project_id, job):
    trace_query = GET_JOB_TRACE.format(project_id, job['id'])
    trace_url = '{0}/{1}'.format(base_url, trace_query)
    trace = fetch_query_url(trace_url)
    category = categorize_trace(trace)

    job['trace'] = str(base64.b64encode(zlib.compress(trace)).decode('utf-8'))
    job['failure_category'] = category


if __name__ == '__main__':
    start_time = datetime.now()

    parser = argparse.ArgumentParser(description="""Retrieve information on project pipelines""")
    parser.add_argument('gitlab_host', type=str,
        help="URL of gitlab instance, e.g. https://my.gitlab.com")
    parser.add_argument('gitlab_project', type=str,
        help="""Project ID (either numeric value or org/proj string, e.g. 'spack/spack')""")
    parser.add_argument('-b', '--updated-before', type=str, default=None,
        help="""Only retrieve pipelines updated before this date (ISO 8601 format
e.g. '2019-03-15T08:00:00Z').  If none is provided, the default is the current time.""")
    parser.add_argument('-a', '--updated-after', type=str, default=None,
        help="""Only retrieve pipelines updated after this date (ISO 8601 format
e.g. '2019-03-15T08:00:00Z').  If none is provided, the default is 24 hrs before the current time.""")
    parser.add_argument('--post-summary', default=False, action='store_true',
        help="Post summary file to S3 bucket (s3://spack-binaries-develop/pipeline-stats/yyyy/mm/dd/HH/MM)")

    args = parser.parse_args()


    gitlab_host = args.gitlab_host
    gitlab_project = urllib.parse.quote_plus(args.gitlab_project)

    before = args.updated_before
    if not before:
        before_time = datetime.now(timezone.utc)
        before = before_time.strftime(QUERY_TIME_FORMAT)
        print('Using updated_before={0}'.format(before))

    after = args.updated_after
    if not after:
        after_time = datetime.now(timezone.utc) + timedelta(hours=-24)
        after = after_time.strftime(QUERY_TIME_FORMAT)
        print('Using updated_after={0}'.format(after))

    post_summary = args.post_summary

    pipeline_details = []
    unrecognized_job_failures = []
    missing_downstreams = {}

    job_status_counts = {}
    pipeline_status_counts = {}
    failure_category_counts = {}

    def increment_pipeline_status(p_stat):
        if p_stat not in pipeline_status_counts:
            pipeline_status_counts[p_stat] = 0
        pipeline_status_counts[p_stat] += 1

    def increment_job_status(j_stat):
        if j_stat not in job_status_counts:
            job_status_counts[j_stat] = 0
        job_status_counts[j_stat] += 1

    def increment_failure_category(category):
        if category not in failure_category_counts:
            failure_category_counts[category] = 0
        failure_category_counts[category] += 1

    try:
        pipelines = get_pipelines(gitlab_host, gitlab_project, updated_before=before, updated_after=after)

        for pipeline in pipelines:
            trim_pipeline_keys(pipeline)

            pipeline_id = pipeline['id']
            increment_pipeline_status(pipeline['status'])

            # First get the jobs of the pipeline (which does not include child jobs
            # associated with generated downstream pipeline).  This is likely just the
            # single pipeline generation job for spack ci pipelines.
            jobs_query = GET_JOBS.format(gitlab_project, pipeline_id)
            jobs_url = '{0}/{1}'.format(gitlab_host, jobs_query)
            pipeline_jobs = paginate_query_url(jobs_url)
            saved_pipeline_jobs = []

            for p_job in pipeline_jobs:
                trim_job_keys(p_job)
                increment_job_status(p_job['status'])
                if p_job['status'] == 'failed':
                    add_job_trace(gitlab_host, gitlab_project, p_job)
                    increment_failure_category(p_job['failure_category'])
                    if p_job['failure_category'] == 'UNKNOWN':
                        unrecognized_job_failures.append(p_job['web_url'])
                    saved_pipeline_jobs.append(p_job)

            pipeline['jobs'] = saved_pipeline_jobs

            # Now get the "bridge" jobs, which will lead us to the the generated
            # downstream pipelines and their jobs.
            bridge_jobs_query = GET_BRIDGE_JOBS.format(gitlab_project, pipeline_id)
            bridge_jobs_url = '{0}/{1}'.format(gitlab_host, bridge_jobs_query)
            bridge_jobs = paginate_query_url(bridge_jobs_url)

            for b_job in bridge_jobs:
                trim_job_keys(b_job)
                if 'downstream_pipeline' in b_job:
                    if b_job['downstream_pipeline']: # We should have an actual pipeline
                        downstream_pipeline = b_job['downstream_pipeline']
                        ds_jobs_query = GET_JOBS.format(gitlab_project, downstream_pipeline['id'])
                        ds_jobs_url = '{0}/{1}'.format(gitlab_host, ds_jobs_query)
                        downstream_jobs = paginate_query_url(ds_jobs_url)
                        saved_downstream_jobs = []
                        for ds_job in downstream_jobs:
                            trim_job_keys(ds_job)
                            increment_job_status(ds_job['status'])
                            if ds_job['status'] == 'failed':
                                add_job_trace(gitlab_host, gitlab_project, ds_job)
                                increment_failure_category(ds_job['failure_category'])
                                if ds_job['failure_category'] == 'UNKNOWN':
                                    unrecognized_job_failures.append(ds_job['web_url'])
                                saved_downstream_jobs.append(ds_job)
                        b_job['downstream_pipeline']['jobs'] = saved_downstream_jobs
                    else: # We have 'downstream_pipeline': null for this bridge job
                        missing_downstreams[pipeline_id] = pipeline['web_url']
                else: # For some reason this bridge job is missing the key altogether
                    missing_downstreams[pipeline_id] = pipeline['web_url']

            pipeline['bridge_jobs'] = bridge_jobs
            pipeline_details.append(pipeline)

        total_jobs = sum([job_status_counts[status] for status in job_status_counts])
        total_pipelines = sum([pipeline_status_counts[status] for status in pipeline_status_counts])

        pipelines_object = {
            'project': args.gitlab_project,
            'updated_after': after,
            'updated_before': before,
            'pipelines': pipeline_details
        }

    finally:
        done_time = datetime.now()
        delta = done_time - start_time
        elapsed_seconds = delta.total_seconds()
        pipelines_object['processing_time'] = '{0} seconds'.format(elapsed_seconds)

    # Write out the json object we built
    with open('output.json', 'w') as json_file:
        json_file.write(json.dumps(pipelines_object))

    # Print some summary statistics
    with open('output.txt', 'w') as text_file:
        text_file.write('\nSummary for {0} to {1}\n\n'.format(after, before))

        text_file.write('  Total pipelines: {0}\n'.format(total_pipelines))
        for pipeline_status in pipeline_status_counts:
            count = pipeline_status_counts[pipeline_status]
            pct = (float(count) / total_pipelines) * 100
            text_file.write('    {0} {1} ({2}%)\n'.format(pipeline_status, count, '%.2f' % pct))

        text_file.write('  Total jobs: {0}\n'.format(total_jobs))
        for job_status in job_status_counts:
            count = job_status_counts[job_status]
            pct = (float(count) / total_jobs) * 100
            text_file.write('    {0} {1} ({2}%)\n'.format(job_status, count, '%.2f' % pct))

        if failure_category_counts:
            text_file.write('  Failure categories:\n')
            for cat in failure_category_counts:
                count = failure_category_counts[cat]
                pct = (float(count) / job_status_counts['failed']) * 100
                text_file.write('    {0} {1} ({2}%)\n'.format(cat, count, '%.2f' % pct))

        if unrecognized_job_failures:
            text_file.write('  The following jobs had unrecognized failures:\n')
            for failed_job_id in unrecognized_job_failures:
                text_file.write('    {0}\n'.format(failed_job_id))

        if missing_downstreams:
            text_file.write('  The following pipelines were missing at least one downstream pipeline:\n')
            for pid in missing_downstreams:
                text_file.write('    {0}\n'.format(missing_downstreams[pid]))

        text_file.write('\nFinshed after {0} seconds\n\n'.format(elapsed_seconds))

    with open('output.txt') as read_back:
        print(read_back.read())

    if post_summary:
        now = datetime.now()
        now_dir = now.strftime('%Y/%m')
        now_name = now.strftime('%Y_%m_%d_%H_%M')
        object_name = 'pipeline-statistics/' + now_dir + '/daily_summary_{0}.txt'.format(now_name)
        s3_client = boto3.client('s3')
        try:
            response = s3_client.upload_file('output.txt', 'spack-logs', object_name)
        except ClientError as e:
            print(e)
