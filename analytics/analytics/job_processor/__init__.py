import json
from datetime import timedelta

import gitlab
import sentry_sdk
from celery import shared_task
from dateutil.parser import isoparse
from django.conf import settings
from gitlab.v4.objects import Project, ProjectJob

from analytics import setup_gitlab_job_sentry_tags
from analytics.job_processor.artifacts import annotate_job_with_artifacts_data
from analytics.job_processor.build_timings import create_build_timings
from analytics.job_processor.prometheus import (
    JobPrometheusDataNotFound,
    PrometheusClient,
)
from analytics.models import Job


def create_job(gl: gitlab.Gitlab, project: Project, gljob: ProjectJob) -> Job:
    # Create base fields on job that are independent of where it ran
    job = Job(
        job_id=gljob.get_id(),
        project_id=project.get_id(),
        name=gljob.name,
        started_at=isoparse(gljob.started_at),
        duration=timedelta(seconds=gljob.duration),
        ref=gljob.ref,
        tags=gljob.tag_list,
        aws=True,  # Default until proven otherwise
    )

    # Prometheus data will either be found and the job annotated, or not, and set aws to False
    try:
        PrometheusClient(settings.SPACK_PROMETHEUS_ENDPOINT).annotate_job(job=job)

        # Save job pod, and node if necessary
        job.pod.save()
        if job.node.pk is None:
            job.node.save()
    except JobPrometheusDataNotFound:
        job.aws = False
        annotate_job_with_artifacts_data(gljob=gljob, job=job)

    # Save and return new job
    job.save()
    return job


@shared_task(name="process_job")
def process_job(job_input_data_json: str):
    # Read input data and extract params
    job_input_data = json.loads(job_input_data_json)
    setup_gitlab_job_sentry_tags(job_input_data)

    # Retrieve project and job from gitlab API
    gl = gitlab.Gitlab(settings.GITLAB_ENDPOINT, settings.GITLAB_TOKEN)
    gl_project = gl.projects.get(job_input_data["project_id"])
    gl_job = gl_project.jobs.get(job_input_data["build_id"])

    # Get or create job record
    job = create_job(gl, gl_project, gl_job)
    create_build_timings(job, gl_job)
