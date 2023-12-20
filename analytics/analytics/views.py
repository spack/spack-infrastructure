from typing import Any
from django.http import HttpRequest, HttpResponse
import json

import sentry_sdk

from analytics.job_log_uploader import upload_job_log


def webhook_handler(request: HttpRequest) -> HttpResponse:
    job_input_data: dict[str, Any] = json.loads(request.body)

    if job_input_data.get("object_kind") != "build":
        sentry_sdk.capture_message("Not a build event")
        return HttpResponse("Not a build event", status=400)

    upload_job_log.delay(request.body)

    return HttpResponse("OK", status=200)
