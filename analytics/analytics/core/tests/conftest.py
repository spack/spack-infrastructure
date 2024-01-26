from typing import cast
from uuid import uuid4

from django.conf import settings
from gitlab import Gitlab
from gitlab.v4.objects import Project
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
def allow_gitlab_webhooks(gitlab_client):
    gl_settings = gitlab_client.settings.get()
    gl_settings.allow_local_requests_from_web_hooks_and_services = True
    gl_settings.save()


@pytest.fixture()
def gitlab_project(gitlab_client: Gitlab, allow_gitlab_webhooks):
    project = cast(Project, gitlab_client.projects.create({"name": f"test-project-{uuid4()}"}))
    project.hooks.create({"url": 'http://django:8000', 'job_events': True})
    yield project
    project.delete()
