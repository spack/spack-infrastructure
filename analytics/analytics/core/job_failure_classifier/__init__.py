import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import gitlab
import opensearch_dsl
import sentry_sdk
import yaml
from celery import shared_task
from django.conf import settings
from django.db import connections
from opensearchpy import ConnectionTimeout
from requests.exceptions import ReadTimeout
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


@dataclass(frozen=True)
class RetryInfo:
    is_retry: bool
    is_manual_retry: bool
    attempt_number: int
    final_attempt: bool


def _job_retry_data(
    job_id: int, job_name: str, job_commit_id: int, job_failure_reason: str
) -> RetryInfo:
    with connections["gitlab"].cursor() as cursor:
        # the prior attempts for a given job are all jobs with a lower id, the same commit_id, and
        # the same name. the commit_id is the foreign key for the pipeline.
        # it's important to filter for a lower job id in the event that the webhook is delayed or
        # received out of order.
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM ci_builds
            WHERE id < %(job_id)s
            AND commit_id = %(commit_id)s
            AND name = %(job_name)s
            """,
            {"job_id": job_id, "job_name": job_name, "commit_id": job_commit_id},
        )
        attempt_number = cursor.fetchone()[0] + 1

        cursor.execute(
            """
            SELECT bm.config_options->>'retry'
            FROM ci_builds_metadata bm
            WHERE bm.build_id = %(job_id)s
            """,
            {"job_id": job_id},
        )
        job = cursor.fetchone()
        if not job[0]:
            # config_options->>retry should always be defined for non-trigger (aka Ci::Bridge)
            # jobs in spack. this is an edge case where a job in gitlab isn't explicitly
            # configured for retries at all.
            sentry_sdk.capture_message(f"Job {job_id} missing retry configuration.")
            # this is the default retry configuration for gitlab
            # see https://docs.gitlab.com/ee/ci/yaml/#retry
            retry_config = {
                "max": 0,
                "when": ["always"],
            }
        else:
            retry_config = json.loads(job[0])

        retry_max = retry_config["max"]
        retry_reasons = retry_config["when"]
        # final_attempt is defined as an attempt that won't be retried for the retry_reasons
        # or because it's gone beyond the max number of retries.
        retryable_by_reason = (
            "always" in retry_reasons or job_failure_reason in retry_reasons
        )
        retryable_by_number = attempt_number <= retry_max
        final_attempt = not (retryable_by_reason and retryable_by_number)

        return RetryInfo(
            is_retry=attempt_number > 1,
            # manual retries are all retries that are not part of the original job
            is_manual_retry=attempt_number > retry_max + 1,
            attempt_number=attempt_number,
            final_attempt=final_attempt,
        )


def _assign_error_taxonomy(job_input_data: dict[str, Any], job_trace: str):
    if job_input_data["build_status"] != "failed":
        raise ValueError("This function should only be called for failed jobs")

    # Read taxonomy file
    with open(Path(__file__).parent / "taxonomy.yaml") as f:
        taxonomy = yaml.safe_load(f)["taxonomy"]

    error_taxonomy_version = taxonomy["version"]

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

    return job_error_class, error_taxonomy_version


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
    autoretry_for=(ReadTimeoutError, ConnectionTimeout, ReadTimeout),
    retry_backoff=30,
    retry_backoff_max=3600,
    max_retries=10,
    retry_jitter=True,
)
def upload_job_failure_classification(job_input_data_json: str) -> None:
    gl = gitlab.Gitlab(
        settings.GITLAB_ENDPOINT,
        settings.GITLAB_TOKEN,
        retry_transient_errors=True,
        timeout=15,
    )

    # Read input data and extract params
    job_input_data = json.loads(job_input_data_json)

    # Annotate if job has been retried
    try:
        retry_info = _job_retry_data(
            job_id=job_input_data["build_id"],
            job_name=job_input_data["build_name"],
            job_commit_id=job_input_data["commit"]["id"],
            job_failure_reason=job_input_data["build_failure_reason"],
        )
        job_input_data.update(asdict(retry_info))
    except Exception:
        sentry_sdk.capture_exception()

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
    error_taxonomy, error_taxonomy_version = _assign_error_taxonomy(
        job_input_data, job_trace
    )
    job_input_data["error_taxonomy"] = error_taxonomy
    job_input_data["error_taxonomy_version"] = error_taxonomy_version

    opensearch_dsl.connections.create_connection(
        hosts=[settings.OPENSEARCH_ENDPOINT],
        http_auth=(
            settings.OPENSEARCH_USERNAME,
            settings.OPENSEARCH_PASSWORD,
        ),
    )
    doc = JobPayload(**job_input_data)
    doc.save()
