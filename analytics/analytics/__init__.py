from typing import Any

from sentry_sdk import set_tag

from .celery import app as celery_app

__all__ = ("celery_app",)


def setup_gitlab_job_sentry_tags(job_input_data: dict[str, Any]) -> None:
    runner = job_input_data.get("runner") or {}
    if runner.get("description"):
        set_tag("is_uo", job_input_data["runner"]["description"].startswith("uo-"))

    set_tag("is_develop", job_input_data["ref"] == "develop")
    set_tag("build_status", job_input_data["build_status"])
