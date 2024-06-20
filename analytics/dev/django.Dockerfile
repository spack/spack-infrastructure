FROM python:3.10-slim
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
    python3 python3-distutils python3-venv unzip zip

# Cleanup
RUN rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Only copy the setup.py, it will still force all install_requires to be installed,
# but find_packages() will find nothing (which is fine). When Docker Compose mounts the real source
# over top of this directory, the .egg-link in site-packages resolves to the mounted directory
# and all package modules are importable.
COPY ./setup.py /opt/django-project/setup.py
RUN pip install --editable /opt/django-project[dev]


# Install spack
RUN git clone -c feature.manyFiles=true https://github.com/spack/spack.git /opt/spack
RUN cd /opt/spack && git checkout v0.22.0

# Include spack import paths for python packages. Order is important
ENV PYTHONPATH "/opt/spack/lib/spack:$PYTHONPATH"
ENV PYTHONPATH "/opt/spack/lib/spack/external/_vendoring:$PYTHONPATH"
ENV PYTHONPATH "/opt/spack/lib/spack/external:$PYTHONPATH"


# Use a directory name which will never be an import name, as isort considers this as first-party.
WORKDIR /opt/django-project
