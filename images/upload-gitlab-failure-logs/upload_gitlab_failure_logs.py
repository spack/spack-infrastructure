import json
import os
import re
from datetime import datetime
from pathlib import Path

import gitlab
import psycopg2
import yaml
from opensearch_dsl import Date, Document, connections


class JobPayload(Document):
    timestamp = Date()

    class Index:
        name = "gitlab-job-failures-*"

    def save(self, **kwargs):
        # assign now if no timestamp given
        if not self.timestamp:
            self.timestamp = datetime.now()

        # override the index to go to the proper timeslot
        kwargs["index"] = self.timestamp.strftime("gitlab-job-failures-%Y%m%d")
        return super().save(**kwargs)


GITLAB_TOKEN = os.environ["GITLAB_TOKEN"]
GITLAB_POSTGRES_DB = os.environ["GITLAB_POSTGRES_DB"]
GITLAB_POSTGRES_USER = os.environ["GITLAB_POSTGRES_RO_USER"]
GITLAB_POSTGRES_PASSWORD = os.environ["GITLAB_POSTGRES_RO_PASSWORD"]
GITLAB_POSTGRES_HOST = os.environ["GITLAB_POSTGRES_HOST"]

OPENSEARCH_ENDPOINT = os.environ["OPENSEARCH_ENDPOINT"]
OPENSEARCH_USERNAME = os.environ["OPENSEARCH_USERNAME"]
OPENSEARCH_PASSWORD = os.environ["OPENSEARCH_PASSWORD"]


# Instantiate gitlab api wrapper
gl = gitlab.Gitlab("https://gitlab.spack.io", GITLAB_TOKEN)

# Instantiate postgres connection
pg_conn = psycopg2.connect(
    host=GITLAB_POSTGRES_HOST,
    port="5432",
    dbname=GITLAB_POSTGRES_DB,
    user=GITLAB_POSTGRES_USER,
    password=GITLAB_POSTGRES_PASSWORD,
)


def job_has_been_retried(job_id: str | int) -> bool:
    with pg_conn:
        cur = pg_conn.cursor()
        cur.execute(
            """
                SELECT COALESCE(ci_builds.retried, false) FROM ci_builds
                WHERE ci_builds.id = %(job_id)s;
            """,
            {"job_id": job_id},
        )
        result = cur.fetchone()
        cur.close()

    return result[0]


def assign_error_taxonomy(job_input_data: dict):
    # Retrieve project and job from gitlab API
    project = gl.projects.get(job_input_data["project_id"])
    job_id = job_input_data["build_id"]
    job = project.jobs.get(job_id)

    # Read taxonomy file
    with open(Path(__file__).parent / "taxonomy.yaml") as f:
        taxonomy = yaml.safe_load(f)["taxonomy"]
    job_input_data["error_taxonomy_version"] = taxonomy["version"]

    # Compile matching patterns from job trace
    job_trace: str = job.trace().decode()  # type: ignore
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

    job_input_data["error_taxonomy"] = job_error_class
    return


def main():
    # Read input data and extract params
    job_input_data = json.loads(os.environ["JOB_INPUT_DATA"])
    job_id = job_input_data["build_id"]

    # Annotate if job has been retried
    job_input_data["retried"] = job_has_been_retried(job_id)

    # Convert all string timestamps in webhook payload to `datetime` objects
    for key, val in job_input_data.items():
        try:
            if isinstance(val, str):
                job_input_data[key] = datetime.strptime(val, "%Y-%m-%d %H:%M:%S %Z")
        except ValueError:
            continue

    # Assign any/all relevant errors
    assign_error_taxonomy(job_input_data)

    # Upload to OpenSearch
    connections.create_connection(
        hosts=[OPENSEARCH_ENDPOINT],
        http_auth=(
            OPENSEARCH_USERNAME,
            OPENSEARCH_PASSWORD,
        ),
    )
    doc = JobPayload(**job_input_data)
    doc.save()


if __name__ == "__main__":
    main()
