import json
from datetime import timedelta

import gitlab
import gitlab.exceptions
from celery import shared_task
from django.conf import settings
from django.db import transaction
from gitlab.v4.objects import ProjectJob
from requests.exceptions import ReadTimeout

from analytics import setup_gitlab_job_sentry_tags
from analytics.core.models.facts import JobFact
from analytics.job_processor.artifacts import JobArtifactFileNotFound
from analytics.job_processor.build_timings import create_build_timing_facts
from analytics.job_processor.dimensions import (
    create_date_time_dimensions,
    create_job_data_dimension,
    create_node_dimension,
    create_package_dimension,
    create_package_spec_dimension,
    create_runner_dimension,
)
from analytics.job_processor.metadata import (
    ClusterJobInfo,
    JobInfo,
    NonClusterJobInfo,
    retrieve_job_info,
)


def calculate_job_cost(info: JobInfo, duration: float) -> float | None:
    if isinstance(info, NonClusterJobInfo):
        return None

    return duration * info.pod.node_occupancy * (float(info.node.spot_price) / 3600)


def create_job_fact(
    gl: gitlab.Gitlab,
    gljob: ProjectJob,
    job_input_data: dict,
    job_trace: str,
) -> JobFact:
    job_info = retrieve_job_info(gljob=gljob)

    start_date, start_time = create_date_time_dimensions(gljob=gljob)
    job_data = create_job_data_dimension(
        job_input_data=job_input_data,
        job_info=job_info,
        gljob=gljob,
        job_trace=job_trace,
    )

    node = create_node_dimension(job_info.node)
    runner = create_runner_dimension(gl=gl, gljob=gljob)
    package = create_package_dimension(job_info.package)
    spec = create_package_spec_dimension(job_info.package)

    # Now that we have all the dimensions, we need to calculate any derived fields
    job_cost = calculate_job_cost(info=job_info, duration=gljob.duration)
    node_price_per_second = (
        job_info.node.spot_price / 3600
        if isinstance(job_info, ClusterJobInfo)
        else None
    )

    # Check that this fact hasn't already been created. If it has, return that value
    # A fact table is unique to it's foreign keys
    existing_job_fact = JobFact.objects.filter(
        start_date=start_date,
        start_time=start_time,
        node=node,
        runner=runner,
        package=package,
        spec=spec,
        job=job_data,
    ).first()
    if existing_job_fact is not None:
        return existing_job_fact

    # Hasn't been created yet, create and return it
    return JobFact.objects.create(
        # Foreign Keys
        start_date=start_date,
        start_time=start_time,
        node=node,
        runner=runner,
        package=package,
        spec=spec,
        job=job_data,
        # numeric
        duration=timedelta(seconds=gljob.duration),
        duration_seconds=gljob.duration,
        # Will be null on non-cluster jobs
        cost=job_cost,
        pod_node_occupancy=job_info.pod.node_occupancy,
        pod_cpu_usage_seconds=job_info.pod.cpu_usage_seconds,
        pod_max_mem=job_info.pod.max_memory,
        pod_avg_mem=job_info.pod.avg_memory,
        node_price_per_second=node_price_per_second,
        node_cpu=job_info.node.cpu,
        node_memory=job_info.node.memory,
        # Can be null on any job
        build_jobs=job_info.misc.build_jobs,
        pod_cpu_request=job_info.pod.cpu_request,
        pod_cpu_limit=job_info.pod.cpu_limit,
        pod_memory_request=job_info.pod.memory_request,
        pod_memory_limit=job_info.pod.memory_limit,
    )


@shared_task(
    name="process_job",
    autoretry_for=(ReadTimeout,),
    max_retries=3,
)
def process_job(job_input_data_json: str):
    # Read input data and extract params
    job_input_data = json.loads(job_input_data_json)
    setup_gitlab_job_sentry_tags(job_input_data)

    # Retrieve project and job from gitlab API
    # TODO: Seems to be very slow and sometimes times out. Look into using shared session?
    gl = gitlab.Gitlab(
        settings.GITLAB_ENDPOINT,
        settings.GITLAB_TOKEN,
        retry_transient_errors=True,
        timeout=15,
    )
    gl_project = gl.projects.get(job_input_data["project_id"])
    gl_job = gl_project.jobs.get(job_input_data["build_id"])
    job_trace: str = gl_job.trace().decode()  # type: ignore

    with transaction.atomic():
        try:
            job = create_job_fact(gl, gl_job, job_input_data, job_trace)
            create_build_timing_facts(job_fact=job, gljob=gl_job)
        except JobArtifactFileNotFound:
            # If the job has a status of "failed", some artifacts might
            # not be present, so don't error if that's the case
            if job_input_data["build_status"] == "failed":
                return

            raise
