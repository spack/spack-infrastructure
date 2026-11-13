FROM python:3.13

RUN apt-get update && apt-get install -y \
        gpg \
        gpg-agent && \
    apt-get autoremove --purge -y && \
    apt-get clean

# Install the AWS CLI (used by pkg/ via subprocess). v2 is self-contained, so unlike the
# awscli PyPI package it doesn't pin the boto3/botocore versions used by pkg/.
COPY --from=amazon/aws-cli:2.40.0 /usr/local/aws-cli /usr/local/aws-cli
RUN ln -s /usr/local/aws-cli/v2/current/bin/aws /usr/local/bin/aws
ENV AWS_PAGER=""

ENV UV_PROJECT_ENVIRONMENT=/usr/local

WORKDIR /srcs
COPY pyproject.toml uv.lock ./

COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /uvx /bin/
RUN uv sync --frozen --no-dev --no-cache

# aws-encryption-cli (used by migrate.sh) gets its own isolated environment, for the
# same reason as the AWS CLI above. It imports pkg_resources, which setuptools 82 removed.
RUN UV_TOOL_DIR=/opt/uv-tools UV_TOOL_BIN_DIR=/usr/local/bin \
    uv tool install --no-cache aws-encryption-sdk-cli==4.2.0 --with "setuptools<82"

COPY pkg /srcs/pkg
COPY --chmod=755 migrate.sh /srcs/migrate.sh

ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "-m", "pkg.publish"]
