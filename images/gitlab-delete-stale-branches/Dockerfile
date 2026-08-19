FROM python:3

ENV UV_PROJECT_ENVIRONMENT=/usr/local

WORKDIR /scripts/
COPY pyproject.toml uv.lock ./
RUN pip install --upgrade uv
RUN uv sync --frozen --no-dev --no-cache
COPY delete_stale_branches.py ./

ENTRYPOINT [ "python", "./delete_stale_branches.py"]
