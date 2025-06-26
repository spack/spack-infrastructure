# Note: this is the Dockerfile for the production image. The development image is located
# inside the dev/ subdirectory.

FROM python:3.13-slim

# Install spack dependencies
RUN apt-get update && \
    apt-get install --no-install-recommends --yes \
    build-essential ca-certificates coreutils curl \
    environment-modules gfortran git gpg lsb-release \
    python3 python3-distutils python3-venv unzip zip \
    && rm -rf /var/lib/apt/lists/*

# Install spack
RUN git clone -c feature.manyFiles=true --depth 1 --branch v0.22.0 https://github.com/spack/spack.git /opt/spack

# Include spack import paths for python packages. Order is important
ENV PYTHONPATH "/opt/spack/lib/spack:$PYTHONPATH"
ENV PYTHONPATH "/opt/spack/lib/spack/external/_vendoring:$PYTHONPATH"
ENV PYTHONPATH "/opt/spack/lib/spack/external:$PYTHONPATH"


WORKDIR /app

COPY requirements.txt /app/requirements.txt

RUN pip install --upgrade pip
RUN pip install -r requirements.txt

COPY . .

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--access-logfile", "-", "analytics.wsgi"]
