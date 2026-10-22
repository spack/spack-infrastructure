FROM python:3

ENV UV_PROJECT_ENVIRONMENT=/usr/local

WORKDIR /scripts/
COPY pyproject.toml uv.lock ./
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /uvx /bin/
RUN uv sync --frozen --no-dev --no-cache
COPY skipped_pipelines.py ./

ENTRYPOINT [ "python", "./skipped_pipelines.py"]
