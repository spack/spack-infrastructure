import json
from typing import Any

import sentry_sdk
from django.http import HttpRequest, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from analytics.core.job_log_uploader import store_job_data
from analytics.job_processor import process_job


@require_http_methods(["POST"])
@csrf_exempt
def webhook_handler(request: HttpRequest) -> HttpResponse:
    job_input_data: dict[str, Any] = json.loads(request.body)

    if job_input_data.get("object_kind") != "build":
        sentry_sdk.capture_message("Not a build event")
        return HttpResponse("Not a build event", status=400)

    if job_input_data["build_status"] not in ["success", "failed"]:
        return HttpResponse("Build job not finished. Skipping.", status=200)

    # Store gitlab job log and failure data in opensearch
    store_job_data.delay(request.body)

    # Store job data in postgres DB
    process_job.delay(request.body)

    return HttpResponse("OK", status=200)
