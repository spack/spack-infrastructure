import typing
from functools import wraps

import gitlab
import requests
from cachetools import TTLCache, cached
from django.conf import settings
from gitlab.v4.objects import Project

T = typing.TypeVar("T")
P = typing.ParamSpec("P")


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
        timeout=15,
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
