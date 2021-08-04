FROM ubuntu:20.04

ARG SPACK_REPO=https://github.com/spack/spack.git
ARG SPACK_REF=develop

RUN apt update -y \
    && apt upgrade -y \
    && apt install -y \
        git         \
        locales     \
        python3-pip \
    && locale-gen en_US.UTF-8 \
    && apt autoremove --purge \
    && apt clean

RUN git clone ${SPACK_REPO}\
    && cd spack\
    && git checkout ${SPACK_REF}

COPY src /work/src/

RUN python3 -m pip install --upgrade pip setuptools wheel \
    && python3 -m pip install --no-cache-dir -r /work/src/requirements.txt

ENV PYTHONPATH ${PYTHONPATH}:/work/src:/spack/lib/spack/external:/spack/lib/spack:/spack/bin
WORKDIR /work/src
ENTRYPOINT [ "python3", "web_server.py" ]
