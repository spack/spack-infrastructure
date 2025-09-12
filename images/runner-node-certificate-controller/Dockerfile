FROM python:3.13-slim

COPY --from=bitnami/kubectl /opt/bitnami/kubectl/bin/kubectl /usr/local/bin

COPY entrypoint.sh /entrypoint.sh

RUN curl -sL https://sentry.io/get-cli/ | sh

ENTRYPOINT [ "/entrypoint.sh" ]
