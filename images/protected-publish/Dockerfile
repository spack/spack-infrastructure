FROM python:3.11

RUN apt-get update && apt-get install -y \
        gpg \
        gpg-agent && \
    apt-get autoremove --purge -y && \
    apt-get clean

COPY requirements.txt /srcs/requirements.txt

RUN pip install --upgrade uv
RUN uv pip install --system --no-cache-dir -r /srcs/requirements.txt

COPY pkg /srcs/pkg
COPY --chmod=755 migrate.sh /srcs/migrate.sh

ENV PYTHONUNBUFFERED=1
WORKDIR /srcs
ENTRYPOINT ["python", "-m", "pkg.publish"]
