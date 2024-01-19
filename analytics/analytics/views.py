from typing import Any
from django.http import HttpRequest, HttpResponse
import json
import re

import sentry_sdk

from analytics.job_log_uploader import upload_job_log
from .job_processor import process_job

BUILD_STAGE_REGEX = r"^stage-\d+$"


def webhook_handler(request: HttpRequest) -> HttpResponse:
    job_input_data: dict[str, Any] = json.loads(request.body)

    if job_input_data.get("object_kind") != "build":
        sentry_sdk.capture_message("Not a build event")
        return HttpResponse("Not a build event", status=400)

    if job_input_data["build_status"] in ["success", "failed"]:
        upload_job_log.delay(request.body)

    if (
        re.match(BUILD_STAGE_REGEX, job_input_data["build_stage"])
        and job_input_data["build_status"] == "success"
    ):
        process_job.delay(request.body)

    return HttpResponse("OK", status=200)
