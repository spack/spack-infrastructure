import base64
import time
from pathlib import Path
from time import sleep
from typing import cast
from uuid import uuid4

from django.conf import settings
from gitlab import Gitlab, GitlabGetError
from gitlab.v4.objects import Group, Project, ProjectFork
import minio
import pytest
import requests

def _maybe_delete_bucket(client: minio.Minio, bucket_name: str):
    if client.bucket_exists(bucket_name):
        items_to_delete = client.list_objects(bucket_name)
        for item in items_to_delete:
            client.remove_object(bucket_name, item.object_name)
        client.remove_bucket(bucket_name)

@pytest.fixture(scope='session')
def minio_client() -> minio.Minio:
    return minio.Minio(
        endpoint="localhost:9000",
        access_key="minioAccessKey",
        secret_key="minioSecretKey",
        secure=False,
        region="us-east-1",
    )

@pytest.fixture(scope='session')
def pr_build_cache_bucket(minio_client: minio.Minio):
    pr_bucket_name = 'spack-binaries-prs-test'

    # Clean up the bucket if it exists
    _maybe_delete_bucket(minio_client, pr_bucket_name)

    minio_client.make_bucket(pr_bucket_name)

    yield pr_bucket_name

    # Clean up the bucket after the tests
    _maybe_delete_bucket(minio_client, pr_bucket_name)


@pytest.fixture(scope='session')
def protected_build_cache_bucket(minio_client: minio.Minio):
    protected_bucket_name = 'spack-binaries-test'

    # Clean up the bucket if it exists
    _maybe_delete_bucket(minio_client, protected_bucket_name)

    minio_client.make_bucket(protected_bucket_name)

    yield protected_bucket_name

    # Clean up the bucket after the tests
    _maybe_delete_bucket(minio_client, protected_bucket_name)


@pytest.fixture(scope="session")
def gitlab_client() -> Gitlab:
    try:
        requests.get(settings.GITLAB_ENDPOINT).raise_for_status()
    except requests.exceptions.RequestException:
        pytest.skip(reason="GitLab failed health check, skipped GitLab integration tests")
    return Gitlab(settings.GITLAB_ENDPOINT, settings.GITLAB_TOKEN)


@pytest.fixture(scope="session", autouse=True)
def allow_gitlab_webhooks(gitlab_client: Gitlab):
    gl_settings = gitlab_client.settings.get()
    gl_settings.allow_local_requests_from_web_hooks_and_services = True
    gl_settings.max_yaml_size_bytes = 50 * 1024 * 1024
    gl_settings.save()


@pytest.fixture()
def gitlab_group(gitlab_client: Gitlab):
    try:
        gitlab_client.groups.get("pytest").delete()
    except GitlabGetError:
        pass

    group: Group = gitlab_client.groups.create(
        {"name": "pytest", "path": "pytest", "visibility": "public"}
    )

    yield group

    group.delete()


@pytest.fixture()
def gitlab_project(gitlab_client: Gitlab, gitlab_group: Group, pr_build_cache_bucket: str, protected_build_cache_bucket: str, request: pytest.FixtureRequest):
    root_project = gitlab_client.projects.get("root/spack")

    # Create a fork of the project for this test
    fork: ProjectFork = root_project.forks.create({"namespace": gitlab_group.get_id()})

    # Wait for the fork to be created
    project: Project
    while (project := gitlab_client.projects.get(fork.get_id())).import_status != "finished":
        time.sleep(1)


    # See these docs for more info on Spack GitLab CI variables:
    # https://spack.readthedocs.io/en/latest/pipelines.html#environment-variables-affecting-pipeline-operation
    ci_variables = {
        # Force rebuild of all packages
        "SPACK_PRUNE_UP_TO_DATE": False,
        "SPACK_PRUNE_UNTOUCHED": False,
        # Only enable build_systems stack
        "SPACK_CI_ENABLE_STACKS": "build_systems",
        # Disable signing of packages. We don't want to sign packages in the test environment.
        "SPACK_REQUIRE_SIGNING": False,
        # Configure local minio build cache
        "PR_MIRROR_FETCH_DOMAIN": f"s3://{pr_build_cache_bucket}",
        "PR_MIRROR_PUSH_DOMAIN": f"s3://{pr_build_cache_bucket}",
        "PROTECTED_MIRROR_FETCH_DOMAIN": f"s3://{protected_build_cache_bucket}",
        "PROTECTED_MIRROR_PUSH_DOMAIN": f"s3://{protected_build_cache_bucket}",
        "S3_ENDPOINT_URL": "http://minio:9000",
        "AWS_ACCESS_KEY_ID": "minioAccessKey",
        "AWS_SECRET_ACCESS_KEY": "minioSecretKey",
        "AWS_REGION": "us-east-1",
    }
    for k, v in ci_variables.items():
        project.variables.create({"key": k, "value": v})

    project.ci_config_path = "share/spack/gitlab/cloud_pipelines/.gitlab-ci.yml"
    project.save()
    project.hooks.create({"url": "http://django:8000", "job_events": True})

    yield project

    project.delete()


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
