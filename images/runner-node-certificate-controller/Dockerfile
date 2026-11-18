FROM ghcr.io/astral-sh/uv:0.13.5-debian

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY main.py /main.py
COPY pyproject.toml /pyproject.toml
COPY uv.lock /uv.lock

# Install dependencies here so that they are bundled into the image
# and don't need to be installed every time the image is run.
RUN uv sync --locked

ENTRYPOINT [ "./main.py" ]
