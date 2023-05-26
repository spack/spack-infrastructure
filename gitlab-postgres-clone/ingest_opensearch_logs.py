import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Generator

import click
import gitlab
import psycopg2
import yaml
from opensearch_dsl import Document, Search, connections
from tqdm import tqdm


class JobPayload(Document):
    class Index:
        name = "gitlab-job-failures-*"


OPENSEARCH_USERNAME = "admin"
OPENSEARCH_ENDPOINT = os.environ["OPENSEARCH_ENDPOINT"]
OPENSEARCH_PASSWORD = os.environ["OPENSEARCH_PASSWORD"]
connections.create_connection(
    hosts=[OPENSEARCH_ENDPOINT],
    http_auth=(
        OPENSEARCH_USERNAME,
        OPENSEARCH_PASSWORD,
    ),
)

POSTGRES_HOST = os.environ["POSTGRES_HOST"]
POSTGRES_DB = "gitlabhq_production"
POSTGRES_USER = "postgres"
POSTGRES_PASSWORD = os.environ["POSTGRES_PASSWORD"]
pg_conn = psycopg2.connect(
    host=POSTGRES_HOST,
    port="5432",
    dbname=POSTGRES_DB,
    user=POSTGRES_USER,
    password=POSTGRES_PASSWORD,
)

GITLAB_TOKEN = os.environ["GITLAB_TOKEN"]
gl = gitlab.Gitlab("https://gitlab.spack.io", GITLAB_TOKEN)

taxonomy = yaml.safe_load(
    (
        Path(__file__).parent.parent
        / "images"
        / "upload-gitlab-failure-logs"
        / "taxonomy.yaml"
    ).read_text()
)["taxonomy"]


def push_job_to_db(job_id: int, error_taxonomy: str, log: str):
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
                    job_id,
                    error_taxonomy,
                    log,
                ),
            )


@click.command()
@click.option("--dry-run", is_flag=True, default=False)
@click.option(
    "--days",
    type=int,
    required=True,
    help="Number of days to go back in re-classification.",
)
@click.option(
    "--error-taxonomy",
    type=str,
    required=False,
    help="If provided, only records that have this error taxonomy will be reclassified.",
)
def reindex(dry_run: bool, days: int, error_taxonomy: str | None):
    search_query: Search = JobPayload.search().query(
        "range",
        timestamp={
            "gte": datetime.utcnow() - timedelta(days=days),
            "lt": datetime.utcnow(),
            "format": "strict_date_optional_time",
        },
    )

    # If a specific taxonomy was provided, filter the results to only include records
    # with that taxonomy.
    if error_taxonomy is not None:
        search_query = search_query.query("match", error_taxonomy=error_taxonomy)

    doc_count = search_query.count()

    tqdm.write(f"Found {doc_count} doc(s) matching filter.")

    def iterator(gen: Generator):
        while True:
            try:
                yield next(gen)
            except StopIteration:
                break
            except Exception as e:
                print("Skipping error:", e)

        print("--- DONE ---")

    for doc in tqdm(iterator(search_query.scan()), total=doc_count):
        # Get GitLab job trace
        job_id = doc.build_id
        project = gl.projects.get(doc.project_id)
        job = project.jobs.get(job_id)
        job_trace: str = job.trace().decode()  # type: ignore

        # NOTE: The code below could be out of date, and should be checked against the code in
        # images/upload-gitlab-failure-logs/upload_gitlab_failure_logs.py

        matching_patterns = set()
        for error_class, lookups in taxonomy["error_classes"].items():
            if lookups:
                for grep_expr in lookups.get("grep_for", []):
                    if re.compile(grep_expr).search(job_trace):
                        matching_patterns.add(error_class)

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
            if doc.build_failure_reason in (
                "stuck_or_timeout_failure",
                "scheduler_failure",
            ):
                job_error_class = doc.build_failure_reason

        if not dry_run and job_trace:
            push_job_to_db(job_id=job_id, error_taxonomy=job_error_class, log=job_trace)


if __name__ == "__main__":
    reindex()
