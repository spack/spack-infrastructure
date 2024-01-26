from time import sleep

from django.conf import settings
from gitlab.v4.objects import Project
import opensearch_dsl
import pytest

from analytics.core.job_failure_classifier import JobPayload


@pytest.mark.django_db()
def test_upload_job_failure_classification(gitlab_project: Project):
    opensearch_dsl.connections.create_connection(
        hosts=[settings.OPENSEARCH_ENDPOINT],
        http_auth=(
            settings.OPENSEARCH_USERNAME,
            settings.OPENSEARCH_PASSWORD,
        ),
    )
    print(JobPayload.search().count())
    file = gitlab_project.files.create(
        {
            "file_path": ".gitlab-ci.yml",
            "branch": "main",
            "content": """
test-job:
  script:
    - echo "The read operation timed out"
    - exit 1
            """,
            "author_email": "test@example.com",
            "author_name": "yourname",
            "commit_message": "Create testfile",
        }
    )

    while len(pipelines := gitlab_project.pipelines.list()) == 0:
        sleep(1)
    assert len(pipelines) == 1

    while (pipeline := gitlab_project.pipelines.get(pipelines[0].get_id())).status in (
        "pending",
        "running",
    ):
        sleep(1)

    job_trace = gitlab_project.jobs.get(pipeline.jobs.list()[0].get_id()).trace().decode()

    assert "The read operation timed out" in job_trace

    sleep(8)

    results = JobPayload.search().query("match", pipeline_id=pipeline.get_id()).execute()
    assert len(results) == 1
    assert results[0].error_taxonomy == "network_timeout"
