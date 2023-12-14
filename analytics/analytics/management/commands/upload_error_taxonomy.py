import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from time import sleep
from typing import Any

import djclick as click
import gitlab
import psycopg2
import yaml

from analytics.models import ErrorTaxonomy, Job

GITLAB_TOKEN = os.environ["GITLAB_TOKEN"]
GITLAB_POSTGRES_DB = os.environ["GITLAB_POSTGRES_DB"]
GITLAB_POSTGRES_USER = os.environ["GITLAB_POSTGRES_RO_USER"]
GITLAB_POSTGRES_PASSWORD = os.environ["GITLAB_POSTGRES_RO_PASSWORD"]
GITLAB_POSTGRES_HOST = os.environ["GITLAB_POSTGRES_HOST"]


def job_retry_data(job_id: str | int, job_name: str) -> tuple[int, bool]:
    # Instantiate postgres connection
    pg_conn = psycopg2.connect(
        host=GITLAB_POSTGRES_HOST,
        port="5432",
        dbname=GITLAB_POSTGRES_DB,
        user=GITLAB_POSTGRES_USER,
        password=GITLAB_POSTGRES_PASSWORD,
    )
    with pg_conn:
        cur = pg_conn.cursor()
        cur.execute(
            """
            SELECT attempt_number, COALESCE(retried, FALSE) as retried FROM (
                SELECT ROW_NUMBER() OVER (ORDER BY id) as attempt_number, retried, id
                FROM ci_builds
                WHERE
                    ci_builds.name = %(job_name)s
                    and ci_builds.stage_id = (
                        SELECT stage_id from ci_builds WHERE id = %(job_id)s LIMIT 1
                    )
                    and ci_builds.status = 'failed'
            ) as build_attempts
            WHERE build_attempts.id = %(job_id)s
            ;
            """,
            {"job_id": job_id, "job_name": job_name},
        )
        result = cur.fetchone()
        cur.close()

    return result


def assign_error_taxonomy(
    job_input_data: dict[str, Any], job_trace: str
) -> tuple[str, str]:
    # Read taxonomy file
    with open(Path(__file__).parent / "taxonomy.yaml") as f:
        taxonomy = yaml.safe_load(f)["taxonomy"]

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
    job_error_class: str | None = None
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

    return job_error_class, taxonomy["version"]


def get_job_trace(gl_project_id: int, gl_build_id: int) -> str:
    # Instantiate gitlab api wrapper
    gl = gitlab.Gitlab("https://gitlab.spack.io", GITLAB_TOKEN)

    # Retrieve project and job from gitlab API
    project = gl.projects.get(gl_project_id)
    job = project.jobs.get(gl_build_id)
    return job.trace().decode()  # type: ignore


@click.command()
def main():
    # Read input data and extract params
    job_input_data: dict[str, Any] = json.loads(os.environ["JOB_INPUT_DATA"])
    project_id: int = job_input_data["project_id"]
    job_id: int = job_input_data["build_id"]
    job_name: str = job_input_data["build_name"]

    # Annotate if job has been retried
    attempt_number, retried = job_retry_data(job_id=job_id, job_name=job_name)

    job_trace = get_job_trace(project_id, job_id)

    # Assign any/all relevant errors
    error_taxonomy, error_taxonomy_version = assign_error_taxonomy(
        job_input_data, job_trace
    )

    # Give the build timing hook some time to create the Job record, if needed.
    # If we're waiting longer than 10 minutes, stop the loop and let an
    # exception get raised (which Sentry will catch)
    start = datetime.now()
    while (
        not Job.objects.filter(job_id=job_id).exists()
        and start + timedelta(minutes=10) > datetime.now()
    ):
        sleep(2)

    ErrorTaxonomy.objects.create(
        job_id=job_id,
        attempt_number=attempt_number,
        retried=retried,
        error_taxonomy=error_taxonomy,
        error_taxonomy_version=error_taxonomy_version,
        webhook_payload=job_input_data,
    )


if __name__ == "__main__":
    main()
