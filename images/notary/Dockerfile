FROM alpine:3.15
MAINTAINER Chris Kotfila <chris.kotfila@kitware.com>

RUN apk add --no-cache \
        bash \
        gpg \
        gpg-agent \
        python3 \
        py3-cffi \
        py3-pip \
    && pip3 install --upgrade pip \
    && pip3 install --no-cache-dir \
        awscli aws-encryption-sdk-cli \
    && rm -rf /var/cache/apk/*

COPY sign.sh /sign.sh
