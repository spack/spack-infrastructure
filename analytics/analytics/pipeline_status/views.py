"""Views for the pipeline status page.

This page is internet-facing and reads GitLab's database directly, which means it
bypasses GitLab's own authorization. Two things follow from that, and both are
enforced here rather than left to configuration:

  * only projects in PIPELINE_STATUS_ALLOWED_PROJECTS may be queried, so the page
    can never be pointed at a private project's pipelines; and
  * every response is cached briefly, so that traffic to the page cannot be turned
    into unbounded query load against the GitLab database.
"""

from django.conf import settings
from django.core.cache import cache
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET

from analytics.pipeline_status.gitlab_queries import (
    PullRequestPipeline,
    get_pull_request_pipeline,
)

# GitHub PR numbers are nowhere near this, but the number reaches a LIKE pattern, so
# give it an explicit ceiling rather than accepting arbitrarily long digit strings.
MAX_PR_NUMBER = 9_999_999

# Sentinel stored in the cache to record "we looked, and there is no pipeline". Without
# it, a PR that hasn't been mirrored yet would re-query on every single request, which
# is exactly the case a crawler or an impatient reload is most likely to produce.
_NO_PIPELINE = "no-pipeline"


def _allowed_projects() -> list[str]:
    return list(settings.PIPELINE_STATUS_ALLOWED_PROJECTS)


def _resolve_project(org: str, repo: str) -> str:
    """Return the validated `org/repo` path, or raise Http404 if it isn't allowlisted."""
    project_path = f"{org}/{repo}"
    if project_path not in _allowed_projects():
        raise Http404(f"Unknown project {project_path!r}")

    return project_path


def _cached_pull_request_pipeline(project_path: str, pr_number: int) -> PullRequestPipeline | None:
    cache_key = f"pipeline-status:{project_path}:{pr_number}"
    cached_value = cache.get(cache_key)
    if cached_value is not None:
        return None if cached_value == _NO_PIPELINE else cached_value

    pipeline = get_pull_request_pipeline(project_path, pr_number)
    cache.set(
        cache_key,
        _NO_PIPELINE if pipeline is None else pipeline,
        timeout=settings.PIPELINE_STATUS_CACHE_SECONDS,
    )

    return pipeline


@require_GET
def index(request: HttpRequest) -> HttpResponse:
    """Landing page: a form to jump to a PR's pipeline.

    The form submits via GET, so a submission can be answered with a redirect to the
    canonical, linkable URL for that PR.
    """
    projects = _allowed_projects()

    submitted_project = request.GET.get("project", "")
    submitted_pr_number = request.GET.get("pr_number", "").strip()
    if submitted_project and submitted_pr_number:
        # Validate before reversing: `project` comes from the query string, and we
        # only ever build a redirect out of values we recognise.
        if submitted_project in projects and submitted_pr_number.isdigit():
            org, _, repo = submitted_project.partition("/")
            return redirect(
                reverse(
                    "pipeline-status:pull-request",
                    kwargs={
                        "org": org,
                        "repo": repo,
                        "pr_number": int(submitted_pr_number),
                    },
                )
            )

        return render(
            request,
            "pipeline_status/index.html",
            {
                "projects": projects,
                "error": "Enter a PR number and pick one of the listed repositories.",
                "submitted_project": submitted_project,
                "submitted_pr_number": submitted_pr_number,
                "cache_seconds": settings.PIPELINE_STATUS_CACHE_SECONDS,
            },
            status=400,
        )

    return render(
        request,
        "pipeline_status/index.html",
        {
            "projects": projects,
            "default_project": projects[0] if projects else "",
            "cache_seconds": settings.PIPELINE_STATUS_CACHE_SECONDS,
        },
    )


@require_GET
def pull_request(request: HttpRequest, org: str, repo: str, pr_number: int) -> HttpResponse:
    """Pipeline status and failed jobs for a single GitHub PR."""
    project_path = _resolve_project(org, repo)
    if pr_number < 1 or pr_number > MAX_PR_NUMBER:
        raise Http404(f"PR number {pr_number} out of range")

    pipeline = _cached_pull_request_pipeline(project_path, pr_number)

    context = {
        "project_path": project_path,
        "pr_number": pr_number,
        "pipeline": pipeline,
        "github_url": f"https://github.com/{project_path}/pull/{pr_number}",
        "gitlab_project_url": f"{settings.GITLAB_ENDPOINT.rstrip('/')}/{project_path}",
        "refresh_seconds": settings.PIPELINE_STATUS_REFRESH_SECONDS,
        "cache_seconds": settings.PIPELINE_STATUS_CACHE_SECONDS,
    }

    # A PR with no pipeline is a perfectly ordinary state -- the sync job runs every
    # five minutes, and pipelines are deliberately deferred -- so explain it rather
    # than showing a bare error. It is still a 404: there is no pipeline at this URL.
    if pipeline is None:
        return render(request, "pipeline_status/no_pipeline.html", context, status=404)

    return render(request, "pipeline_status/pull_request.html", context)


@require_GET
def robots_txt(request: HttpRequest) -> HttpResponse:
    """Ask crawlers to stay away.

    Every PR number is a distinct URL backed by live database queries, so an
    indexer walking the space would generate real load for no benefit to anyone.
    """
    return HttpResponse("User-agent: *\nDisallow: /\n", content_type="text/plain")
