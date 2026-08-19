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


# Install dependencies into the image's system prefix rather than a project .venv
ENV UV_PROJECT_ENVIRONMENT=/usr/local

WORKDIR /app

COPY pyproject.toml uv.lock /app/

RUN pip install --upgrade uv
# --no-install-project: the app itself is not installed, it's run from /app below
RUN uv sync --frozen --no-install-project --no-cache

COPY . .

RUN chmod +x ./entrypoint.sh
ENTRYPOINT [ "./entrypoint.sh" ]
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--access-logfile", "-", "analytics.wsgi"]
