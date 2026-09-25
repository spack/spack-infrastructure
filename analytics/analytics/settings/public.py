"""Settings for the internet-facing pipeline status deployment.

This is the only part of the analytics project that is reachable from the internet,
so it is configured separately from the webhook handler rather than sharing its
settings. The differences are all narrowing: a urlconf that does not contain the
webhook, HTTPS enforcement, and a hard cap on how long a GitLab query may run.

Used by k8s/production/custom/pipeline-status/.
"""

import os

from .production import *  # noqa: F403

# Serve only the pipeline status page. The webhook handler is unauthenticated and
# CSRF-exempt by necessity, and is simply absent from this urlconf.
ROOT_URLCONF = "analytics.urls_public"

# The ALB terminates TLS, so Django only ever sees plain HTTP and has to be told when
# the original request was secure.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True

# HSTS for this hostname only: deliberately no includeSubDomains and no preload, since
# the same gateway serves other *.spack.io names and this deployment should not make
# that decision on their behalf. Raise the duration once it has been running happily.
SECURE_HSTS_SECONDS = 3600
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Cap how long any single statement may run against GitLab's database. This belongs
# here rather than in base.py because the analytics backfill commands legitimately run
# queries far longer than this against the same database.
GITLAB_DB_STATEMENT_TIMEOUT_MS = int(os.environ.get("GITLAB_DB_STATEMENT_TIMEOUT_MS", "10000"))
DATABASES["gitlab"] = DATABASES["gitlab"] | {  # noqa: F405
    "OPTIONS": {
        "options": f"-c statement_timeout={GITLAB_DB_STATEMENT_TIMEOUT_MS}",
    },
}
