FROM python:3.11

RUN apt-get update && apt-get install -y \
        gpg \
        gpg-agent && \
    apt-get autoremove --purge -y && \
    apt-get clean

ENV UV_PROJECT_ENVIRONMENT=/usr/local

WORKDIR /srcs
COPY pyproject.toml uv.lock ./

RUN pip install --upgrade uv
RUN uv sync --frozen --no-dev --no-cache

COPY retry_trigger_jobs.py /srcs/retry_trigger_jobs.py

ENTRYPOINT ["python", "retry_trigger_jobs.py"]
