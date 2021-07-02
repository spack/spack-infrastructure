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

WORKDIR /scripts/
COPY requirements.txt ./

RUN python3 -m pip install --upgrade pip setuptools wheel \
    && python3 -m pip install --no-cache-dir -r requirements.txt \
    && cd / \
    && git clone ${SPACK_REPO}\
    && cd spack\
    && git checkout ${SPACK_REF}\
    && cd /scripts/

ENV PATH ${PATH}:/spack/bin

COPY SpackPRBinaryGraduation.py ./

ENTRYPOINT [ "spack", "python", "./SpackPRBinaryGraduation.py"]
