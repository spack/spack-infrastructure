import json
import re
import uuid
from dataclasses import dataclass
from datetime import timedelta

import gitlab
from celery import shared_task
from dateutil.parser import isoparse
from django.conf import settings
from django.db import transaction
from gitlab.v4.objects import ProjectJob

from analytics import setup_gitlab_job_sentry_tags
from analytics.core.job_failure_classifier import (
    _assign_error_taxonomy,
    _job_retry_data,
)
from analytics.core.models.dimensions import (
    DateDimension,
    JobDataDimension,
    NodeDimension,
    PackageDimension,
    RunnerDimension,
    TimeDimension,
)
from analytics.core.models.facts import JobFact
from analytics.job_processor.build_timings import create_build_timing_facts
from analytics.job_processor.metadata import (
    ClusterJobInfo,
    JobInfo,
    MissingNodeInfo,
    NodeInfo,
    NonClusterJobInfo,
    PackageInfo,
    retrieve_job_info,
)

UNNECESSARY_JOB_REGEX = re.compile(r"No need to rebuild [^,]+, found hash match")


def create_job_data_dimension(
    job_input_data: dict,
    job_info: JobInfo,
    gljob: ProjectJob,
    job_trace: str,
) -> JobDataDimension:
    job_id = job_input_data["build_id"]
    existing_job = JobDataDimension.objects.filter(job_id=job_id).first()
    if existing_job is not None:
        return existing_job

    job_name = job_input_data["build_name"]
    job_commit_id = job_input_data["commit"]["id"]
    job_failure_reason = job_input_data["build_failure_reason"]
    retry_info = _job_retry_data(
        job_id=job_id,
        job_name=job_name,
        job_commit_id=job_commit_id,
        job_failure_reason=job_failure_reason,
    )

    error_taxonomy = (
        _assign_error_taxonomy(job_input_data, job_trace)[0]
        if job_input_data["build_status"] == "failed"
        else None
    )

    job_data = JobDataDimension.objects.create(
        job_id=job_id,
        commit_id=job_commit_id,
        job_url=f"https://gitlab.spack.io/spack/spack/-/jobs/{job_id}",
        name=job_name,
        ref=gljob.ref,
        tags=gljob.tag_list,
        job_size=job_info.misc.job_size,
        stack=job_info.misc.stack,
        # Retry info
        is_retry=retry_info.is_retry,
        is_manual_retry=retry_info.is_manual_retry,
        attempt_number=retry_info.attempt_number,
        final_attempt=retry_info.final_attempt,
        status=job_input_data["build_status"],
        error_taxonomy=error_taxonomy,
        unnecessary=UNNECESSARY_JOB_REGEX.search(job_trace) is not None,
        pod_name=job_info.pod.name,
        # TODO: Once this info is available, update this
        gitlab_runner_version="",
        # TODO: Once this is also used to process failed jobs, change this
        is_build=True,
    )

    return job_data


@dataclass
class JobFactDimensions:
    """Refers to the primary keys of the dimensions that have been created for a job fact."""

    start_date: int
    start_time: int
    end_date: int
    end_time: int

    job_data: int
    node: uuid.UUID
    runner: int
    package: int


def create_date_time_dimensions(
    gljob: ProjectJob
) -> tuple[DateDimension, TimeDimension, DateDimension, TimeDimension]:
    start_date = DateDimension.ensure_exists(gljob.started_at)
    start_time = TimeDimension.ensure_exists(gljob.started_at)

    finished_at = isoparse(gljob.started_at) + timedelta(seconds=gljob.duration)
    end_date = DateDimension.ensure_exists(finished_at)
    end_time = TimeDimension.ensure_exists(finished_at)

    return (start_date, start_time, end_date, end_time)


def create_node_dimension(info: NodeInfo | MissingNodeInfo) -> NodeDimension:
    if isinstance(info, MissingNodeInfo):
        return NodeDimension.objects.get(name="")

    node, _ = NodeDimension.objects.get_or_create(
        system_uuid=info.system_uuid,
        name=info.name,
        cpu=info.cpu,
        memory=info.memory,
        capacity_type=info.capacity_type,
        instance_type=info.instance_type,
    )

    return node


# Since this isn't info that we currently collect, just return the empty runner here
# TODO: Add this info
def create_runner_dimension() -> RunnerDimension:
    return RunnerDimension.objects.get(name="")


def create_package_dimension(info: PackageInfo) -> PackageDimension:
    package, _ = PackageDimension.objects.get_or_create(
        name=info.name,
        version=info.version,
        compiler_name=info.compiler_name,
        compiler_version=info.compiler_version,
        arch=info.arch,
        variants=info.variants,
    )

    return package


def calculate_job_cost(info: JobInfo, duration: float) -> float | None:
    if isinstance(info, NonClusterJobInfo):
        return None

    return duration * info.pod.node_occupancy * (float(info.node.spot_price) / 3600)


def create_job_fact(
    gljob: ProjectJob,
    job_input_data: dict,
    job_trace: str,
) -> JobFact:
    job_info = retrieve_job_info(gljob=gljob)
    start_date, start_time, end_date, end_time = create_date_time_dimensions(
        gljob=gljob
    )

    job_data = create_job_data_dimension(
        job_input_data=job_input_data,
        job_info=job_info,
        gljob=gljob,
        job_trace=job_trace,
    )

    node = create_node_dimension(job_info.node)
    runner = create_runner_dimension()
    package = create_package_dimension(job_info.package)

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
        end_date=end_date,
        end_time=end_time,
        node=node,
        runner=runner,
        package=package,
        job=job_data,
    ).first()
    if existing_job_fact is not None:
        return existing_job_fact

    # Hasn't been created yet, create and return it
    return JobFact.objects.create(
        # Foreign Keys
        start_date=start_date,
        start_time=start_time,
        end_date=end_date,
        end_time=end_time,
        node=node,
        runner=runner,
        package=package,
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


@shared_task(name="process_job")
def process_job(job_input_data_json: str):
    # Read input data and extract params
    job_input_data = json.loads(job_input_data_json)
    setup_gitlab_job_sentry_tags(job_input_data)

    # Retrieve project and job from gitlab API
    gl = gitlab.Gitlab(
        settings.GITLAB_ENDPOINT, settings.GITLAB_TOKEN, retry_transient_errors=True
    )
    gl_project = gl.projects.get(job_input_data["project_id"])
    gl_job = gl_project.jobs.get(job_input_data["build_id"])
    job_trace: str = gl_job.trace().decode()  # type: ignore

    # Use a transaction, to account for transient failures
    with transaction.atomic():
        job = create_job_fact(gl_job, job_input_data, job_trace)
        create_build_timing_facts(job_fact=job, gljob=gl_job)
