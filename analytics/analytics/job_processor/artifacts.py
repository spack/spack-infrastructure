import tempfile
import zipfile
from contextlib import contextmanager

import yaml
from gitlab.v4.objects import ProjectJob

from analytics.core.models import LegacyJob


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


def annotate_job_with_artifacts_data(gljob: ProjectJob, job: LegacyJob):
    """Fetch the artifacts of a job to retrieve info about it."""
    pipeline_yml_filename = "jobs_scratch_dir/reproduction/cloud-ci-pipeline.yml"
    with get_job_artifacts_file(gljob, pipeline_yml_filename) as pipeline_file:
        raw_pipeline = yaml.safe_load(pipeline_file)

    pipeline_vars = raw_pipeline.get("variables", {})
    job_vars = raw_pipeline.get(gljob.name, {}).get("variables", {})
    if not job_vars:
        raise Exception(f"Empty job variables for job {gljob.id}")

    job.package_name = job_vars["SPACK_JOB_SPEC_PKG_NAME"]
    job.package_version = job_vars["SPACK_JOB_SPEC_PKG_VERSION"]
    job.compiler_name = job_vars["SPACK_JOB_SPEC_COMPILER_NAME"]
    job.compiler_version = job_vars["SPACK_JOB_SPEC_COMPILER_VERSION"]
    job.arch = job_vars["SPACK_JOB_SPEC_ARCH"]
    job.package_variants = job_vars["SPACK_JOB_SPEC_VARIANTS"]
    job.job_size = job_vars["CI_JOB_SIZE"]
    job.stack = pipeline_vars["SPACK_CI_STACK_NAME"]

    # This var isn't guaranteed to be present
    job.build_jobs = job_vars.get("SPACK_BUILD_JOBS")
