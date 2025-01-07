import logging
from typing import Optional

from django.http import HttpRequest


def _filter_favicon_requests(record: logging.LogRecord) -> bool:
    if record.name == "django.request":
        request: HttpRequest | None = getattr(record, "request", None)
        if request and request.path == "/favicon.ico":
            return False

    if (
        record.name == "django.server"
        and isinstance(record.args, tuple)
        and len(record.args) >= 1
        and str(record.args[0]).startswith("GET /favicon.ico ")
    ):
        return False

    return True


def _filter_static_requests(record: logging.LogRecord) -> bool:
    if (
        record.name == "django.server"
        and isinstance(record.args, tuple)
        and len(record.args) >= 1
        and str(record.args[0]).startswith("GET /static/")
    ):
        return False

    return True
