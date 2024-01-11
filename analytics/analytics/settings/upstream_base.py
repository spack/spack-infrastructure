import os

from ._logging import _filter_favicon_requests, _filter_static_requests
from ._utils import string_to_list

# Login/auth
LOGIN_REDIRECT_URL = "/"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.ScryptPasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
]

# Celery
CELERY_BROKER_CONNECTION_TIMEOUT = 30
CELERY_BROKER_HEARTBEAT = None
CELERY_BROKER_POOL_LIMIT = 1
CELERY_BROKER_URL = os.environ["CELERY_BROKER_URL"]
CELERY_EVENT_QUEUE_EXPIRES = 60
CELERY_RESULT_BACKEND = None
CELERY_TASK_ACKS_ON_FAILURE_OR_TIMEOUT = True
CELERY_TASK_REJECT_ON_WORKER_LOST = False
CELERY_WORKER_CANCEL_LONG_RUNNING_TASKS_ON_CONNECTION_LOSS = True
CELERY_WORKER_CONCURRENCY = 1
CELERY_WORKER_PREFETCH_MULTIPLIER = 1

# CORS
CORS_ALLOW_CREDENTIALS = False
CORS_ORIGIN_WHITELIST = string_to_list(os.environ.get("DJANGO_CORS_ORIGIN_WHITELIST", ""))
CORS_ORIGIN_REGEX_WHITELIST = string_to_list(
    os.environ.get("DJANGO_CORS_ORIGIN_REGEX_WHITELIST", "")
)

# Database config
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CONN_MAX_AGE = 600
CONN_HEALTH_CHECKS = True
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "USER": os.environ["DB_USER"],
        "HOST": os.environ["DB_HOST"],
        "NAME": os.environ["DB_NAME"],
        "PASSWORD": os.environ["DB_PASS"],
    }
}

# Logging config
LOGGING = {
    "version": 1,
    # Replace existing logging configuration
    "incremental": False,
    # This redefines all of Django's declared loggers, but most loggers are implicitly
    # declared on usage, and should not be disabled. They often propagate their output
    # to the root anyway.
    "disable_existing_loggers": False,
    "formatters": {"rich": {"datefmt": "[%X]"}},
    "filters": {
        "filter_favicon_requests": {
            "()": "django.utils.log.CallbackFilter",
            "callback": _filter_favicon_requests,
        },
        "filter_static_requests": {
            "()": "django.utils.log.CallbackFilter",
            "callback": _filter_static_requests,
        },
    },
    "handlers": {
        "console": {
            "class": "rich.logging.RichHandler",
            "formatter": "rich",
            "filters": ["filter_favicon_requests", "filter_static_requests"],
        },
    },
    # Existing loggers actually contain direct (non-string) references to existing handlers,
    # so after redefining handlers, all existing loggers must be redefined too
    "loggers": {
        # Configure the root logger to output to the console
        "": {"level": "INFO", "handlers": ["console"], "propagate": False},
        # Django defines special configurations for the "django" and "django.server" loggers,
        # but we will manage all content at the root logger instead, so reset those
        # configurations.
        "django": {
            "handlers": [],
            "level": "NOTSET",
            "propagate": True,
        },
        "django.server": {
            "handlers": [],
            "level": "NOTSET",
            "propagate": True,
        },
    },
}

# Storage config
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

# Misc
STATIC_URL = "static/"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    },
]
TIME_ZONE = "UTC"
USE_TZ = True
