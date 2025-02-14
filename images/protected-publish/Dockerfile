FROM python:3.11

RUN apt-get update && apt-get install -y \
        gpg \
        gpg-agent && \
    apt-get autoremove --purge -y && \
    apt-get clean

COPY requirements.txt /srcs/requirements.txt

RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r /srcs/requirements.txt

COPY pkg /srcs/pkg
COPY --chmod=755 migrate.sh /srcs/migrate.sh
COPY test_stacks.txt /srcs/test_stacks.txt
COPY develop_stacks.txt /srcs/develop_stacks.txt

WORKDIR /srcs
ENTRYPOINT ["python", "-m", "pkg.publish"]
