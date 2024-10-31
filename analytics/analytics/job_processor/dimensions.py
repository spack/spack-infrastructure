from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any

from django.db import connections
import gitlab
import gitlab.exceptions
from gitlab.v4.objects import ProjectJob
import sentry_sdk
import yaml

from analytics.core.models.dimensions import (
    DateDimension,
    JobDataDimension,
    NodeDimension,
    PackageDimension,
    PackageSpecDimension,
    RunnerDimension,
    TimeDimension,
)
from analytics.job_processor.metadata import JobMiscInfo, NodeInfo, PackageInfo, PodInfo

UNNECESSARY_JOB_REGEX = re.compile(r"No need to rebuild [^,]+, found hash match")
BUILD_STAGE_REGEX = r"^stage-\d+$"


class UnrecognizedJobType(Exception):
    def __init__(self, job_id: int, name: str) -> None:
        message = f"Unrecognized job type for Job: ({job_id}) {name}"
        super().__init__(message)


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
        # A non-retryable job can either have an explicit max of zero, or no max at all.
        # If the job is not retryable, the 'when' key will not exist
        if retry_max in (0, None):
            retry_reasons = []
        # If the job is retryable, the 'when' key will be a list of reasons to retry
        else:
            retry_reasons = retry_config["when"]
        # final_attempt is defined as an attempt that won't be retried for the retry_reasons
        # or because it's gone beyond the max number of retries.
        retryable_by_reason = "always" in retry_reasons or job_failure_reason in retry_reasons
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
        return JobDataDimension.JobType.GENERATE

    if name == "no-specs-to-rebuild":
        return JobDataDimension.JobType.NO_SPECS
    if name == "rebuild-index":
        return JobDataDimension.JobType.REBUILD_INDEX
    if name == "copy":
        return JobDataDimension.JobType.COPY
    if name == "unsupported-copy":
        return JobDataDimension.JobType.UNSUPPORTED_COPY
    if name == "sign-pkgs":
        return JobDataDimension.JobType.SIGN_PKGS
    if name == "protected-publish":
        return JobDataDimension.JobType.PROTECTED_PUBLISH

    if re.match(BUILD_STAGE_REGEX, job_input_data["build_stage"]) is not None:
        return JobDataDimension.JobType.BUILD

    # Unrecognized type, raise error
    raise UnrecognizedJobType(job_input_data["build_id"], name)


def create_job_data_dimension(
    job_input_data: dict,
    misc_info: JobMiscInfo | None,
    pod_info: PodInfo | None,
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

    job_data = JobDataDimension.objects.create(
        job_id=job_id,
        commit_id=job_commit_id,
        job_url=f"https://gitlab.spack.io/spack/spack/-/jobs/{job_id}",
        name=job_name,
        ref=gljob.ref,
        tags=gljob.tag_list,
        job_size=misc_info.job_size if misc_info else None,
        stack=misc_info.stack if misc_info else None,
        # Retry info
        is_retry=retry_info.is_retry,
        is_manual_retry=retry_info.is_manual_retry,
        attempt_number=retry_info.attempt_number,
        final_attempt=retry_info.final_attempt,
        status=job_status,
        error_taxonomy=error_taxonomy,
        unnecessary=unnecessary,
        pod_name=pod_info.name if pod_info else None,
        gitlab_runner_version=runner_version,
        job_type=determine_job_type(job_input_data),
        gitlab_section_timers=gitlab_section_timers,
    )

    return job_data


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
        name=info.name,
        cpu=info.cpu,
        memory=info.memory,
        capacity_type=info.capacity_type,
        instance_type=info.instance_type,
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
        name=runner_name,
        platform=runner.platform,
        host=host,
        arch=runner.architecture,
        tags=runner.tag_list,
        in_cluster=in_cluster,
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
