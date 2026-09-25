"""View tests.

These never touch a database: the GitLab query function is patched out, because the
point here is the behaviour around it -- the project allowlist, the caching, and what
gets rendered -- rather than the SQL, which is exercised against a real GitLab schema.
"""

from datetime import datetime, timezone

from django.core.cache import cache
from django.test import override_settings
import pytest

from analytics.pipeline_status.gitlab_queries import (
    FailedJob,
    Pipeline,
    PullRequestPipeline,
)

ALLOWED = ["spack/spack-packages", "spack/spack"]


@pytest.fixture(autouse=True)
def _clear_cache():
    # The cache is process-local and would otherwise leak between tests.
    cache.clear()
    yield
    cache.clear()


def _sample_pipeline(**overrides) -> PullRequestPipeline:
    root = Pipeline(
        id=1000,
        status="failed",
        created_at=datetime(2026, 9, 25, 10, 0, tzinfo=timezone.utc),
        started_at=datetime(2026, 9, 25, 10, 1, tzinfo=timezone.utc),
        finished_at=datetime(2026, 9, 25, 11, 1, tzinfo=timezone.utc),
        duration=3600,
    )
    defaults = {
        "project_path": "spack/spack-packages",
        "pr_number": 12345,
        "ref": "pr12345_fix/foo",
        "sha": "abc123de" * 5,
        "root": root,
        "child_pipelines": [],
        "job_status_counts": {"success": 2, "failed": 1},
        "failed_jobs": [
            FailedJob(
                id=201,
                name="build-some-package",
                stage="build",
                failure_reason="script_failure",
                allow_failure=False,
                pipeline_id=1000,
                is_trigger_job=False,
                started_at=datetime(2026, 9, 25, 10, 2, tzinfo=timezone.utc),
                finished_at=datetime(2026, 9, 25, 10, 12, tzinfo=timezone.utc),
            )
        ],
        "failed_jobs_truncated": False,
    }
    return PullRequestPipeline(**(defaults | overrides))


@pytest.fixture
def stub_query(monkeypatch):
    """Patch the GitLab query, recording the arguments it was called with."""
    calls = []

    def _stub(project_path, pr_number):
        calls.append((project_path, pr_number))
        return _sample_pipeline() if pr_number == 12345 else None

    monkeypatch.setattr("analytics.pipeline_status.views.get_pull_request_pipeline", _stub)
    return calls


@override_settings(PIPELINE_STATUS_ALLOWED_PROJECTS=ALLOWED)
def test_detail_page_renders_the_pipeline(client, stub_query):
    response = client.get("/pipelines/spack/spack-packages/pull/12345/")
    body = response.content.decode()

    assert response.status_code == 200
    assert "Pull request #12345" in body
    assert "pr12345_fix/foo" in body
    assert "build-some-package" in body
    assert "Script failure" in body
    # Links out to GitLab and GitHub, since this page deliberately does not replace them.
    assert "/-/jobs/201" in body
    assert "https://github.com/spack/spack-packages/pull/12345" in body


@override_settings(PIPELINE_STATUS_ALLOWED_PROJECTS=ALLOWED)
def test_missing_pipeline_is_explained_not_just_404(client, stub_query):
    response = client.get("/pipelines/spack/spack-packages/pull/999/")

    assert response.status_code == 404
    assert "No pipeline found" in response.content.decode()


@override_settings(PIPELINE_STATUS_ALLOWED_PROJECTS=ALLOWED)
def test_project_outside_the_allowlist_is_never_queried(client, stub_query):
    """The allowlist is the control that stops this page reaching a private project."""
    response = client.get("/pipelines/spack/some-private-repo/pull/1/")

    assert response.status_code == 404
    assert stub_query == [], "the GitLab database must not be queried at all"


@override_settings(PIPELINE_STATUS_ALLOWED_PROJECTS=ALLOWED)
@pytest.mark.parametrize("pr_number", [0, 10_000_000])
def test_out_of_range_pr_numbers_are_rejected(client, stub_query, pr_number):
    response = client.get(f"/pipelines/spack/spack-packages/pull/{pr_number}/")

    assert response.status_code == 404
    assert stub_query == []


@override_settings(PIPELINE_STATUS_ALLOWED_PROJECTS=ALLOWED)
def test_repeat_views_are_served_from_cache(client, stub_query):
    for _ in range(3):
        client.get("/pipelines/spack/spack-packages/pull/12345/")

    assert len(stub_query) == 1


@override_settings(PIPELINE_STATUS_ALLOWED_PROJECTS=ALLOWED)
def test_absent_pipelines_are_cached_too(client, stub_query):
    """Otherwise an unmirrored PR re-queries on every request."""
    for _ in range(3):
        client.get("/pipelines/spack/spack-packages/pull/999/")

    assert len(stub_query) == 1


@override_settings(PIPELINE_STATUS_ALLOWED_PROJECTS=ALLOWED)
def test_index_lists_the_allowed_projects(client):
    response = client.get("/pipelines/")
    body = response.content.decode()

    assert response.status_code == 200
    for project in ALLOWED:
        assert project in body


@override_settings(PIPELINE_STATUS_ALLOWED_PROJECTS=ALLOWED)
def test_index_form_redirects_to_the_canonical_url(client):
    response = client.get("/pipelines/", {"project": "spack/spack", "pr_number": "42"})

    assert response.status_code == 302
    assert response["Location"] == "/pipelines/spack/spack/pull/42/"


@override_settings(PIPELINE_STATUS_ALLOWED_PROJECTS=ALLOWED)
@pytest.mark.parametrize(
    "params",
    [
        # A project not on the allowlist must not become a redirect target.
        {"project": "evil/repo", "pr_number": "1"},
        {"project": "https://evil.example.com", "pr_number": "1"},
        {"project": "spack/spack", "pr_number": "not-a-number"},
    ],
)
def test_index_form_rejects_bad_input(client, params):
    response = client.get("/pipelines/", params)

    assert response.status_code == 400
    assert "Location" not in response


@override_settings(ROOT_URLCONF="analytics.urls_public")
def test_robots_txt_disallows_everything(client):
    response = client.get("/robots.txt")

    assert response.status_code == 200
    assert "Disallow: /" in response.content.decode()


@override_settings(ROOT_URLCONF="analytics.urls_public")
def test_public_urlconf_does_not_serve_the_webhook(client):
    """The internet-facing deployment must not expose the GitLab webhook handler.

    The webhook is unauthenticated and CSRF-exempt by necessity, and lives at the root
    path in the default urlconf. Keeping it out of this urlconf is the structural half
    of that guarantee; the gateway's path matching is the other half.
    """
    assert client.get("/").status_code == 404
    assert client.post("/", data="{}", content_type="application/json").status_code == 404


@override_settings(ROOT_URLCONF="analytics.urls", PIPELINE_STATUS_ALLOWED_PROJECTS=ALLOWED)
def test_default_urlconf_still_serves_the_webhook(client):
    """Guards against the reverse mistake: the webhook deployment still needs it."""
    # GET is rejected by the view's own method check, which is proof the route exists.
    assert client.get("/").status_code == 405
