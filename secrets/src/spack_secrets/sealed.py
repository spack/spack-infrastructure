# ruff: noqa: S603

import json
import shutil
from subprocess import PIPE, Popen

import click
from click.exceptions import ClickException

from .utils import (
    ensure_document_kind,
    fetch_key_pairs,
    latest_key_pair,
    populated_tempfile,
)


class InvalidSealedSecretError(ClickException):
    def __init__(self) -> None:
        super().__init__("Invalid k8s resource kind (expected SealedSecret).")


class KubesealNotFound(ClickException):
    def __init__(self) -> None:
        super().__init__(
            "kubeseal not found. Please follow the installation instructions https://github.com/bitnami-labs/sealed-secrets#kubeseal"
        )


def ensure_document_type(doc: dict):
    pass


def get_kubeseal_path():
    kubeseal = shutil.which("kubeseal")
    if kubeseal is None:
        raise KubesealNotFound

    return kubeseal


def decrypt_sealed_secret(secret: dict) -> dict:
    ensure_document_kind(secret)

    # Try to decrypt secret with each key pair
    key_pairs = fetch_key_pairs()
    for _, key in key_pairs:
        with populated_tempfile(starting_value=key.encode("utf-8")) as private_key_file:
            # Seal value
            p = Popen(
                [
                    get_kubeseal_path(),
                    "--recovery-unseal",
                    "--recovery-private-key",
                    private_key_file.name,
                ],
                stdin=PIPE,
                stdout=PIPE,
                stderr=PIPE,
            )
            output, _ = p.communicate(input=json.dumps(secret).encode("utf-8"))
            if p.returncode != 0:
                continue

            # Decryption successful, return the decrypted secret
            return json.loads(output.decode("utf-8"))

    raise click.ClickException(
        f"Could not decrypt secret {secret['metadata']['name']}."
        " Is your KUBECONFIG environment variable correctly set?"
    )


def seal_secret(secret: dict) -> dict:
    # Write cert to temp file so that it can be passed to kubeseal
    cert, _ = latest_key_pair()
    with populated_tempfile(cert.encode("utf-8")) as cert_file:
        # Seal value
        p = Popen(
            [get_kubeseal_path(), "--cert", cert_file.name],
            stdin=PIPE,
            stdout=PIPE,
        )
        stdout, stderr = p.communicate(json.dumps(secret).encode("utf-8"))
        encrypted_value = stdout.decode("utf-8")

    # Check return
    rc = p.returncode
    if rc != 0:
        raise click.ClickException(f"Error sealing secret! Error from kubeseal: {stderr}")

    return json.loads(encrypted_value)


def seal_raw_secret_value(secret_namespace: str, secret_name: str, value: str):
    # Write cert to temp file so that it can be passed to kubeseal
    cert, _ = latest_key_pair()
    with populated_tempfile(cert.encode("utf-8")) as cert_file:
        # Seal value
        p = Popen(
            [
                get_kubeseal_path(),
                "--raw",
                "--namespace",
                secret_namespace,
                "--name",
                secret_name,
                "--cert",
                cert_file.name,
            ],
            stdin=PIPE,
            stdout=PIPE,
        )
        output, _ = p.communicate(value.encode("utf-8"))
        encrypted_value = output.decode("utf-8")

    # Check return
    rc = p.returncode
    if rc != 0:
        raise click.ClickException(f"Error sealing secret {secret_name}")

    return encrypted_value
