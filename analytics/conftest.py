import os

# Set required env vars before Django (and any package that imports it) is loaded.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "analytics.settings.testing")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/0")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_PASS", "test")
os.environ.setdefault("GITLAB_DB_USER", "test")
os.environ.setdefault("GITLAB_DB_HOST", "localhost")
os.environ.setdefault("GITLAB_DB_NAME", "test")
os.environ.setdefault("GITLAB_DB_PASS", "test")
os.environ.setdefault("GITLAB_DB_PORT", "5432")
os.environ.setdefault("OPENSEARCH_ENDPOINT", "http://localhost:9200")
os.environ.setdefault("OPENSEARCH_USERNAME", "test")
os.environ.setdefault("OPENSEARCH_PASSWORD", "test")
os.environ.setdefault("GITLAB_ENDPOINT", "https://gitlab.example.com")
os.environ.setdefault("GITLAB_TOKEN", "test")
os.environ.setdefault("PROMETHEUS_URL", "http://localhost:9090")

import django  # noqa: E402

django.setup()
