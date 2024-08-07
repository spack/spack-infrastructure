import json
import re
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta

import djclick as click
from django.db import connection
from gitlab.v4.objects import ProjectJob
from tqdm import tqdm

from analytics.core.models.dimensions import (
    JobDataDimension,
    NodeDimension,
    PackageDimension,
    PackageSpecDimension,
)
from analytics.core.models.facts import JobFact
from analytics.core.models.legacy import LegacyJobAttempt
from analytics.job_processor import process_job
from analytics.job_processor.dimensions import (
    create_date_time_dimensions,
    create_job_data_dimension,
    create_runner_dimension,
)
from analytics.job_processor.utils import (
    get_gitlab_handle,
    get_gitlab_job,
    get_gitlab_project,
)

# Setup gitlab connection
gl = get_gitlab_handle()
gl_project = get_gitlab_project(2)

BUILD_NAME_REGEX = re.compile(r"^[^@]+@\S+ \/[a-z0-9]{7} %")
ALT_BUILD_NAME_REGEX = re.compile(r"^\(specs\) [^/]+\/[a-z0-9]{7}")


def augment_job_data(job_attempt: LegacyJobAttempt):
    job_id = job_attempt.job_id
    job_data = JobDataDimension.objects.get(job_id=job_id)

    job_data.error_taxonomy = job_attempt.error_taxonomy
    job_data.gitlab_section_timers = job_attempt.section_timers

    # Copy retry data
    job_data.is_retry = job_attempt.is_retry
    job_data.is_manual_retry = job_attempt.is_manual_retry
    job_data.attempt_number = job_attempt.attempt_number
    job_data.final_attempt = job_attempt.final_attempt

    job_data.save()


def create_basic_job_fact(gljob: ProjectJob, job_input_data: dict):
    date_dim, time_dim = create_date_time_dimensions(gljob=gljob)
    runner_dim = create_runner_dimension(gl=gl, gljob=gljob)
    job_dim = create_job_data_dimension(
        job_input_data=job_input_data,
        pod_info=None,
        misc_info=None,
        gljob=gljob,
        job_trace="",
    )

    JobFact.objects.create(
        # Foreign Keys
        start_date=date_dim,
        start_time=time_dim,
        node=NodeDimension.get_empty_row(),
        runner=runner_dim,
        package=PackageDimension.get_empty_row(),
        spec=PackageSpecDimension.get_empty_row(),
        job=job_dim,
        # Numeric
        duration=timedelta(seconds=gljob.duration),
        duration_seconds=gljob.duration,
    )


def migrate_job_attempt(job_id: int):
    job_attempt = LegacyJobAttempt.objects.get(job_id=job_id)
    gl_job = get_gitlab_job(gl_project, job_attempt.job_id)

    # It seems that even if a job has a status of "success", it always at
    # least has a "build_failure_reason" of "unknown_failure"
    failure_reason = getattr(gl_job, "job_failure_reason", "unknown_failure")

    # Determine whether this is a build job or not from the name, and mock the stage field to match that
    is_build = (
        BUILD_NAME_REGEX.match(job_attempt.name) is not None
        or ALT_BUILD_NAME_REGEX.match(job_attempt.name) is not None
    )
    build_stage = "stage-1" if is_build else ""

    # Reconstruct the job_input_data dict, to pass to create_job_fact
    job_input_data = {
        "project_id": 2,
        "build_id": job_attempt.job_id,
        "build_name": job_attempt.name,
        "commit": {"id": job_attempt.commit_id},
        "build_failure_reason": failure_reason,
        "build_status": job_attempt.status,
        "build_stage": build_stage,
        "ref": job_attempt.ref,
    }

    try:
        process_job(json.dumps(job_input_data))
    except Exception:
        # Default to this if errored
        create_basic_job_fact(gljob=gl_job, job_input_data=job_input_data)

    # Augment remaining data from existing job_attempt record
    augment_job_data(job_attempt=job_attempt)


@click.command()
def migrate_all_job_attempts():
    # Get all job attempts that don't already have a record in the fact table
    # Use raw SQL query as otherwise an inefficient subquery is required
    cursor = connection.cursor()
    cursor.execute("""
        SELECT lja.job_id
        FROM core_legacyjobattempt lja
        LEFT JOIN core_jobfact on core_jobfact.job_id = lja.job_id
        WHERE core_jobfact.id IS NULL
    """)
    job_ids = cursor.fetchall()

    with tqdm(total=len(job_ids)) as pbar:
        with ThreadPoolExecutor(max_workers=10) as e:
            futures = [e.submit(migrate_job_attempt, job_id) for (job_id,) in job_ids]
            for future in as_completed(futures):
                pbar.update(1)
                pbar.set_description()
                if future.exception() is not None:
                    traceback.print_exception(future.exception())
