#!/usr/bin/env python3

import base64
import json
import os
import re
from pathlib import Path
from subprocess import PIPE, Popen

import click
import yaml
from kubernetes import client, config

RECOVERY_KEY_FILE = os.getenv("RECOVERY_KEY_FILE")
if RECOVERY_KEY_FILE is None:
    raise click.ClickException(
        "Please specify cert file via RECOVERY_KEY_FILE environment variable."
    )
if not Path(RECOVERY_KEY_FILE).exists():
    raise click.ClickException(f"Recovery key {RECOVERY_KEY_FILE} not found")


# Load local kube config
config.load_kube_config()
v1 = client.CoreV1Api()


def verify_secrets(sealed_secrets: list[dict]):
    sealed_secrets = sorted(
        sealed_secrets,
        key=lambda d: (d["metadata"]["namespace"], d["metadata"]["name"]),
    )

    for sealed_secret in sealed_secrets:
        metadata = sealed_secret["metadata"]
        name = metadata["name"]
        namespace = metadata["namespace"]
        sealed_secret_id = f"{namespace}/{name}"
        print(f"--- {sealed_secret_id} ---")

        # Find matching secret
        secret = v1.read_namespaced_secret(name=name, namespace=namespace)
        secret_dict = secret.to_dict()
        p = Popen(
            [
                "kubeseal",
                "--recovery-unseal",
                "--recovery-private-key",
                RECOVERY_KEY_FILE,
            ],
            stdin=PIPE,
            stdout=PIPE,
        )
        output, _ = p.communicate(
            json.dumps(sealed_secret, default=str).encode("utf-8")
        )
        rc = p.returncode
        if rc != 0:
            raise Exception(f"Error processing sealed secret {sealed_secret_id}")

        # Verify
        mismatched = []
        unsealed_secret_dict = json.loads(output)
        for key, value in unsealed_secret_dict["data"].items():
            secret_value = secret_dict["data"][key]
            if value != secret_value:
                secret_decoded_value = secret_value and base64.b64decode(secret_value)
                unsealed_secret_decoded_value = value and base64.b64decode(value)
                mismatched.append(
                    {
                        "sealed": unsealed_secret_decoded_value,
                        "unsealed": secret_decoded_value,
                    }
                )

        # Print mismatches if they exist
        if mismatched:
            for mismatch in mismatched:
                escaped_sealed = (
                    f'"{mismatch["sealed"]}"'
                    if mismatch["sealed"] is not None
                    else mismatch["sealed"]
                )
                escaped_unsealed = (
                    f'"{mismatch["unsealed"]}"'
                    if mismatch["unsealed"] is not None
                    else mismatch["unsealed"]
                )
                print(
                    f"MISMATCH: {escaped_sealed} (sealed) "
                    f"!= {escaped_unsealed} (unsealed)"
                )


@click.group(
    help="Verify that sealed secret values match the unsealed values in the cluster."
)
def cli():
    pass


@cli.command(help='Use local "sealed-secrets.yaml" files.')
def local():
    secrets_files = []
    for root, _, files in os.walk(".", topdown=True):
        for name in files:
            if re.match("sealed-secrets.yaml", name):
                secrets_files.append(os.path.join(root, name))

    # Load secrets from all files
    sealed_secrets = []
    for file in secrets_files:
        with open(file) as f:
            sealed_secrets.extend(list(yaml.safe_load_all(f)))

    # Verify
    verify_secrets(sealed_secrets)


@cli.command(help="Use sealedsecrets.bitnami.com cluster resources.")
def remote():
    with client.ApiClient() as api_client:
        api_instance = client.CustomObjectsApi(api_client)

    # Retrieve sealed secrets from all namespaces
    sealed_secrets = api_instance.list_cluster_custom_object(
        "bitnami.com", "v1alpha1", "sealedsecrets"
    )["items"]

    # Verify
    verify_secrets(sealed_secrets)


if __name__ == "__main__":
    cli()
