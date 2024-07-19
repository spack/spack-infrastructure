import re

import gitlab
import gitlab.exceptions
from gitlab.v4.objects import ProjectJob

from analytics.core.job_failure_classifier import (
    _assign_error_taxonomy,
    _job_retry_data,
)
from analytics.core.models.dimensions import (
    DateDimension,
    JobDataDimension,
    NodeDimension,
    PackageDimension,
    PackageSpecDimension,
    RunnerDimension,
    TimeDimension,
)
from analytics.job_processor.metadata import (
    JobInfo,
    MissingNodeInfo,
    NodeInfo,
    PackageInfo,
)

UNNECESSARY_JOB_REGEX = re.compile(r"No need to rebuild [^,]+, found hash match")
BUILD_STAGE_REGEX = r"^stage-\d+$"


def get_gitlab_section_timers(job_trace: str) -> dict[str, int]:
    timers: dict[str, int] = {}

    # See https://docs.gitlab.com/ee/ci/jobs/index.html#custom-collapsible-sections for the format
    # of section names.
    r = re.findall(r"section_(start|end):(\d+):([A-Za-z0-9_\-\.]+)", job_trace)
    for start, end in zip(r[::2], r[1::2]):
        timers[start[2]] = int(end[1]) - int(start[1])

    return timers


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

    job_status = job_input_data["build_status"]
    error_taxonomy = (
        _assign_error_taxonomy(job_input_data, job_trace)[0]
        if job_status == "failed"
        else None
    )

    gitlab_section_timers = get_gitlab_section_timers(job_trace=job_trace)

    rvmatch = re.search(r"Running with gitlab-runner (\d+\.\d+\.\d+)", job_trace)
    runner_version = rvmatch.group(1) if rvmatch is not None else ""
    unnecessary = UNNECESSARY_JOB_REGEX.search(job_trace) is not None
    is_build = re.match(BUILD_STAGE_REGEX, job_input_data["build_stage"])

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
        status=job_status,
        error_taxonomy=error_taxonomy,
        unnecessary=unnecessary,
        pod_name=job_info.pod.name,
        gitlab_runner_version=runner_version,
        is_build=is_build,
        gitlab_section_timers=gitlab_section_timers,
    )

    return job_data


def create_date_time_dimensions(
    gljob: ProjectJob,
) -> tuple[DateDimension, TimeDimension]:
    start_date = DateDimension.ensure_exists(gljob.started_at)
    start_time = TimeDimension.ensure_exists(gljob.started_at)

    return (start_date, start_time)


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


def create_runner_dimension(gl: gitlab.Gitlab, gljob: ProjectJob) -> RunnerDimension:
    empty_runner = RunnerDimension.objects.get(name="")

    _runner: dict | None = getattr(gljob, "runner", None)
    if _runner is None:
        return empty_runner

    runner_id = _runner["id"]
    existing_runner = RunnerDimension.objects.filter(runner_id=runner_id).first()
    if existing_runner is not None:
        return existing_runner

    # Attempt to fetch this runner from gitlab
    try:
        runner = gl.runners.get(runner_id)
    except gitlab.exceptions.GitlabGetError as e:
        if e.response_code != 404:
            raise

        return empty_runner

    in_cluster = False
    host = "unknown"
    runner_name: str = runner.description

    if runner_name.startswith("uo-"):
        host = "uo"
    if runner_name.startswith("runner-"):
        host = "cluster"
        in_cluster = True

    # Create and return new runner
    return RunnerDimension.objects.create(
        runner_id=runner_id,
        name=runner_name,
        platform=runner.platform,
        host=host,
        arch=runner.architecture,
        tags=runner.tag_list,
        in_cluster=in_cluster,
    )


def create_package_dimension(info: PackageInfo) -> PackageDimension:
    package, _ = PackageDimension.objects.get_or_create(name=info.name)
    return package


def create_package_spec_dimension(info: PackageInfo) -> PackageSpecDimension:
    package, _ = PackageSpecDimension.objects.get_or_create(
        hash=info.hash,
        name=info.name,
        version=info.version,
        compiler_name=info.compiler_name,
        compiler_version=info.compiler_version,
        arch=info.arch,
        variants=info.variants,
    )

    return package
