import re
from pathlib import Path
from typing import Any

import gitlab
import gitlab.exceptions
import yaml
from gitlab.v4.objects import ProjectJob

from analytics.core.models.dimensions import (
    DateDimension,
    GitlabJobDataDimension,
    JobResultDimension,
    JobRetryDimension,
    JobType,
    NodeDimension,
    PackageDimension,
    PackageSpecDimension,
    RunnerDimension,
    SpackJobDataDimension,
    TimeDimension,
)
from analytics.job_processor.metadata import JobMiscInfo, NodeInfo, PackageInfo
from analytics.job_processor.utils import get_job_exit_code, get_job_retry_data

UNNECESSARY_JOB_REGEX = re.compile(r"No need to rebuild [^,]+, found hash match")
BUILD_STAGE_REGEX = r"^stage-\d+$"


class UnrecognizedJobType(Exception):
    def __init__(self, job_id: int, name: str) -> None:
        message = f"Unrecognized job type for Job: ({job_id}) {name}"
        super().__init__(message)


def _assign_error_taxonomy(job_input_data: dict[str, Any], job_trace: str):
    if job_input_data["build_status"] != "failed":
        raise ValueError("This function should only be called for failed jobs")

    # Read taxonomy file
    with open(Path(__file__).parent / "error_taxonomy.yaml") as f:
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


def get_gitlab_section_timers(job_trace: str) -> dict[str, int]:
    timers: dict[str, int] = {}

    # See https://docs.gitlab.com/ee/ci/jobs/index.html#custom-collapsible-sections for the format
    # of section names.
    r = re.findall(r"section_(start|end):(\d+):([A-Za-z0-9_\-\.]+)", job_trace)
    for start, end in zip(r[::2], r[1::2]):
        timers[start[2]] = int(end[1]) - int(start[1])

    return timers


def determine_job_type(job_input_data: dict):
    name = job_input_data["build_name"]

    if "-generate" in name:
        return JobType.GENERATE

    if name == "no-specs-to-rebuild":
        return JobType.NO_SPECS
    if name == "rebuild-index":
        return JobType.REBUILD_INDEX
    if name == "copy":
        return JobType.COPY
    if name == "unsupported-copy":
        return JobType.UNSUPPORTED_COPY
    if name == "sign-pkgs":
        return JobType.SIGN_PKGS
    if name == "protected-publish":
        return JobType.PROTECTED_PUBLISH

    if re.match(BUILD_STAGE_REGEX, job_input_data["build_stage"]) is not None:
        return JobType.BUILD

    # Unrecognized type, raise error
    raise UnrecognizedJobType(job_input_data["build_id"], name)


def create_spack_job_data_dimension(data: JobMiscInfo | None):
    if data is None:
        return SpackJobDataDimension.get_empty_row()

    res, _ = SpackJobDataDimension.objects.get_or_create(
        job_size=data.job_size, stack=data.stack
    )
    return res


def create_gitlab_job_data_dimension(
    gljob: ProjectJob, job_input_data: dict, job_trace: str
):
    rvmatch = re.search(r"Running with gitlab-runner (\d+\.\d+\.\d+)", job_trace)
    runner_version = rvmatch.group(1) if rvmatch is not None else ""

    res, _ = GitlabJobDataDimension.objects.get_or_create(
        gitlab_runner_version=runner_version,
        ref=gljob.ref,
        tags=gljob.tag_list,
        commit_id=job_input_data["commit"]["id"],
        job_type=determine_job_type(job_input_data),
    )

    return res


def create_job_result_dimension(job_input_data: dict, job_trace: str):
    status = job_input_data["build_status"]
    error_taxonomy = (
        _assign_error_taxonomy(job_input_data, job_trace)[0]
        if status == "failed"
        else None
    )
    # job_exit_code = get_job_exit_code(job_id=job_id)
    # job_failure_reason: str = job_input_data["build_failure_reason"]
    unnecessary = UNNECESSARY_JOB_REGEX.search(job_trace) is not None
    res, _ = JobResultDimension.objects.get_or_create(
        status=status,
        error_taxonomy=error_taxonomy,
        unnecessary=unnecessary,
        job_type=determine_job_type(job_input_data=job_input_data),
    )

    return res


def create_job_retry_dimension(job_input_data: dict):
    job_id = job_input_data["build_id"]
    job_name = job_input_data["build_name"]
    job_commit_id = job_input_data["commit"]["id"]
    job_failure_reason: str = job_input_data["build_failure_reason"]
    retry_info = get_job_retry_data(
        job_id=job_id,
        job_name=job_name,
        job_commit_id=job_commit_id,
        job_failure_reason=job_failure_reason,
    )

    retry_info, _ = JobRetryDimension.objects.get_or_create(
        is_retry=retry_info.is_retry,
        is_manual_retry=retry_info.is_manual_retry,
        attempt_number=retry_info.attempt_number,
        final_attempt=retry_info.final_attempt,
    )

    return retry_info


def create_date_time_dimensions(
    gljob: ProjectJob,
) -> tuple[DateDimension, TimeDimension]:
    start_date = DateDimension.ensure_exists(gljob.started_at)
    start_time = TimeDimension.ensure_exists(gljob.started_at)

    return (start_date, start_time)


def create_node_dimension(info: NodeInfo | None) -> NodeDimension:
    if info is None:
        return NodeDimension.get_empty_row()

    node, _ = NodeDimension.objects.get_or_create(
        system_uuid=info.system_uuid,
        defaults={
            "name": info.name,
            "cpu": info.cpu,
            "memory": info.memory,
            "capacity_type": info.capacity_type,
            "instance_type": info.instance_type,
        },
    )

    return node


def create_runner_dimension(gl: gitlab.Gitlab, gljob: ProjectJob) -> RunnerDimension:
    empty_runner = RunnerDimension.get_empty_row()

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
    runner, _ = RunnerDimension.objects.get_or_create(
        runner_id=runner_id,
        defaults={
            "name": runner_name,
            "platform": runner.platform,
            "host": host,
            "arch": runner.architecture,
            "tags": runner.tag_list,
            "in_cluster": in_cluster,
        },
    )

    return runner


def create_package_dimension(info: PackageInfo | None) -> PackageDimension:
    if info is None:
        return PackageDimension.get_empty_row()

    package, _ = PackageDimension.objects.get_or_create(name=info.name)
    return package


def create_package_spec_dimension(info: PackageInfo | None) -> PackageSpecDimension:
    if info is None:
        return PackageSpecDimension.get_empty_row()

    spec, _ = PackageSpecDimension.objects.get_or_create(
        hash=info.hash,
        defaults={
            "name": info.name,
            "version": info.version,
            "compiler_name": info.compiler_name,
            "compiler_version": info.compiler_version,
            "arch": info.arch,
            "variants": info.variants,
        },
    )

    return spec
