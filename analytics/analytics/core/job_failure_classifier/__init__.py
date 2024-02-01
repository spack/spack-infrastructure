from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any

from celery import shared_task
from django.conf import settings
from django.db import connections
import gitlab
import opensearch_dsl
import yaml
from opensearchpy import ConnectionTimeout
from urllib3.exceptions import ReadTimeoutError


class JobPayload(opensearch_dsl.Document):
    timestamp = opensearch_dsl.Date()

    class Index:
        name = "gitlab-job-failures-*"

    def save(self, **kwargs):
        # assign now if no timestamp given
        if not self.timestamp:
            self.timestamp = datetime.now()

        # override the index to go to the proper timeslot
        kwargs["index"] = self.timestamp.strftime("gitlab-job-failures-%Y%m%d")
        return super().save(**kwargs)


def _job_retry_data(job_id: str | int, job_name: str) -> tuple[int, bool]:
    with connections["gitlab"].cursor() as cursor:
        cursor.execute(
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
        result = cursor.fetchone()
        cursor.close()

    return result


def _assign_error_taxonomy(job_input_data: dict[str, Any], job_trace: str):
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


def _collect_pod_status(job_input_data: dict[str, Any], job_trace: str):
    """Collect k8s info about this job and store it in the OpenSearch record"""
    # Record whether this job was run on a kubernetes pod or via some other
    # means (a UO runner, for example)
    job_input_data["kubernetes_job"] = "Using Kubernetes executor" in job_trace

    # If this job wasn't run on kubernetes, there's no pod to fetch so
    # we can exit early
    if not job_input_data["kubernetes_job"]:
        return

    # Jobs sometimes don't have a `runner` field if the job failed due
    # to a runner system failure.
    # In some cases they *do* have a `runner` field, but it is None.
    if job_input_data.get("runner") is None:
        return

    # Scan job logs to infer the name of the pod this job was executed on
    runner_name_matches = re.findall(
        rf"Running on (.+) via {job_input_data['runner']['description']}...",
        job_trace,
    )
    if not len(runner_name_matches):
        job_input_data["pod_status"] = None
        return


@shared_task(
    name="upload_job_failure_classification",
    soft_time_limit=60,
    autoretry_for=(ReadTimeoutError, ConnectionTimeout),
    retry_backoff=5,
    max_retries=5,
)
def upload_job_failure_classification(job_input_data_json: str) -> None:
    gl = gitlab.Gitlab(settings.GITLAB_ENDPOINT, settings.GITLAB_TOKEN, retry_transient_errors=True)

    # Read input data and extract params
    job_input_data = json.loads(job_input_data_json)
    job_id = job_input_data["build_id"]
    job_name = job_input_data["build_name"]

    # Annotate if job has been retried
    attempt_number, retried = _job_retry_data(job_id=job_id, job_name=job_name)
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
    _collect_pod_status(job_input_data, job_trace)

    # Assign any/all relevant errors
    _assign_error_taxonomy(job_input_data, job_trace)

    opensearch_dsl.connections.create_connection(
        hosts=[settings.OPENSEARCH_ENDPOINT],
        http_auth=(
            settings.OPENSEARCH_USERNAME,
            settings.OPENSEARCH_PASSWORD,
        ),
    )
    doc = JobPayload(**job_input_data)
    doc.save()
