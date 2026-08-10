FROM ghcr.io/astral-sh/uv:debian

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY main.py /main.py
COPY pyproject.toml /pyproject.toml
COPY uv.lock /uv.lock

# Install dependencies here so that they are bundled into the image
# and don't need to be installed every time the image is run.
RUN uv sync

ENTRYPOINT [ "./main.py" ]
