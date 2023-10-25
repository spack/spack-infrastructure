import json
import os
import re
from datetime import datetime
from pathlib import Path
from time import sleep
from typing import Any

import gitlab
import psycopg2
import sentry_sdk
import yaml
from kubernetes import client, config
from kubernetes.client.exceptions import ApiException
from kubernetes.client.models.v1_pod import V1Pod
from kubernetes.client.models.v1_pod_status import V1PodStatus
from opensearch_dsl import Date, Document, connections


sentry_sdk.init(
    # Sample only 1% of jobs
    traces_sample_rate=0.01,
)

config.load_config()
v1_client = client.CoreV1Api()


class JobPayload(Document):
    timestamp = Date()

    class Index:
        name = "gitlab-job-failures-*"

    def save(self, **kwargs):
        # assign now if no timestamp given
        if not self.timestamp:
            self.timestamp = datetime.now()

        # override the index to go to the proper timeslot
        kwargs["index"] = self.timestamp.strftime("gitlab-job-failures-%Y%m%d")
        return super().save(**kwargs)


GITLAB_TOKEN = os.environ["GITLAB_TOKEN"]
GITLAB_POSTGRES_DB = os.environ["GITLAB_POSTGRES_DB"]
GITLAB_POSTGRES_USER = os.environ["GITLAB_POSTGRES_RO_USER"]
GITLAB_POSTGRES_PASSWORD = os.environ["GITLAB_POSTGRES_RO_PASSWORD"]
GITLAB_POSTGRES_HOST = os.environ["GITLAB_POSTGRES_HOST"]

OPENSEARCH_ENDPOINT = os.environ["OPENSEARCH_ENDPOINT"]
OPENSEARCH_USERNAME = os.environ["OPENSEARCH_USERNAME"]
OPENSEARCH_PASSWORD = os.environ["OPENSEARCH_PASSWORD"]


# Instantiate gitlab api wrapper
gl = gitlab.Gitlab("https://gitlab.spack.io", GITLAB_TOKEN)

# Instantiate postgres connection
pg_conn = psycopg2.connect(
    host=GITLAB_POSTGRES_HOST,
    port="5432",
    dbname=GITLAB_POSTGRES_DB,
    user=GITLAB_POSTGRES_USER,
    password=GITLAB_POSTGRES_PASSWORD,
)


def job_retry_data(job_id: str | int, job_name: str) -> tuple[int, bool]:
    with pg_conn:
        cur = pg_conn.cursor()
        cur.execute(
            """
            SELECT attempt_number, COALESCE(retried, FALSE) as retried FROM (
                SELECT ROW_NUMBER() OVER (ORDER BY id) as attempt_number, retried, id
                FROM ci_builds
                WHERE
                    ci_builds.name = %(job_name)s
                    and ci_builds.stage_id = (
                        SELECT stage_id from ci_builds WHERE id = %(job_id)s LIMIT 1
                    )
                    and ci_builds.status = 'failed'
            ) as build_attempts
            WHERE build_attempts.id = %(job_id)s
            ;
            """,
            {"job_id": job_id, "job_name": job_name},
        )
        result = cur.fetchone()
        cur.close()

    return result


def assign_error_taxonomy(job_input_data: dict[str, Any], job_trace: str):
    # Read taxonomy file
    with open(Path(__file__).parent / "taxonomy.yaml") as f:
        taxonomy = yaml.safe_load(f)["taxonomy"]
    job_input_data["error_taxonomy_version"] = taxonomy["version"]

    # Compile matching patterns from job trace
    matching_patterns = set()
    for error_class, lookups in taxonomy["error_classes"].items():
        if lookups:
            for grep_expr in lookups.get("grep_for", []):
                if re.compile(grep_expr).search(job_trace):
                    matching_patterns.add(error_class)

    # If the job logs matched any regexes, assign it the taxonomy
    # with the highest priority in the "deconflict order".
    # Otherwise, assign it a taxonomy of "other".
    job_error_class = None
    if len(matching_patterns):
        for error_class in taxonomy["deconflict_order"]:
            if error_class in matching_patterns:
                job_error_class = error_class
                break
    else:
        job_error_class = "other"

        # If this job timed out or failed to be scheduled by GitLab,
        # label it as such.
        if job_input_data["build_failure_reason"] in (
            "stuck_or_timeout_failure",
            "scheduler_failure",
        ):
            job_error_class = job_input_data["build_failure_reason"]

    job_input_data["error_taxonomy"] = job_error_class
    return


def collect_pod_status(job_input_data: dict[str, Any], job_trace: str):
    """Collect k8s info about this job and store it in the OpenSearch record"""
    # Record whether this job was run on a kubernetes pod or via some other
    # means (a UO runner, for example)
    job_input_data["kubernetes_job"] = "Using Kubernetes executor" in job_trace

    # If this job wasn't run on kubernetes, there's no pod to fetch so
    # we can exit early
    if not job_input_data["kubernetes_job"]:
        return

    # Jobs sometimes don't have a `runner` field if the job failed du
    # to a runner system failure
    if 'runner' not in job_input_data:
        return

    # Scan job logs to infer the name of the pod this job was executed on
    runner_name_matches = re.findall(
        rf"Running on (.+) via {job_input_data['runner']['description']}...",
        job_trace,
    )
    if not len(runner_name_matches):
        job_input_data["pod_status"] = None
        return

    pod_name = runner_name_matches[0]

    pod: V1Pod | None = None
    while True:
        # Try to fetch pod with kube
        try:
            pod = v1_client.read_namespaced_pod(name=pod_name, namespace="pipeline")
        except ApiException:
            # If it doesn't work, that means the pod has already been cleaned up.
            # In that case, we break out of the loop and return.
            break

        # Check if the pod is still running. If so, keep re-fetching it until it's complete
        status: V1PodStatus = pod.status
        if status.phase != "Running":
            break

        sleep(1)

    if pod:
        job_input_data["pod_status"] = pod.status.to_dict()


def main():
    # Read input data and extract params
    job_input_data = json.loads(os.environ["JOB_INPUT_DATA"])
    job_id = job_input_data["build_id"]
    job_name = job_input_data["build_name"]

    # Annotate if job has been retried
    attempt_number, retried = job_retry_data(job_id=job_id, job_name=job_name)
    job_input_data["attempt_number"] = attempt_number
    job_input_data["retried"] = retried

    # Convert all string timestamps in webhook payload to `datetime` objects
    for key, val in job_input_data.items():
        try:
            if isinstance(val, str):
                job_input_data[key] = datetime.strptime(val, "%Y-%m-%d %H:%M:%S %Z")
        except ValueError:
            continue

    # Retrieve project and job from gitlab API
    project = gl.projects.get(job_input_data["project_id"])
    job = project.jobs.get(job_input_data["build_id"])
    job_trace: str = job.trace().decode()  # type: ignore

    # Get info about the k8s pod this job ran on
    collect_pod_status(job_input_data, job_trace)

    # Assign any/all relevant errors
    assign_error_taxonomy(job_input_data, job_trace)

    # Upload to OpenSearch
    connections.create_connection(
        hosts=[OPENSEARCH_ENDPOINT],
        http_auth=(
            OPENSEARCH_USERNAME,
            OPENSEARCH_PASSWORD,
        ),
    )
    doc = JobPayload(**job_input_data)
    doc.save()


if __name__ == "__main__":
    main()
