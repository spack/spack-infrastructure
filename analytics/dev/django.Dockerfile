FROM python:3.13-slim
# Install system libraries for Python packages:
# * psycopg2
RUN apt-get update && \
    apt-get install --no-install-recommends --yes \
    libpq-dev gcc libc6-dev git

# Install spack dependencies
RUN apt-get update && \
    apt-get install --no-install-recommends --yes \
    build-essential ca-certificates coreutils curl \
    environment-modules gfortran git gpg lsb-release \
    python3 python3-venv unzip zip

# Cleanup
RUN rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Only copy the dependency metadata, so that the layer is cached independently of the source.
# --no-install-project keeps the app itself out of site-packages; Docker Compose mounts the real
# source over /opt/django-project and PYTHONPATH (set below) makes its modules importable.
ENV UV_PROJECT_ENVIRONMENT=/usr/local
COPY ./pyproject.toml ./uv.lock /opt/django-project/
RUN pip install --upgrade uv
RUN uv sync --project /opt/django-project --frozen --no-install-project --extra dev --no-cache


# Install spack
RUN git clone -c feature.manyFiles=true https://github.com/spack/spack.git /opt/spack
RUN cd /opt/spack && git checkout v0.22.0

# Include spack import paths for python packages. Order is important
ENV PYTHONPATH="/opt/spack/lib/spack"
ENV PYTHONPATH="/opt/spack/lib/spack/external/_vendoring:${PYTHONPATH}"
ENV PYTHONPATH="/opt/spack/lib/spack/external:${PYTHONPATH}"

# Make the bind-mounted project source importable
ENV PYTHONPATH="/opt/django-project:${PYTHONPATH}"


# Use a directory name which will never be an import name, as isort considers this as first-party.
WORKDIR /opt/django-project
