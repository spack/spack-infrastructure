import json
from subprocess import PIPE, Popen

import click

from .utils import (
    fetch_key_pairs,
    latest_key_pair,
    populated_tempfile,
)


def decrypt_sealed_secret(secret: dict) -> dict:
    if secret.get("kind", None) != "SealedSecret":
        raise Exception("Attempted to decrypt invalid resource.")

    key_pairs = fetch_key_pairs()
    for _, key in key_pairs:
        with populated_tempfile(starting_value=key.encode("utf-8")) as private_key_file:
            # Seal value
            p = Popen(
                [
                    "kubeseal",
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

            decrypted_secret = json.loads(output.decode("utf-8"))
            return decrypted_secret

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
            ["kubeseal", "--cert", cert_file.name],
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
                "kubeseal",
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
