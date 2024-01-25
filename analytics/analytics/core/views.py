import json
import re
from typing import Any

from django.http import HttpRequest, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import sentry_sdk

from analytics.core.job_failure_classifier import upload_job_failure_classification
from analytics.core.job_log_uploader import upload_job_log
from analytics.job_processor import process_job

BUILD_STAGE_REGEX = r"^stage-\d+$"


@require_http_methods(["POST"])
@csrf_exempt
def webhook_handler(request: HttpRequest) -> HttpResponse:
    job_input_data: dict[str, Any] = json.loads(request.body)

    if job_input_data.get("object_kind") != "build":
        sentry_sdk.capture_message("Not a build event")
        return HttpResponse("Not a build event", status=400)

    if job_input_data["build_status"] in ["success", "failed"]:
        upload_job_log.delay(request.body)

    if job_input_data["build_status"] == "failed":
        upload_job_failure_classification.delay(request.body)

    if (
        re.match(BUILD_STAGE_REGEX, job_input_data["build_stage"])
        and job_input_data["build_status"] == "success"
    ):
        process_job.delay(request.body)

    return HttpResponse("OK", status=200)
