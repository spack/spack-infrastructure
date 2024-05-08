FROM python:3.11

ARG SPACK_VERSION=e4s-24.05

RUN cd / && \
    git clone --depth 1 --single-branch --branch ${SPACK_VERSION} https://github.com/spack/spack

RUN apt-get update && apt-get install -y \
        gpg \
        gpg-agent && \
    apt-get autoremove --purge -y && \
    apt-get clean

COPY requirements.txt /srcs/requirements.txt

RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r /srcs/requirements.txt

COPY publish.py /srcs/publish.py

WORKDIR /srcs
ENV SPACK_ROOT /spack
ENTRYPOINT ["python", "publish.py"]
