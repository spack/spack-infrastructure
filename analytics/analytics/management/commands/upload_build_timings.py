import json
import os
import tempfile
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass

import djclick as click
import gitlab
import yaml
from gitlab.v4.objects import Project, ProjectJob

from analytics.models import Job, Timer, TimerPhase

# Instantiate gitlab api wrapper
GITLAB_TOKEN = os.environ["GITLAB_TOKEN"]
GITLAB_URL = os.getenv("GITLAB_URL", "https://gitlab.spack.io")
gl = gitlab.Gitlab(GITLAB_URL, GITLAB_TOKEN)

# Grab job data
JOB_INPUT_DATA = os.environ["JOB_INPUT_DATA"]


@dataclass
class JobMetadata:
    package_name: str
    package_version: str
    compiler_name: str
    compiler_version: str
    arch: str
    package_variants: str
    job_size: str
    stack: str
    build_jobs: str | None = None


class UnprocessedAwsJob(Exception):
    def __init__(self, job: ProjectJob):
        message = f"AWS Job {job.get_id()} was not previously processed"
        super().__init__(message)


class JobArtifactFileNotFound(Exception):
    def __init__(self, job: ProjectJob, filename: str):
        message = f"File {filename} not found in job artifacts of job {job.id}"
        super().__init__(message)


@contextmanager
def get_job_artifacts_file(job: ProjectJob, filename: str):
    """Yields a file IO, raises KeyError if the filename is not present"""
    with tempfile.NamedTemporaryFile(suffix=".zip") as temp:
        artifacts_file = temp.name
        with open(artifacts_file, "wb") as f:
            job.artifacts(streamed=True, action=f.write)

        with zipfile.ZipFile(artifacts_file) as zfile:
            try:
                with zfile.open(filename) as timing_file:
                    yield timing_file
            except KeyError:
                raise JobArtifactFileNotFound(job, filename)


def get_job_metadata(job: ProjectJob) -> JobMetadata:
    # parse the yaml from artifacts/jobs_scratch_dir/reproduction/cloud-ci-pipeline.yml
    pipeline_yml_filename = "jobs_scratch_dir/reproduction/cloud-ci-pipeline.yml"
    with get_job_artifacts_file(job, pipeline_yml_filename) as pipeline_file:
        raw_pipeline = yaml.safe_load(pipeline_file)

    # Load vars and return
    pipeline_vars = raw_pipeline.get("variables", {})
    job_vars = raw_pipeline.get(job.name, {}).get("variables", {})
    if not job_vars:
        raise Exception(f"Empty job variables for job {job.id}")

    return JobMetadata(
        package_name=job_vars["SPACK_JOB_SPEC_PKG_NAME"],
        package_version=job_vars["SPACK_JOB_SPEC_PKG_VERSION"],
        compiler_name=job_vars["SPACK_JOB_SPEC_COMPILER_NAME"],
        compiler_version=job_vars["SPACK_JOB_SPEC_COMPILER_VERSION"],
        arch=job_vars["SPACK_JOB_SPEC_ARCH"],
        package_variants=job_vars["SPACK_JOB_SPEC_VARIANTS"],
        job_size=job_vars["CI_JOB_SIZE"],
        stack=pipeline_vars["SPACK_CI_STACK_NAME"],
        # This var isn't guaranteed to be present
        build_jobs=job_vars.get("SPACK_BUILD_JOBS"),
    )


def create_non_aws_job(project: Project, job: ProjectJob) -> Job:
    # Raise exception if this is an AWS job, as it should have been processed already
    runner_tags = gl.runners.get(job.runner["id"]).tag_list
    if "aws" in runner_tags:
        raise UnprocessedAwsJob(job)

    # Return created job
    job_metadata = get_job_metadata(job)
    return Job.objects.create(
        job_id=job.get_id(),
        project_id=project.get_id(),
        name=job.name,
        started_at=job.started_at,
        duration=job.duration,
        ref=job.ref,
        tags=job.tag_list,
        package_name=job_metadata.package_name,
        aws=True,
        # Extra fields
        package_version=job_metadata.package_version,
        compiler_name=job_metadata.compiler_name,
        compiler_version=job_metadata.compiler_version,
        arch=job_metadata.arch,
        package_variants=job_metadata.package_variants,
        build_jobs=job_metadata.build_jobs,
        job_size=job_metadata.job_size,
        stack=job_metadata.stack,
    )


def get_timings_json(job: ProjectJob) -> list[dict]:
    timing_filename = "jobs_scratch_dir/user_data/install_times.json"
    with get_job_artifacts_file(job, timing_filename) as file:
        return json.load(file)


@click.command()
def main():
    # Read input data and extract params
    job_input_data = json.loads(JOB_INPUT_DATA)
    project_id = job_input_data["project_id"]
    job_id = job_input_data["build_id"]

    # Retrieve project and job from gitlab API
    gl_project = gl.projects.get(project_id)
    gl_job = gl_project.jobs.get(job_id)

    # Get and update existing job, or create new job
    try:
        job = Job.objects.get(project_id=project_id, job_id=job_id)
        Job.objects.filter(project_id=job.project_id, job_id=job.job_id).update(
            tags=gl_job.tag_list,
            duration=gl_job.duration,
        )
    except Job.DoesNotExist:
        job = create_non_aws_job(gl_project, gl_job)

    # Get timings
    timings = get_timings_json(gl_job)

    # Iterate through each timer and create timers and phase results
    phases = []
    for entry in timings:
        # Sometimes name can be missing, skip if so
        name = entry.get("name")
        if name is None:
            continue

        # Check for timer and skip if already exists
        pkghash = entry.get("hash")
        if Timer.objects.filter(job=job, name=name, hash=pkghash).exists():
            continue

        # Create timer
        timer = Timer.objects.create(
            job=job,
            name=name,
            hash=pkghash,
            cache=entry["cache"],
            time_total=entry["total"],
        )

        # Add all phases to bulk phase list
        phases.extend(
            [
                TimerPhase(
                    timer=timer,
                    name=phase["name"],
                    path=phase["path"],
                    seconds=phase["seconds"],
                    count=phase["count"],
                    is_subphase=("/" in phase["path"]),
                )
                for phase in entry["phases"]
            ]
        )

    # Bulk create phases
    TimerPhase.objects.bulk_create(phases)


if __name__ == "__main__":
    main()
