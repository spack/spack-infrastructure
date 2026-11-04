FROM python:3

# Install the AWS CLI. v2 is self-contained, so unlike the awscli PyPI package it
# doesn't pin the boto3/botocore versions installed below.
COPY --from=amazon/aws-cli:2.39.3 /usr/local/aws-cli /usr/local/aws-cli
RUN ln -s /usr/local/aws-cli/v2/current/bin/aws /usr/local/bin/aws
ENV AWS_PAGER=""

ENV UV_PROJECT_ENVIRONMENT=/usr/local

WORKDIR /scripts/
COPY pyproject.toml uv.lock ./
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /uvx /bin/
RUN uv sync --frozen --no-dev --no-cache

ENTRYPOINT ["/bin/bash"]
