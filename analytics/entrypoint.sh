#!/bin/sh
set -e

# Always run migrate when invoking this image
python manage.py migrate

# This will exec the CMD passed to docker, i.e. "gunicorn" or "celery"
exec "$@"
