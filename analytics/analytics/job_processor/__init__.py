from datetime import timedelta
import json
import logging
import re

from celery import shared_task
from django.db import transaction
import gitlab
import gitlab.exceptions
from gitlab.v4.objects import ProjectJob
from requests.exceptions import RequestException

from analytics import setup_gitlab_job_sentry_tags
from analytics.core.models.dimensions import JobType
from analytics.core.models.facts import JobFact
from analytics.job_processor.build_timings import create_build_timing_facts
from analytics.job_processor.dimensions import (
    BUILD_STAGE_REGEX,
    create_date_time_dimensions,
    create_gitlab_job_data_dimension,
    create_job_result_dimension,
    create_job_retry_dimension,
    create_node_dimension,
    create_package_dimension,
    create_package_spec_dimension,
    create_runner_dimension,
    create_spack_job_data_dimension,
    get_gitlab_section_timers,
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

logger = logging.getLogger(__name__)


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
    spack_job = create_spack_job_data_dimension(data=job_info.misc, job_input_data=job_input_data)
    gitlab_job_data = create_gitlab_job_data_dimension(
        gljob=gljob, job_input_data=job_input_data, job_trace=job_trace
    )
    job_result = create_job_result_dimension(
        job_input_data=job_input_data, job_trace=job_trace
    )
    job_retry_data = create_job_retry_dimension(job_input_data=job_input_data)

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
    job_id = job_input_data["build_id"]
    existing_job_fact = JobFact.objects.filter(job_id=job_id).first()
    if existing_job_fact is not None:
        return existing_job_fact

    pod_info = job_info.pod or MissingPodInfo()
    node_info = job_info.node or MissingNodeInfo()
    section_timers = get_gitlab_section_timers(job_trace=job_trace)

    # Hasn't been created yet, create and return it
    return JobFact.objects.create(
        job_id=job_id,
        # Foreign Keys
        start_date=start_date,
        start_time=start_time,
        node=node,
        runner=runner,
        package=package,
        spec=spec,
        spack_job_data=spack_job,
        gitlab_job_data=gitlab_job_data,
        job_result=job_result,
        job_retry=job_retry_data,
        # small descriptive data
        name=job_input_data["build_name"],
        pod_name=pod_info.name or "",
        job_url=f"https://gitlab.spack.io/spack/spack-packages/-/jobs/{job_id}",
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
        # Section timer data
        gitlab_clear_worktree=section_timers.get("clear_worktree", 0),
        gitlab_after_script=section_timers.get("after_script", 0),
        gitlab_cleanup_file_variables=section_timers.get("cleanup_file_variables", 0),
        gitlab_download_artifacts=section_timers.get("download_artifacts", 0),
        gitlab_get_sources=section_timers.get("get_sources", 0),
        gitlab_prepare_executor=section_timers.get("prepare_executor", 0),
        gitlab_prepare_script=section_timers.get("prepare_script", 0),
        gitlab_resolve_secrets=section_timers.get("resolve_secrets", 0),
        gitlab_step_script=section_timers.get("step_script", 0),
        gitlab_upload_artifacts_on_failure=section_timers.get(
            "upload_artifacts_on_failure", 0
        ),
        gitlab_upload_artifacts_on_success=section_timers.get(
            "upload_artifacts_on_success", 0
        ),
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

    # In this case, don't bother processing the job, as it likely never started.
    if gl_job.started_at is None:
        logger.info("Build found with no start time. Skipping...")
        return

    job_trace: str = gl_job.trace().decode()  # type: ignore
    with transaction.atomic():
        job = create_job_fact(gl, gl_job, job_input_data, job_trace)

    # Create build timing facts in a separate transaction, in case this fails
    with transaction.atomic():
        if (
            job.job_result.job_type == JobType.BUILD
            and job.job_result.status == "success"
        ):
            create_build_timing_facts(job_fact=job, gljob=gl_job)
