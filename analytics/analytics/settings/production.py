import logging
import os

import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.pure_eval import PureEvalIntegration

from ._utils import string_to_list
from .base import *  # noqa: F403

SECRET_KEY = os.environ["SECRET_KEY"]

CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_CONCURRENCY = None

ALLOWED_HOSTS = string_to_list(os.environ["ALLOWED_HOSTS"])

sentry_sdk.init(
    integrations=[
        LoggingIntegration(level=logging.INFO, event_level=logging.WARNING),
        DjangoIntegration(),
        CeleryIntegration(monitor_beat_tasks=True),
        PureEvalIntegration(),
    ],
    in_app_include=["analytics"],
    # Send traces for non-exception events too
    attach_stacktrace=True,
    # Submit request User info from Django
    send_default_pii=True,
    traces_sample_rate=0.01,
    profiles_sample_rate=0.01,
)
