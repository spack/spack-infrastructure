import json
import os
import tempfile
import zipfile
from contextlib import contextmanager

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


def get_job_metadata(job: ProjectJob) -> dict:
    # parse the yaml from artifacts/jobs_scratch_dir/reproduction/cloud-ci-pipeline.yml
    pipeline_yml_filename = "jobs_scratch_dir/reproduction/cloud-ci-pipeline.yml"
    with get_job_artifacts_file(job, pipeline_yml_filename) as pipeline_file:
        raw_pipeline = yaml.safe_load(pipeline_file)

    # Load vars and return
    pipeline_vars = raw_pipeline.get("variables", {})
    job_vars = raw_pipeline.get(job.name, {}).get("variables", {})
    if not job_vars:
        raise Exception(f"Empty job variables for job {job.id}")

    return {
        "package_name": job_vars["SPACK_JOB_SPEC_PKG_NAME"],
        "package_version": job_vars["SPACK_JOB_SPEC_PKG_VERSION"],
        "compiler_name": job_vars["SPACK_JOB_SPEC_COMPILER_NAME"],
        "compiler_version": job_vars["SPACK_JOB_SPEC_COMPILER_VERSION"],
        "arch": job_vars["SPACK_JOB_SPEC_ARCH"],
        "package_variants": job_vars["SPACK_JOB_SPEC_VARIANTS"],
        "job_size": job_vars["CI_JOB_SIZE"],
        "stack": pipeline_vars["SPACK_CI_STACK_NAME"],
        # This var isn't guaranteed to be present
        "build_jobs": job_vars.get("SPACK_BUILD_JOBS"),
    }


def create_job(project: Project, job: ProjectJob) -> Job:
    # grab runner tags
    runner_tags = gl.runners.get(job.runner["id"]).tag_list

    # Return created job
    return Job.objects.create(
        job_id=job.get_id(),
        project_id=project.get_id(),
        name=job.name,
        started_at=job.started_at,
        duration=job.duration,
        ref=job.ref,
        tags=job.tag_list,
        aws=("aws" in runner_tags),
        **get_job_metadata(job),
    )


def get_timings_json(job: ProjectJob) -> list[dict]:
    timing_filename = "jobs_scratch_dir/user_data/install_times.json"
    with get_job_artifacts_file(job, timing_filename) as file:
        return json.load(file)


@click.command()
def main():
    # Read input data and extract params
    job_input_data = json.loads(JOB_INPUT_DATA)
    job_id = job_input_data["build_id"]

    # Retrieve project and job from gitlab API
    gl_project = gl.projects.get(job_input_data["project_id"])
    gl_job = gl_project.jobs.get(job_input_data["build_id"])

    # Get or create job record
    job = Job.objects.filter(job_id=job_id).first()
    if job is None:
        job = create_job(gl_project, gl_job)

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
