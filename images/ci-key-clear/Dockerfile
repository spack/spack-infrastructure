FROM python:3.14

ENV UV_PROJECT_ENVIRONMENT=/usr/local

WORKDIR /scripts/
COPY pyproject.toml uv.lock ./
RUN pip install --upgrade uv
RUN uv sync --frozen --no-dev --no-cache
COPY delete_aws_admin_access_keys.py ./

ENTRYPOINT [ "python", "./delete_aws_admin_access_keys.py"]
