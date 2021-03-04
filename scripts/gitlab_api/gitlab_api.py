import argparse
import base64
import datetime
import json
import os
import re
import urllib.parse
import zlib

import requests


"""
Set the GITLAB_PRIVATE_TOKEN environment variable to a valid personal access token

Provide UTC/Zulu times (for MST, just add 7 hours, for MDT, add 6)

Examples:

    Retrieve the first handful of pipelines in the project history:

        $ python examples/gitlab_api.py spack/spack --updated-before "2021-02-18T19:00:00Z"

"""


GITLAB_PRIVATE_TOKEN = os.environ.get('GITLAB_PRIVATE_TOKEN', None)

GET_PIPELINES   = 'https://gitlab.next.spack.io/api/v4/projects/{0}/pipelines?per_page=100'
GET_JOBS        = 'https://gitlab.next.spack.io/api/v4/projects/{0}/pipelines/{1}/jobs?per_page=100'
GET_BRIDGE_JOBS = 'https://gitlab.next.spack.io/api/v4/projects/{0}/pipelines/{1}/bridges?per_page=100'
GET_JOB_TRACE   = 'https://gitlab.next.spack.io/api/v4/projects/{0}/jobs/{1}/trace'

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


def get_pipelines(project_id, updated_before=None, updated_after=None):
    pipelines = []
    pipelines_url = GET_PIPELINES.format(project_id)

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

def add_job_trace(project_id, job):
    trace_url = GET_JOB_TRACE.format(project_id, job['id'])
    trace = fetch_query_url(trace_url)
    category = categorize_trace(trace)

    job['trace'] = str(base64.b64encode(zlib.compress(trace)).decode('utf-8'))
    job['failure_category'] = category


if __name__ == '__main__':
    start_time = datetime.datetime.now()

    parser = argparse.ArgumentParser(description="""Retrieve information on project pipelines""")
    parser.add_argument('project_id', metavar='project', type=str,
        help="""Project ID (either numeric value or org/proj string, e.g. 'spack/spack')""")
    parser.add_argument('-b', '--updated-before', type=str, default=None,
        help="Only retrieve pipelines updated before this date (ISO 8601 format e.g. '2019-03-15T08:00:00Z')")
    parser.add_argument('-a', '--updated-after', type=str, default=None,
        help="Only retrieve pipelines updated after this date (ISO 8601 format e.g. '2019-03-15T08:00:00Z')")

    args = parser.parse_args()

    project_id = urllib.parse.quote_plus(args.project_id)
    before = args.updated_before
    after = args.updated_after

    pipeline_details = []
    unrecognized_job_failures = []

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
        pipelines = get_pipelines(project_id, updated_before=before, updated_after=after)

        for pipeline in pipelines:
            trim_pipeline_keys(pipeline)

            pipeline_id = pipeline['id']
            increment_pipeline_status(pipeline['status'])

            # First get the jobs of the pipeline (which does not include child jobs
            # associated with generated downstream pipeline).  This is likely just the
            # single pipeline generation job for spack ci pipelines.
            jobs_url = GET_JOBS.format(project_id, pipeline_id)
            pipeline_jobs = paginate_query_url(jobs_url)
            saved_pipeline_jobs = []

            for p_job in pipeline_jobs:
                trim_job_keys(p_job)
                increment_job_status(p_job['status'])
                if p_job['status'] == 'failed':
                    add_job_trace(project_id, p_job)
                    increment_failure_category(p_job['failure_category'])
                    if p_job['failure_category'] == 'UNKNOWN':
                        unrecognized_job_failures.append(p_job['web_url'])
                    saved_pipeline_jobs.append(p_job)

            pipeline['jobs'] = saved_pipeline_jobs

            # Now get the "bridge" jobs, which will lead us to the the generated
            # downstream pipelines and their jobs.
            bridge_jobs_url = GET_BRIDGE_JOBS.format(project_id, pipeline_id)
            bridge_jobs = paginate_query_url(bridge_jobs_url)

            for b_job in bridge_jobs:
                trim_job_keys(b_job)
                if 'downstream_pipeline' in b_job:
                    if b_job['downstream_pipeline']: # We should have an actual pipeline
                        downstream_pipeline = b_job['downstream_pipeline']
                        ds_jobs_url = GET_JOBS.format(project_id, downstream_pipeline['id'])
                        downstream_jobs = paginate_query_url(ds_jobs_url)
                        saved_downstream_jobs = []
                        for ds_job in downstream_jobs:
                            trim_job_keys(ds_job)
                            increment_job_status(ds_job['status'])
                            if ds_job['status'] == 'failed':
                                add_job_trace(project_id, ds_job)
                                increment_failure_category(ds_job['failure_category'])
                                if ds_job['failure_category'] == 'UNKNOWN':
                                    unrecognized_job_failures.append(ds_job['web_url'])
                                saved_downstream_jobs.append(ds_job)
                        b_job['downstream_pipeline']['jobs'] = saved_downstream_jobs
                    else: # We have 'downstream_pipeline': null for this bridge job
                        print('ALERT: child pipeline missing for pipeline')
                        print('  {0}'.format(pipeline['web_url']))

            pipeline['bridge_jobs'] = bridge_jobs
            pipeline_details.append(pipeline)

        # Print some summary statistics
        total_jobs = sum([job_status_counts[status] for status in job_status_counts])
        total_pipelines = sum([pipeline_status_counts[status] for status in pipeline_status_counts])

        print()
        print('Summary\n')

        print('  Total pipelines: {0}'.format(total_pipelines))
        for pipeline_status in pipeline_status_counts:
            count = pipeline_status_counts[pipeline_status]
            pct = (float(count) / total_pipelines) * 100
            print('    {0} {1} ({2}%)'.format(pipeline_status, count, '%.2f' % pct))

        print('  Total jobs: {0}'.format(total_jobs))
        for job_status in job_status_counts:
            count = job_status_counts[job_status]
            pct = (float(count) / total_jobs) * 100
            print('    {0} {1} ({2}%)'.format(job_status, count, '%.2f' % pct))

        if failure_category_counts:
            print('  Failure categories:')
            for cat in failure_category_counts:
                count = failure_category_counts[cat]
                pct = (float(count) / job_status_counts['failed']) * 100
                print('    {0} {1} ({2}%)'.format(cat, count, '%.2f' % pct))

        if unrecognized_job_failures:
            print('  The following jobs had unrecognized failures:')
            for failed_job_id in unrecognized_job_failures:
                print('    {0}'.format(failed_job_id))

        print()
    finally:
        done_time = datetime.datetime.now()
        delta = done_time - start_time
        elapsed_seconds = delta.total_seconds()

        pipelines_object = {
            'project': args.project_id,
            'updated_after': after,
            'updated_before': before,
            'processing_time': '{0} seconds'.format(elapsed_seconds),
            'pipelines': pipeline_details
        }

        # Write out the json object we built
        with open('output.json', 'w') as fd:
            fd.write(json.dumps(pipelines_object))

        print('\nFinshed after {0} seconds\n'.format(elapsed_seconds))
