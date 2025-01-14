import base64
from pathlib import Path
from time import sleep
from typing import cast
from uuid import uuid4

from django.conf import settings
from gitlab import Gitlab
from gitlab.v4.objects import Project
import minio
import pytest
import requests


@pytest.fixture()
def gitlab_client() -> Gitlab:
    try:
        requests.get(settings.GITLAB_ENDPOINT).raise_for_status()
    except requests.exceptions.RequestException:
        pytest.skip(reason="GitLab failed health check, skipped GitLab integration tests")
    return Gitlab(settings.GITLAB_ENDPOINT, settings.GITLAB_TOKEN)


@pytest.fixture()
def allow_gitlab_webhooks(gitlab_client: Gitlab):
    gl_settings = gitlab_client.settings.get()
    gl_settings.allow_local_requests_from_web_hooks_and_services = True
    gl_settings.max_yaml_size_bytes = 50 * 1024 * 1024
    gl_settings.save()


@pytest.fixture()
def gitlab_project(gitlab_client: Gitlab, allow_gitlab_webhooks):
    project = gitlab_client.projects.get("root/spack")

    ci_variables = {
        # Force rebuild of all packages
        "SPACK_PRUNE_UP_TO_DATE": False,
        "SPACK_PRUNE_UNTOUCHED": False,
        # Only enable build_systems stack
        "SPACK_CI_ENABLE_STACKS": "build_systems",
        # Set the signing key to the dummy key
        "SPACK_SIGNING_KEY": base64.b64encode(
            (Path(__file__).parent / "data" / "dummy.gpg").read_text().encode()
        ).decode(),
        # Configure minio build cache
        "PR_MIRROR_FETCH_DOMAIN": "s3://spack-binaries-prs-test",
        "PR_MIRROR_PUSH_DOMAIN": "s3://spack-binaries-prs-test",
        "PROTECTED_MIRROR_FETCH_DOMAIN": "s3://spack-binaries-test",
        "PROTECTED_MIRROR_PUSH_DOMAIN": "s3://spack-binaries-test",
        "AWS_ENDPOINT_URL_S3": "http://minio:9000",
        "AWS_ACCESS_KEY": "minioAccessKey",
        "AWS_SECRET_ACCESS_KEY": "minioSecretKey",
        "AWS_REGION": "us-east-1",
    }
    for k, v in ci_variables.items():
        project.variables.create({"key": k, "value": v})

    project.ci_config_path = "share/spack/gitlab/cloud_pipelines/.gitlab-ci.yml"
    project.save()

    client = minio.Minio(
        endpoint="localhost:9000",
        access_key="minioAccessKey",
        secret_key="minioSecretKey",
        secure=False,
        region="us-east-1",
    )
    client.make_bucket("spack-binaries-test")
    client.make_bucket("spack-binaries-prs-test")

    return project
    # project = cast(Project, gitlab_client.projects.create({"name": f"test-project-{uuid4()}"}))
    # project.hooks.create({"url": "http://django:8000", "job_events": True})
    # yield project
    # project.delete()


def wait_for_pipeline_completion(gitlab_project: Project, pipeline_id: int):
    while len(pipelines := gitlab_project.pipelines.list()) == 0:
        sleep(1)
    assert len(pipelines) == 1

    while (pipeline := gitlab_project.pipelines.get(pipelines[0].get_id())).status in (
        "pending",
        "running",
    ):
        sleep(1)


def run_echo_job(gitlab_project: Project, job_output: str) -> str:
    file = gitlab_project.files.create(
        {
            "file_path": ".gitlab-ci.yml",
            "branch": "main",
            "content": f"""
test-generate:
  stage: build
  script:
    - echo \"{job_output}\"
    - exit 1
            """,
            "author_email": "test@example.com",
            "author_name": "yourname",
            "commit_message": "Create testfile",
        }
    )
