FROM python:3.11-slim

ENV UV_PROJECT_ENVIRONMENT=/usr/local

WORKDIR /app

COPY pyproject.toml uv.lock /app/

RUN pip install --upgrade uv
RUN uv sync --frozen --no-dev --no-cache

COPY . .

CMD [ "python", "./snapshot_release_tags.py" ]
