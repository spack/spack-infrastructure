import json
import re
from datetime import timedelta

import gitlab
import gitlab.exceptions
from celery import shared_task
from django.db import transaction
from gitlab.v4.objects import ProjectJob
from requests.exceptions import RequestException

from analytics import setup_gitlab_job_sentry_tags
from analytics.core.models.dimensions import JobDataDimension
from analytics.core.models.facts import JobFact
from analytics.job_processor.build_timings import create_build_timing_facts
from analytics.job_processor.dimensions import (
    BUILD_STAGE_REGEX,
    create_date_time_dimensions,
    create_job_data_dimension,
    create_node_dimension,
    create_package_dimension,
    create_package_spec_dimension,
    create_runner_dimension,
)
from analytics.job_processor.metadata import (
    JobInfo,
    MissingNodeInfo,
    MissingPodInfo,
    retrieve_job_info,
)
from analytics.job_processor.utils import (
    get_gitlab_handle,
    get_gitlab_job,
    get_gitlab_project,
)


def calculate_job_cost(info: JobInfo, duration: float) -> float | None:
    if info.node is None or info.pod is None:
        return None

    return duration * info.pod.node_occupancy * (float(info.node.spot_price) / 3600)


def create_job_fact(
    gl: gitlab.Gitlab,
    gljob: ProjectJob,
    job_input_data: dict,
    job_trace: str,
) -> JobFact:
    is_build = re.match(BUILD_STAGE_REGEX, job_input_data["build_stage"]) is not None
    job_info = retrieve_job_info(gljob=gljob, is_build=is_build)

    start_date, start_time = create_date_time_dimensions(gljob=gljob)
    job_data = create_job_data_dimension(
        job_input_data=job_input_data,
        pod_info=job_info.pod,
        misc_info=job_info.misc,
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
        job_info.node.spot_price / 3600 if job_info.node is not None else None
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

    pod_info = job_info.pod or MissingPodInfo()
    node_info = job_info.node or MissingNodeInfo()

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
        pod_node_occupancy=pod_info.node_occupancy,
        pod_cpu_usage_seconds=pod_info.cpu_usage_seconds,
        pod_max_mem=pod_info.max_memory,
        pod_avg_mem=pod_info.avg_memory,
        node_price_per_second=node_price_per_second,
        node_cpu=node_info.cpu,
        node_memory=node_info.memory,
        # Can be null on any job
        build_jobs=job_info.misc.build_jobs if job_info.misc else None,
        pod_cpu_request=pod_info.cpu_request,
        pod_cpu_limit=pod_info.cpu_limit,
        pod_memory_request=pod_info.memory_request,
        pod_memory_limit=pod_info.memory_limit,
    )


@shared_task(
    name="process_job",
    autoretry_for=(RequestException,),
    max_retries=3,
)
def process_job(job_input_data_json: str):
    # Read input data and extract params
    job_input_data = json.loads(job_input_data_json)
    setup_gitlab_job_sentry_tags(job_input_data)

    # Retrieve project and job from gitlab API
    gl = get_gitlab_handle()
    gl_project = get_gitlab_project(job_input_data["project_id"])
    gl_job = get_gitlab_job(gl_project, job_input_data["build_id"])
    job_trace: str = gl_job.trace().decode()  # type: ignore

    with transaction.atomic():
        job = create_job_fact(gl, gl_job, job_input_data, job_trace)

    # Create build timing facts in a separate transaction, in case this fails
    with transaction.atomic():
        if job.job.job_type == JobDataDimension.JobType.BUILD:
            create_build_timing_facts(job_fact=job, gljob=gl_job)
