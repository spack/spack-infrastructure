import tempfile
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass

import yaml
from gitlab.exceptions import GitlabGetError
from gitlab.v4.objects import ProjectJob


class JobArtifactFileNotFound(Exception):
    def __init__(self, job: ProjectJob, filename: str):
        message = f"File {filename} not found in job artifacts of job {job.id}"
        super().__init__(message)


class JobArtifactVariablesNotFound(Exception):
    def __init__(self, job: ProjectJob) -> None:
        message = f"Entry for job {job.id} not found in artifacts file: {job.name}"
        super().__init__(message)


class JobArtifactsMissingVariable(Exception):
    def __init__(self, job: ProjectJob, variable: str) -> None:
        message = f"The following variable was missing in the artifacts for job {job.id}: {variable}"
        super().__init__(message)


@contextmanager
def get_job_artifacts_file(job: ProjectJob, filename: str):
    """Yields a file IO, raises KeyError if the filename is not present"""
    with tempfile.NamedTemporaryFile(suffix=".zip") as temp:
        artifacts_file = temp.name

        # Download artifacts zip
        try:
            with open(artifacts_file, "wb") as f:
                job.artifacts(streamed=True, action=f.write)
        except GitlabGetError:
            raise JobArtifactFileNotFound(job, filename)

        # Open specific file within artifacts zip
        with zipfile.ZipFile(artifacts_file) as zfile:
            try:
                with zfile.open(filename) as timing_file:
                    yield timing_file
            except KeyError:
                raise JobArtifactFileNotFound(job, filename)


@dataclass
class JobArtifactsData:
    package_hash: str
    package_name: str
    package_version: str
    compiler_name: str
    compiler_version: str
    arch: str
    package_variants: str
    job_size: str
    stack: str

    # This var isn't guaranteed to be present
    build_jobs: int | None


def get_job_artifacts_data(gljob: ProjectJob) -> JobArtifactsData:
    """Fetch the artifacts of a job to retrieve info about it."""
    pipeline_yml_filename = "jobs_scratch_dir/reproduction/cloud-ci-pipeline.yml"
    with get_job_artifacts_file(gljob, pipeline_yml_filename) as pipeline_file:
        raw_pipeline = yaml.safe_load(pipeline_file)

    pipeline_vars = raw_pipeline.get("variables", {})
    job_vars = raw_pipeline.get(gljob.name, {}).get("variables", {})
    if not job_vars:
        raise JobArtifactVariablesNotFound(job=gljob)

    try:
        return JobArtifactsData(
            package_hash=job_vars["SPACK_JOB_SPEC_DAG_HASH"],
            package_name=job_vars["SPACK_JOB_SPEC_PKG_NAME"],
            package_version=job_vars["SPACK_JOB_SPEC_PKG_VERSION"],
            compiler_name=job_vars["SPACK_JOB_SPEC_COMPILER_NAME"],
            compiler_version=job_vars["SPACK_JOB_SPEC_COMPILER_VERSION"],
            arch=job_vars["SPACK_JOB_SPEC_ARCH"],
            package_variants=job_vars["SPACK_JOB_SPEC_VARIANTS"],
            job_size=job_vars["CI_JOB_SIZE"],
            stack=pipeline_vars["SPACK_CI_STACK_NAME"],
            build_jobs=job_vars.get("SPACK_BUILD_JOBS"),
        )
    except KeyError as e:
        raise JobArtifactsMissingVariable(job=gljob, variable=e.args[0])
