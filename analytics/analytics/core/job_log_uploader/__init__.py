import json
import re
from dataclasses import asdict
from datetime import datetime
from typing import Any

import gitlab
from celery import shared_task
from dateutil.parser import isoparse
from django.conf import settings
from gitlab.v4.objects import Project, ProjectJob
from opensearch_dsl import Date, Document, connections
from opensearchpy import ConnectionTimeout
from urllib3.exceptions import ReadTimeoutError

from analytics import setup_gitlab_job_sentry_tags
from analytics.core.job_failure_classifier import (
    _assign_error_taxonomy,
    _job_retry_data,
)
from analytics.core.models.legacy import LegacyJobAttempt


class JobLog(Document):
    timestamp = Date()

    class Index:
        name = "gitlab-job-logs-*"

    def save(self, **kwargs):
        # assign now if no timestamp given
        if not self.timestamp:
            self.timestamp = datetime.utcnow()

        # override the index to go to the proper timeslot
        kwargs["index"] = self.timestamp.strftime("gitlab-job-logs-%Y%m%d")
        return super().save(**kwargs)


def _get_section_timers(job_trace: str) -> dict[str, int]:
    timers: dict[str, int] = {}

    # See https://docs.gitlab.com/ee/ci/jobs/index.html#custom-collapsible-sections for the format
    # of section names.
    r = re.findall(r"section_(start|end):(\d+):([A-Za-z0-9_\-\.]+)", job_trace)
    for start, end in zip(r[::2], r[1::2]):
        timers[start[2]] = int(end[1]) - int(start[1])

    return timers


def _create_job_attempt(
    project: Project,
    gl_job: ProjectJob,
    webhook_payload: dict[str, Any],
    job_trace: str,
) -> LegacyJobAttempt:
    retry_info = _job_retry_data(
        job_id=gl_job.get_id(),
        job_name=gl_job.name,
        job_commit_id=webhook_payload["commit"]["id"],
        job_failure_reason=webhook_payload["build_failure_reason"],
    )

    section_timers = _get_section_timers(job_trace)
    error_taxonomy = (
        _assign_error_taxonomy(webhook_payload, job_trace)[0]
        if webhook_payload["build_status"] == "failed"
        else None
    )

    return LegacyJobAttempt.objects.create(
        job_id=gl_job.get_id(),
        project_id=project.get_id(),
        commit_id=webhook_payload["commit"]["id"],
        name=gl_job.name,
        started_at=isoparse(gl_job.started_at),
        finished_at=isoparse(gl_job.finished_at),
        ref=gl_job.ref,
        is_retry=retry_info.is_retry,
        is_manual_retry=retry_info.is_manual_retry,
        attempt_number=retry_info.attempt_number,
        final_attempt=retry_info.final_attempt,
        status=webhook_payload["build_status"],
        error_taxonomy=error_taxonomy,
        section_timers=section_timers,
    )


@shared_task(
    name="store_job_data",
    soft_time_limit=60,
    autoretry_for=(ReadTimeoutError, ConnectionTimeout),
    retry_backoff=30,
    retry_backoff_max=3600,
    max_retries=10,
    retry_jitter=True,
)
def store_job_data(job_input_data_json: str) -> None:
    job_input_data: dict[str, Any] = json.loads(job_input_data_json)
    setup_gitlab_job_sentry_tags(job_input_data)

    gl = gitlab.Gitlab(
        settings.GITLAB_ENDPOINT, settings.GITLAB_TOKEN, retry_transient_errors=True
    )

    # Retrieve project and job from gitlab API
    project = gl.projects.get(job_input_data["project_id"])
    job = project.jobs.get(job_input_data["build_id"])
    job_trace: str = job.trace().decode()

    retry_info = _job_retry_data(
        job_id=job_input_data["build_id"],
        job_name=job_input_data["build_name"],
        job_commit_id=job_input_data["commit"]["id"],
        job_failure_reason=job_input_data["build_failure_reason"],
    )
    job_input_data.update(asdict(retry_info))

    # Remove ANSI escape sequences from colorized output
    # TODO: this still leaves trailing ;m in the output
    job_trace = re.sub(
        r"\x1b\[([0-9,A-Z]{1,2}(;[0-9]{1,2})?(;[0-9]{3})?)?[m|G|K]?", "", job_trace
    )

    connections.create_connection(
        hosts=[settings.OPENSEARCH_ENDPOINT],
        http_auth=(
            settings.OPENSEARCH_USERNAME,
            settings.OPENSEARCH_PASSWORD,
        ),
    )

    doc = JobLog(
        **job_input_data,
        job_url=f'{job_input_data["project"]["web_url"]}/-/jobs/{job_input_data["build_id"]}',
        job_trace=job_trace,
    )
    doc.save()

    _create_job_attempt(project, job, job_input_data, job_trace)
