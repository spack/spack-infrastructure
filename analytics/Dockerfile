# Note: this is the Dockerfile for the production image. The development image is located
# inside the dev/ subdirectory.

FROM python:3.13-slim

# Install spack dependencies
RUN apt-get update && \
    apt-get install --no-install-recommends --yes \
    build-essential ca-certificates coreutils curl \
    environment-modules gfortran git gpg lsb-release \
    python3 python3-venv unzip zip \
    && rm -rf /var/lib/apt/lists/*

# Install spack
RUN git clone -c feature.manyFiles=true --depth 1 --branch v0.22.0 https://github.com/spack/spack.git /opt/spack

# Include spack import paths for python packages. Order is important
ENV PYTHONPATH "/opt/spack/lib/spack:$PYTHONPATH"
ENV PYTHONPATH "/opt/spack/lib/spack/external/_vendoring:$PYTHONPATH"
ENV PYTHONPATH "/opt/spack/lib/spack/external:$PYTHONPATH"


WORKDIR /app

COPY requirements.txt /app/requirements.txt

RUN pip install --upgrade uv
RUN uv pip install --system -r requirements.txt

COPY . .

# Collect the pipeline status page's CSS/JS so whitenoise can serve them. Done at build
# time so that the image is self-contained and a container can start without write
# access to anything. The settings module reads its configuration from the environment
# at import, so throwaway values are supplied here; none of them is used for anything
# beyond writing files into staticfiles/.
RUN DJANGO_SETTINGS_MODULE=analytics.settings.production \
    SECRET_KEY=collectstatic \
    ALLOWED_HOSTS=collectstatic \
    DB_USER=collectstatic DB_HOST=collectstatic DB_NAME=collectstatic DB_PASS=collectstatic \
    CELERY_BROKER_URL=redis://collectstatic \
    GITLAB_ENDPOINT=http://collectstatic GITLAB_TOKEN=collectstatic \
    GITLAB_DB_USER=collectstatic GITLAB_DB_HOST=collectstatic \
    GITLAB_DB_NAME=collectstatic GITLAB_DB_PASS=collectstatic GITLAB_DB_PORT=5432 \
    PROMETHEUS_URL=http://collectstatic \
    python manage.py collectstatic --noinput

RUN chmod +x ./entrypoint.sh
ENTRYPOINT [ "./entrypoint.sh" ]
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--access-logfile", "-", "analytics.wsgi"]
