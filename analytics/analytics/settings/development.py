import os

from ._docker import _AlwaysContains, _is_docker
from .base import *  # noqa: F403

DEBUG = True
SECRET_KEY = "insecuresecret"

ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
CORS_ORIGIN_REGEX_WHITELIST = [r"^https?://localhost:\d+$", r"^https?://127\.0\.0\.1:\d+$"]

# When in Docker, the bridge network sends requests from the host machine exclusively via a
# dedicated IP address. Since there's no way to determine the real origin address,
# consider any IP address (though actually this will only be the single dedicated address) to
# be internal. This relies on the host to set up appropriate firewalls for Docker, to prevent
# access from non-internal addresses.
INTERNAL_IPS = _AlwaysContains() if _is_docker() else ["127.0.0.1"]

CELERY_TASK_ACKS_LATE = False
CELERY_WORKER_CONCURRENCY = 1

DEBUG_TOOLBAR_CONFIG = {
    "RESULTS_CACHE_SIZE": 250,
    "PRETTIFY_SQL": False,
}

INSTALLED_APPS += ["debug_toolbar"]  # noqa: F405
MIDDLEWARE = ["debug_toolbar.middleware.DebugToolbarMiddleware"] + MIDDLEWARE  # noqa: F405
