import os
from pathlib import Path

from .upstream_base import *  # noqa: F403,F401

# Install local apps first, to ensure any overridden resources are found first
INSTALLED_APPS = [
    "analytics.core.apps.CoreConfig",
    "analytics.pipeline_status.apps.PipelineStatusConfig",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.humanize",
    "django.contrib.postgres",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "corsheaders",
    "django_extensions",
    "girder_utils",
]

# Middleware
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "analytics.pipeline_status.middleware.SecurityHeadersMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# Databases
DATABASES |= {
    "gitlab": {
        "ENGINE": "django.db.backends.postgresql",
        "USER": os.environ["GITLAB_DB_USER"],
        "HOST": os.environ["GITLAB_DB_HOST"],
        "NAME": os.environ["GITLAB_DB_NAME"],
        "PASSWORD": os.environ["GITLAB_DB_PASS"],
        "PORT": os.environ["GITLAB_DB_PORT"],
    },
}

# django-extensions
RUNSERVER_PLUS_PRINT_SQL_TRUNCATE = None
SHELL_PLUS_PRINT_SQL = True
SHELL_PLUS_PRINT_SQL_TRUNCATE = None

# Misc
BASE_DIR = Path(__file__).resolve(strict=True).parent.parent.parent
STATIC_ROOT = BASE_DIR / "staticfiles"
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
WSGI_APPLICATION = "analytics.wsgi.application"
ROOT_URLCONF = "analytics.urls"

# Spack specific settings
GITLAB_ENDPOINT = os.environ["GITLAB_ENDPOINT"]
GITLAB_TOKEN = os.environ["GITLAB_TOKEN"]

PROMETHEUS_URL = os.environ["PROMETHEUS_URL"]

# Caching
#
# An in-process cache is enough for what it is used for: collapsing repeated views of
# the same pipeline into one set of GitLab queries. It is deliberately not shared
# between pods -- there is nothing here worth the operational cost of a shared cache,
# and a per-pod cache degrades gracefully.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "analytics",
    },
}

# Pipeline status page
#
# The page reads GitLab's database directly and therefore bypasses GitLab's own
# authorization. This allowlist is a security boundary rather than a convenience: only
# these projects can be queried, so the page cannot be made to reveal a private
# project's pipelines. Both are public, and both are mirrored from GitHub under the
# same path by the gh-gl-sync CronJobs, so one list covers the GitHub repo and the
# GitLab project alike.
PIPELINE_STATUS_ALLOWED_PROJECTS = ["spack/spack-packages", "spack/spack"]

# How long a pipeline summary may be reused. Short enough that the page still reads as
# live, long enough that reloads and concurrent viewers collapse into a single set of
# queries.
PIPELINE_STATUS_CACHE_SECONDS = 15

# How often the page offers to reload itself, for someone watching a running pipeline.
PIPELINE_STATUS_REFRESH_SECONDS = 30
