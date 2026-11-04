FROM python:3.11

ENV UV_PROJECT_ENVIRONMENT=/usr/local

WORKDIR /srcs
COPY pyproject.toml uv.lock ./

COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /uvx /bin/
RUN uv sync --frozen --no-dev --no-cache

COPY retry_trigger_jobs.py /srcs/retry_trigger_jobs.py

ENTRYPOINT ["python", "retry_trigger_jobs.py"]
