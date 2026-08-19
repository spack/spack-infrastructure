FROM python:3.11-slim

ENV UV_PROJECT_ENVIRONMENT=/usr/local

WORKDIR /scripts/

COPY pyproject.toml uv.lock ./
RUN pip install --upgrade uv
RUN uv sync --frozen --no-dev --no-cache
COPY backup.py ./

ENTRYPOINT [ "python", "./backup.py"]
