import base64
import functools
import os
import sys
import tempfile
import typing
from contextlib import contextmanager

import click
from kubernetes.client import CoreV1Api
from ruamel.yaml import YAML

if typing.TYPE_CHECKING:
    from kubernetes.client.models.v1_secret_list import V1SecretList


class InvalidSealedSecretError(click.ClickException):
    def __init__(self, kind) -> None:
        super().__init__(f"Invalid k8s resource kind (expected SealedSecret, found {kind}).")


def ensure_document_kind(doc: dict):
    """Ensure the doc has a `kind` of `SealedSecret`, raising an exception otherwise."""
    kind = doc.get("kind", None)
    if kind != "SealedSecret":
        raise InvalidSealedSecretError(kind)


def get_yaml_reader():
    def represent_none(self, data):
        return self.represent_scalar("tag:yaml.org,2002:null", "null")

    yl = YAML()
    yl.preserve_quotes = True
    yl.representer.add_representer(type(None), represent_none)

    return yl


@functools.cache
def fetch_key_pairs() -> list[tuple[str, str]]:
    """Fetch all sealed secrets key pairs found in the cluster.

    Fetches all sealed secrets key pairs found in the cluster, in order of ascending creation date
    (most recent last).
    """
    # Fetch list of secrets
    secrets: V1SecretList = CoreV1Api().list_namespaced_secret(
        namespace="kube-system",
        label_selector="sealedsecrets.bitnami.com/sealed-secrets-key=active",
    )
    if not secrets.items:
        raise Exception("Could not find sealed-secret key pair in namespace kube-system")  # noqa: TRY002

    ordered_secrets = sorted(secrets.items, key=lambda item: item.metadata.creation_timestamp)
    return [
        (
            base64.b64decode(secret.data["tls.crt"]).decode(),
            base64.b64decode(secret.data["tls.key"]).decode(),
        )
        for secret in ordered_secrets
    ]


def latest_key_pair() -> tuple[str, str]:
    return fetch_key_pairs()[-1]


@contextmanager
def populated_tempfile(starting_value: bytes | None = None):
    """Context manager that takes care of populating a temporary file's contents."""
    with tempfile.NamedTemporaryFile() as tmp:
        if starting_value is not None:
            tmp.write(starting_value)
            tmp.flush()
            os.fsync(tmp.fileno())

        # Yield tempfile wrapper
        try:
            yield tmp
        finally:
            pass


def exit_prompt(prompt: str, correct: str) -> None:
    answer = click.prompt(
        click.style(
            prompt,
            fg="yellow",
        )
    )
    if answer != correct:
        click.echo(click.style("Exiting...", fg="yellow"))
        sys.exit(0)
