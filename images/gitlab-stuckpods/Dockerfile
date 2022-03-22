FROM ubuntu

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get -yqq update \
 && apt-get -yqq install --no-install-recommends \
    git \
    locales \
    openssh-client \
    curl \
    parallel \
    jq \
#        python3 \
#        python3-pip \
#        python3-setuptools \
#        ipython3 \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/* \
 && locale-gen en_US.UTF-8

ENV LANGUAGE en_US.UTF-8
ENV LANG en_US.UTF-8
ENV LC_ALL en_US.UTF-8

COPY --from=bitnami/kubectl /opt/bitnami/kubectl/bin/kubectl /usr/local/bin
COPY entrypoint.sh /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
