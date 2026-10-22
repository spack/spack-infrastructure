FROM python:3.11

RUN apt-get update && apt-get install -y \
        gpg \
        gpg-agent && \
    apt-get autoremove --purge -y && \
    apt-get clean

ENV UV_PROJECT_ENVIRONMENT=/usr/local

WORKDIR /srcs
COPY pyproject.toml uv.lock ./

COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /uvx /bin/
RUN uv sync --frozen --no-dev --no-cache

COPY pkg /srcs/pkg
COPY --chmod=755 migrate.sh /srcs/migrate.sh

ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "-m", "pkg.publish"]
