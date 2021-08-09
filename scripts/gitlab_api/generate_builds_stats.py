import argparse
import base64
from datetime import datetime, timedelta, timezone
import json
import os
import re
import shutil
import sqlite3
import urllib.parse
import zipfile
import zlib

import boto3
from botocore.exceptions import ClientError
import requests
import ruamel.yaml as yaml

import gitlab_api


"""
Set the GITLAB_PRIVATE_TOKEN environment variable to a valid personal access token

Provide UTC/Zulu times (for MST, just add 7 hours, for MDT, add 6)

Example usage:

    $ python generate_builds_stats.py https://gitlab.spack.io spack/spack \
        --db-path /Users/scott/Documents/spack/statistics-on-builds/db/pipelines.db \
        --updated-after 2021-07-10T12:00:00Z

"""

GITLAB_PR_BRANCH_REGEX = re.compile(r"^github/pr([\d]+)_(.+)$")


def download_artifacts(url, save_path, chunk_size=65536):
    r = requests.get(url, stream=True)

    save_dir = os.path.dirname(save_path)
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    with open(save_path, 'wb') as fd:
        for chunk in r.iter_content(chunk_size=chunk_size):
            fd.write(chunk)


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
    parser.add_argument('--db-path', type=str, default=None, help="""Absolute path to sqlite3 database
file to create or open for editing.  Default is None, which results in no database updates.""")
    parser.add_argument('--cache-dir', type=str, default=os.getcwd(), help="""Directory in which
to cache objects fetched via api (avoids fetching the same thing multiple times).  Defaults to
the current working directory.""")

    args = parser.parse_args()

    gitlab_host = args.gitlab_host
    gitlab_project = urllib.parse.quote_plus(args.gitlab_project)

    before = args.updated_before
    if not before:
        before_time = datetime.now(timezone.utc)
        before = before_time.strftime(gitlab_api.QUERY_TIME_FORMAT)
        print('Using updated_before={0}'.format(before))

    after = args.updated_after
    if not after:
        after_time = datetime.now(timezone.utc) + timedelta(hours=-24)
        after = after_time.strftime(gitlab_api.QUERY_TIME_FORMAT)
        print('Using updated_after={0}'.format(after))

    db_connection = None
    db_cursor = None
    if args.db_path:
        db_connection = sqlite3.connect(args.db_path)
        db_cursor = db_connection.cursor()

        db_cursor.execute("PRAGMA foreign_keys = ON;")

        tables = db_cursor.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()
        tables = [t[0] for t in tables]

        if 'pipelines' not in tables:
            print('Creating "pipelines" table')
            db_cursor.execute("""CREATE TABLE pipelines (
                pipeline_id INTEGER NOT NULL primary key,
                link TEXT,
                pr_number TEXT,
                branch TEXT,
                create_time TEXT,
                update_time TEXT
            );""")

        if 'builds' not in tables:
            print('Creating "builds" table')
            db_cursor.execute("""CREATE TABLE builds (
                job_id INTEGER NOT NULL primary key,
                job_name TEXt,
                runner TEXT,
                status TEXT,
                duration REAL,
                pkg_name TEXT,
                dag_hash TEXT,
                build_hash TEXT,
                full_hash TEXT,
                link TEXT,
                create_time TEXT,
                start_time TEXT,
                pipeline_id INTEGER NOT NULL,
                FOREIGN KEY (pipeline_id)
                    REFERENCES pipelines (pipeline_id)
            );""")

        if 'generates' not in tables:
            print('Creating "generates" table')
            db_cursor.execute("""CREATE TABLE generates (
                job_id INTEGER NOT NULL primary key,
                status TEXT,
                duration REAL,
                runner TEXT,
                link TEXT,
                create_time TEXT,
                start_time TEXT,
                pipeline_id INTEGER NOT NULL,
                FOREIGN KEY (pipeline_id)
                    REFERENCES pipelines (pipeline_id)
            );""")

    ignore_keys = [
        'cleanup',
        'rebuild-index',
        'stages',
        'variables',
        'no-specs-to-rebuild'
    ]

    required_hashes = [
        'SPACK_JOB_SPEC_DAG_HASH',
        'SPACK_JOB_SPEC_BUILD_HASH',
        'SPACK_JOB_SPEC_FULL_HASH'
    ]

    try:
        pipelines = gitlab_api.get_pipelines(gitlab_host,
                                             gitlab_project,
                                             updated_before=before,
                                             updated_after=after)

        for pipeline in pipelines:
            pipeline_id = pipeline['id']
            cached_pipeline_dir = os.path.join(args.cache_dir, 'pipelines', str(pipeline_id))
            cached_jobs_json = os.path.join(cached_pipeline_dir, 'jobs.json')
            pipeline_jobs = None

            if not (os.path.exists(cached_pipeline_dir)):
                os.makedirs(cached_pipeline_dir)

            cached_pipeline_file = os.path.join(cached_pipeline_dir, 'pipeline.json')
            if not os.path.exists(cached_pipeline_file):
                with open(cached_pipeline_file, 'w') as fd:
                    print('caching pipeline {0} in {1}'.format(pipeline_id, cached_pipeline_file))
                    fd.write(json.dumps(pipeline))

            pr_number = 'None'
            branch = 'None'
            m = GITLAB_PR_BRANCH_REGEX.match(pipeline['ref'])
            if m:
                pr_number = m.group(1)
                branch = m.group(2)
            else:
                if pipeline['ref'] == 'github/develop':
                    branch = 'develop'

            if db_cursor:
                db_cursor.execute(
                    "INSERT OR IGNORE INTO pipelines VALUES (?, ?, ?, ?, ?, ?);",
                    (
                        pipeline_id,
                        pipeline['web_url'],
                        pr_number,
                        branch,
                        pipeline['created_at'],
                        pipeline['updated_at']
                    ))

            if os.path.exists(cached_jobs_json):
                with open(cached_jobs_json) as fd:
                    pipeline_jobs = json.loads(fd.read())
            else:
                # First get the jobs of the pipeline (which includes only the pipeline
                # generation jobs, since the pipelines query doesn't return dynamically
                # created pipelines generation jobs.
                jobs_query = gitlab_api.GET_JOBS.format(gitlab_project, pipeline_id)
                jobs_url = '{0}/{1}'.format(gitlab_host, jobs_query)
                pipeline_jobs = gitlab_api.paginate_query_url(jobs_url)

                with open(cached_jobs_json, 'w') as fd:
                    print('caching {0} in {1}'.format(jobs_url, cached_jobs_json))
                    fd.write(json.dumps(pipeline_jobs))

            generated_jobs = {}

            for p_job in pipeline_jobs:
                job_id = p_job['id']

                # If job was canceled, then runner is null
                job_runner = 'None'
                if 'runner' in p_job and p_job['runner']:
                    job_runner = p_job['runner']['description']

                # Regardless of the status of this pipeline generation job, we store
                # it in the database
                db_cursor.execute(
                    "INSERT OR IGNORE INTO generates VALUES (?, ?, ?, ?, ?, ?, ?, ?);",
                    (
                        job_id,
                        p_job['status'],
                        p_job['duration'],
                        job_runner,
                        p_job['web_url'],
                        p_job['created_at'],
                        p_job['started_at'],
                        pipeline_id
                    ))

                if p_job['status'] != 'success':
                    # These are pipeline generation jobs, not downstream child jobs,
                    # so there are no artifacts to retrieve if the job failed.
                    continue

                cached_job_dir = os.path.join(cached_pipeline_dir, str(job_id))
                job_artifacts_dir = os.path.join(cached_job_dir, 'artifacts')
                if not os.path.exists(job_artifacts_dir):
                    artifacts_query = gitlab_api.GET_ARTIFACTS.format(gitlab_project, job_id)
                    artifacts_url = '{0}/{1}'.format(gitlab_host, artifacts_query)
                    cached_artifacts_zip = os.path.join(cached_job_dir, 'artifacts.zip')

                    download_artifacts(artifacts_url, cached_artifacts_zip)

                    try:
                        zip_file = zipfile.ZipFile(cached_artifacts_zip)
                        zip_file.extractall(job_artifacts_dir)
                    except Exception as e_inst:
                        print('Unable to extract cached artifacts for job {}'.format(
                            job_id))
                        print(e_inst)
                        continue
                    finally:
                        if zip_file:
                            zip_file.close()
                        os.remove(cached_artifacts_zip)

                # Now we have the dynamically generated pipeline file as well as the
                # spack.yaml and spack.lock for this pipeline generation job
                generated_pipeline_yaml = os.path.join(
                    job_artifacts_dir, 'jobs_scratch_dir', 'cloud-ci-pipeline.yml')

                gen_yaml_jobs = {}

                try:
                    with open(generated_pipeline_yaml) as fd:
                        gen_yaml_jobs = yaml.safe_load(fd.read())
                except:
                    print('No generated pipeline yaml found for job {0}'.format(job_id))

                for job_name, job_definition in gen_yaml_jobs.items():
                    if job_name not in ignore_keys:
                        if job_name in generated_jobs:
                            print(' **** WARNING: duplicated job key: {0} for pipeline: {1}'.format(
                                job_name, pipeline_id))
                        else:
                            generated_jobs[job_name] = job_definition

            cached_bridge_jobs_json = os.path.join(cached_pipeline_dir, 'bridge_jobs.json')
            bridge_jobs = None

            if os.path.exists(cached_bridge_jobs_json):
                with open(cached_bridge_jobs_json) as fd:
                    bridge_jobs = json.loads(fd.read())
            else:
                # Now get the "bridge" jobs, which is the only way to find the generated
                # downstream pipelines and their jobs.
                bridge_jobs_query = gitlab_api.GET_BRIDGE_JOBS.format(gitlab_project, pipeline_id)
                bridge_jobs_url = '{0}/{1}'.format(gitlab_host, bridge_jobs_query)
                bridge_jobs = gitlab_api.paginate_query_url(bridge_jobs_url)

                with open(cached_bridge_jobs_json, 'w') as fd:
                    print('caching {0} in {1}'.format(bridge_jobs_url, cached_bridge_jobs_json))
                    fd.write(json.dumps(bridge_jobs))

            # Each bridge job represents a generated downstream pipeline
            for bridge_job in bridge_jobs:
                if 'downstream_pipeline' not in bridge_job or not bridge_job['downstream_pipeline']:
                    print(' ^^^^ WARNING: bridge job {0} has no downstream pipeline (pipeline: {1})'.format(
                        bridge_job['name'], pipeline_id))
                    continue

                cached_child_jobs_json = os.path.join(cached_pipeline_dir, str(bridge_job['id']), 'child_jobs.json')
                downstream_jobs = None

                if os.path.exists(cached_child_jobs_json):
                    with open(cached_child_jobs_json) as fd:
                        downstream_jobs = json.loads(fd.read())
                else:
                    if not os.path.exists(os.path.dirname(cached_child_jobs_json)):
                        os.makedirs(os.path.dirname(cached_child_jobs_json))

                    downstream_pipeline = bridge_job['downstream_pipeline']
                    ds_jobs_query = gitlab_api.GET_JOBS.format(gitlab_project, downstream_pipeline['id'])
                    ds_jobs_url = '{0}/{1}'.format(gitlab_host, ds_jobs_query)
                    downstream_jobs = gitlab_api.paginate_query_url(ds_jobs_url)

                    with open(cached_child_jobs_json, 'w') as fd:
                        print('caching {0} in {1}'.format(ds_jobs_url, cached_child_jobs_json))
                        fd.write(json.dumps(downstream_jobs))

                # These are the generated rebuild child jobs
                for rebuild_job in downstream_jobs:
                    name = rebuild_job['name']

                    if name in ignore_keys:
                        continue

                    job_id = rebuild_job['id']
                    runner = 'None'
                    if 'runner' in rebuild_job and rebuild_job['runner']:  # If job was canceled, then runner is null
                        runner = rebuild_job['runner']['description']
                    status = rebuild_job['status']
                    duration = rebuild_job['duration']
                    web_url = rebuild_job['web_url']
                    time_created = rebuild_job['created_at']
                    time_started = rebuild_job['started_at']
                    job_details = generated_jobs[name]
                    job_vars = job_details['variables']

                    # Ignore jobs generated before we stored all the hashes with each job
                    missing_hashes = [h for h in required_hashes if h not in job_vars]
                    if missing_hashes:
                        print(' @@@@ WARNING: job {0} missing hashes: {1}, ignoring'.format(job_id, missing_hashes))
                        continue

                    pkg_name = job_vars['SPACK_JOB_SPEC_PKG_NAME']
                    dag_hash = job_vars['SPACK_JOB_SPEC_DAG_HASH']
                    build_hash = job_vars['SPACK_JOB_SPEC_BUILD_HASH']
                    full_hash = job_vars['SPACK_JOB_SPEC_FULL_HASH']

                    # Insert rebuild details into db
                    db_cursor.execute(
                        "INSERT OR IGNORE INTO builds VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
                        (
                            job_id,
                            name,
                            runner,
                            status,
                            duration,
                            pkg_name,
                            dag_hash,
                            build_hash,
                            full_hash,
                            web_url,
                            time_created,
                            time_started,
                            pipeline_id
                        ))

    finally:
        if db_connection:
            db_connection.commit()
            db_connection.close()

        done_time = datetime.now()
        delta = done_time - start_time
        elapsed_seconds = delta.total_seconds()
        print('Finished in {0} seconds'.format(elapsed_seconds))
