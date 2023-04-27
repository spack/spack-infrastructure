import functools
import os
import re
from dataclasses import dataclass
from pathlib import Path

import gitlab
import psycopg2
import yaml
from gitlab.v4.objects.jobs import ProjectJob
from gitlab.v4.objects.pipelines import ProjectPipelineJob
from tqdm import tqdm

GITLAB_TOKEN = os.environ["GITLAB_TOKEN"]
POSTGRES_DB = "gitlab"
POSTGRES_USER = "postgres"
POSTGRES_PASSWORD = "postgres"
POSTGRES_HOST = "localhost"


# Instantiate gitlab api wrapper
gl = gitlab.Gitlab("https://gitlab.spack.io", GITLAB_TOKEN)

# Instantiate postgres connection
pg_conn = psycopg2.connect(
    host=POSTGRES_HOST,
    port="5432",
    dbname=POSTGRES_DB,
    user=POSTGRES_USER,
    password=POSTGRES_PASSWORD,
)


@dataclass
class JobLog:
    job_id: int
    log: str
    error_taxonomy: str


def push_job_to_db(job_log: JobLog):
    # TODO: Use postgres COPY FROM
    with pg_conn:
        with pg_conn.cursor() as cur:
            cur.execute(
                """
                INSERT into job_logs (job_id, error_taxonomy, log) VALUES (%s, %s, %s)
                ON CONFLICT (job_id)
                DO
                    UPDATE SET log = EXCLUDED.log
                ;
                """,
                (
                    job_log.job_id,
                    job_log.error_taxonomy,
                    job_log.log,
                ),
            )


@functools.cache
def read_taxonomy():
    # Read taxonomy file
    with open(
        Path(__file__).parent.parent
        / "images"
        / "upload-gitlab-failure-logs"
        / "taxonomy.yaml"
    ) as f:
        return yaml.safe_load(f)["taxonomy"]


def match_error_class(job: ProjectJob, log: str) -> str:
    taxonomy = read_taxonomy()

    # Compile matching patterns from job trace
    matching_patterns = set()
    for error_class, lookups in taxonomy["error_classes"].items():
        if lookups:
            for grep_expr in lookups.get("grep_for", []):
                if re.compile(grep_expr).search(log):
                    matching_patterns.add(error_class)

    # If the job logs matched any regexes, assign it the taxonomy
    # with the highest priority in the "deconflict order".
    # Otherwise, assign it a taxonomy of "other".
    if len(matching_patterns):
        for error_class in taxonomy["deconflict_order"]:
            if error_class in matching_patterns:
                return error_class

    # If this job timed out or failed to be scheduled by GitLab, label it as such.
    failure_reasons = ["stuck_or_timeout_failure", "scheduler_failure"]
    if getattr(job, "failure_reason", None) in failure_reasons:
        return job.failure_reason

    # Default unclassified category
    return "other"


def job_to_job_log(job: ProjectJob) -> JobLog:
    log = job.trace().decode()
    return JobLog(
        job_id=job.id,
        error_taxonomy=match_error_class(job, log=log),
        log=log,
    )


project = gl.projects.get(2)
pipelines = project.pipelines.list(
    all=True, iterator=True, order_by="id", sort="desc", status="failed"
)
for pipeline in tqdm(pipelines):
    jobs = pipeline.jobs.list(scope="failed")
    for pipeline_job in tqdm(jobs):
        pipeline_job: ProjectPipelineJob
        job = project.jobs.get(id=pipeline_job.get_id())
        push_job_to_db(job_to_job_log(job))
