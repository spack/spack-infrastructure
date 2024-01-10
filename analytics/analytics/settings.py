import os
from pathlib import Path

import sentry_sdk

sentry_sdk.init(
    # Sample only 1% of transactions
    traces_sample_rate=0.01,
)

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

ROOT_URLCONF = "analytics.urls"

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

# Application definition
INSTALLED_APPS = [
    "analytics",
    "django_extensions",
]

# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ["DB_NAME"],
        "USER": os.environ["DB_USER"],
        "PASSWORD": os.environ["DB_PASS"],
        "HOST": os.environ["DB_HOST"],
        "PORT": os.environ.get("DB_PORT", 5432),
    }
}

# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Default primary key field type
# https://docs.djangoproject.com/en/4.2/ref/settings/#default-auto-field
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

SECRET_KEY = os.environ["SECRET_KEY"]

CELERY_BROKER_URL = os.environ["CELERY_BROKER_URL"]

# These settings are mostly copied from https://github.com/girder/django-composed-configuration/blob/master/composed_configuration/_celery.py
CELERY_RESULT_BACKEND = None
CELERY_TASK_ACKS_LATE = not DEBUG
CELERY_TASK_REJECT_ON_WORKER_LOST = False
CELERY_TASK_ACKS_ON_FAILURE_OR_TIMEOUT = True
CELERY_WORKER_CANCEL_LONG_RUNNING_TASKS_ON_CONNECTION_LOSS = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_WORKER_CONCURRENCY = 1 if DEBUG else None

# Custom settings

OPENSEARCH_ENDPOINT = os.environ["OPENSEARCH_ENDPOINT"]
OPENSEARCH_USERNAME = os.environ["OPENSEARCH_USERNAME"]
OPENSEARCH_PASSWORD = os.environ["OPENSEARCH_PASSWORD"]

GITLAB_ENDPOINT: str = os.environ["GITLAB_ENDPOINT"]
GITLAB_TOKEN: str = os.environ["GITLAB_TOKEN"]

SPACK_PROMETHEUS_ENDPOINT: str = os.environ.get("SPACK_PROMETHEUS_ENDPOINT")
