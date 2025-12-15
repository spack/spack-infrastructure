from dataclasses import dataclass
from functools import wraps
import json
import typing

from cachetools import TTLCache, cached
from django.conf import settings
from django.db import connections
import gitlab
from gitlab.v4.objects import Project
import requests
import sentry_sdk

T = typing.TypeVar("T")
P = typing.ParamSpec("P")


class JobMetadataNotFound(Exception):
    pass


@dataclass(frozen=True)
class RetryInfo:
    is_retry: bool
    is_manual_retry: bool
    attempt_number: int
    final_attempt: bool


def get_job_retry_data(
    job_id: int, job_name: str, job_pipeline_id: int, job_failure_reason: str
) -> RetryInfo:
    with connections["gitlab"].cursor() as cursor:
        # In gitlab, the pipeline ID is stored as `commit_id`.
        # The prior attempts for a given job are all jobs with a lower id, the same commit_id, and
        # the same name. 
        # It's important to filter for a lower job id in the event that the webhook is delayed or
        # received out of order.
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM p_ci_builds
            WHERE id < %(job_id)s
            AND commit_id = %(commit_id)s
            AND name = %(job_name)s
            """,
            {"job_id": job_id, "job_name": job_name, "commit_id": job_pipeline_id},
        )
        attempt_number = cursor.fetchone()[0] + 1

        cursor.execute(
            """
            SELECT bm.config_options->>'retry'
            FROM p_ci_builds_metadata bm
            WHERE bm.build_id = %(job_id)s
            """,
            {"job_id": job_id},
        )
        job = cursor.fetchone()
        # This is a temporary workaround for GitLab 18.6.0.
        if job is None:
            raise JobMetadataNotFound(job_id)
        if not job[0]:
            # config_options->>retry should always be defined for non-trigger (aka Ci::Bridge)
            # jobs in spack. this is an edge case where a job in gitlab isn't explicitly
            # configured for retries at all.
            sentry_sdk.capture_message(f"Job {job_id} missing retry configuration.")
            # this is the default retry configuration for gitlab
            # see https://docs.gitlab.com/ee/ci/yaml/#retry
            retry_config = {
                "max": 0,
                "when": ["always"],
            }
        else:
            retry_config = json.loads(job[0])

        retry_max = retry_config["max"]
        # A non-retryable job can either have an explicit max of zero, or no max at all.
        # If the job is not retryable, the 'when' key will not exist
        if retry_max in (0, None):
            retry_reasons = []
        # If the job is retryable, the 'when' key will be a list of reasons to retry
        else:
            retry_reasons = retry_config["when"]
        # final_attempt is defined as an attempt that won't be retried for the retry_reasons
        # or because it's gone beyond the max number of retries.
        retryable_by_reason = "always" in retry_reasons or job_failure_reason in retry_reasons
        retryable_by_number = attempt_number <= retry_max
        final_attempt = not (retryable_by_reason and retryable_by_number)

        return RetryInfo(
            is_retry=attempt_number > 1,
            # manual retries are all retries that are not part of the original job
            is_manual_retry=attempt_number > retry_max + 1,
            attempt_number=attempt_number,
            final_attempt=final_attempt,
        )


def get_job_exit_code(job_id: int) -> int | None:
    with connections["gitlab"].cursor() as cursor:
        cursor.execute(
            """
            SELECT exit_code
            FROM p_ci_builds_metadata
            WHERE build_id = %(job_id)s
            """,
            {"job_id": job_id},
        )
        result = cursor.fetchone()

    return result[0] if result else None


# This is useful because we currently experience timeouts when accessing gitlab through
# its external IP address. If that is changed or if the underlying issue is resolved,
# this will not be necessary
def retry_gitlab_timeout(func: typing.Callable[P, T]) -> typing.Callable[P, T]:
    """A decorator function to retry gitlab read timeouts."""

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        while True:
            try:
                return func(*args, **kwargs)
            except requests.exceptions.ReadTimeout:
                pass

    return wrapper


@retry_gitlab_timeout
@cached(cache=TTLCache(maxsize=1, ttl=60 * 30))
def get_gitlab_handle():
    return gitlab.Gitlab(
        settings.GITLAB_ENDPOINT,
        settings.GITLAB_TOKEN,
        retry_transient_errors=True,
        timeout=30,
    )


@retry_gitlab_timeout
@cached(cache=TTLCache(maxsize=1024, ttl=60 * 30))
def get_gitlab_project(project_id: int):
    gl = get_gitlab_handle()
    return gl.projects.get(project_id)


@retry_gitlab_timeout
@cached(cache=TTLCache(maxsize=1024, ttl=60 * 30))
def get_gitlab_job(project: Project, job_id: int):
    return project.jobs.get(job_id)
