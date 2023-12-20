import base64
import hashlib
import os
import shutil
import subprocess
import typing
from pathlib import Path

import click
import kubernetes.config
from kubernetes.client import CoreV1Api

from .curses import select_secret_and_key
from .sealed import decrypt_sealed_secret, seal_raw_secret_value, seal_secret
from .utils import exit_prompt, get_yaml_reader, populated_tempfile

if typing.TYPE_CHECKING:
    from kubernetes.client.models.v1_config_map import V1ConfigMap


def read_user_input(starting_value: bytes | None = None) -> str:
    """Open the user configured editor and retrieve the input value."""
    EDITOR = os.environ.get("EDITOR", "vim")

    with populated_tempfile(starting_value=starting_value) as tmp:
        # Open editor so user can change things
        retcode = subprocess.call([EDITOR, tmp.name])
        if retcode != 0:
            raise click.ClickException("Error retrieving secret value")

        # Read value back out
        tmp.seek(0)
        val = tmp.read().decode("utf-8")

    return val


def handle_raw_secret_input():
    secret_name = click.prompt("Secret name")
    secret_namespace = click.prompt("Secret namespace")
    secret_value = read_user_input()
    encrypted_value = seal_raw_secret_value(
        secret_namespace=secret_namespace,
        secret_name=secret_name,
        value=secret_value,
    )
    click.echo(click.style("--------------------------------", fg="green"))
    click.echo(click.style("Secret value successfully sealed", fg="green"))
    click.echo(click.style("--------------------------------", fg="green"))
    click.echo(encrypted_value)


def print_cluster_info():
    configmap: V1ConfigMap = CoreV1Api().read_namespaced_config_map(
        namespace="kube-system", name="cluster-info"
    )  # type: ignore[reportGeneralTypeIssues]

    if configmap.data is None:
        raise Exception("Cluster-info configmap has null data field")

    cluster_name = configmap.data["cluster-name"]
    message = f"Operating on cluster: {cluster_name}"
    border = "-" * len(message)
    click.echo(f"{border}\n{message}\n{border}")


@click.command(help="Update an existing secret")
@click.argument("secrets_file", type=click.STRING, required=False)
@click.option(
    "--raw",
    type=click.BOOL,
    is_flag=True,
    help="Returns an encrypted value directly, instead of updating a file",
)
@click.option(
    "--value",
    type=click.STRING,
    help="Supply the value for the selected secret as an argument.",
)
def update(secrets_file: str, *, value: str, raw: bool):
    if secrets_file is None and not raw:
        raise click.ClickException(
            "Argument SECRETS_FILE must be supplied when --raw is not specified"
        )

    # Load k8s config
    if os.environ.get("KUBECONFIG") is None:
        raise click.ClickException("Environment variable KUBECONFIG must be set")
    kubernetes.config.load_config()

    # Check that kubeseal is installed
    if shutil.which("kubeseal") is None:
        raise click.ClickException(
            "kubeseal not found. Please follow the installation instructions https://github.com/bitnami-labs/sealed-secrets#kubeseal"
        )

    # Display info about which cluster is being acted on
    print_cluster_info()

    # Handle raw input case
    if raw:
        handle_raw_secret_input()
        exit(0)

    # Normal secret file input
    secrets_file_path = Path(secrets_file)
    if not secrets_file_path.exists():
        raise click.ClickException(f"File {secrets_file} not found")
    if secrets_file_path.is_dir():
        raise click.ClickException("Argument SECRETS_FILE must be a file, not a folder.")

    # Read in supplied secret file
    yl = get_yaml_reader()
    with open(secrets_file) as f:
        secret_docs = list(yl.load_all(f))

    # Retrieve the secret and key to update
    sealed_secret, secret_index, key_to_update, adding_new_key = select_secret_and_key(
        secret_docs=secret_docs
    )
    secret = decrypt_sealed_secret(sealed_secret)

    # Retrieve value, if not already supplied
    if not value:
        # Pre-populate value if updating an existing key, so the user can see it
        starting_input = (
            None if adding_new_key else base64.b64decode(secret["data"][key_to_update] or "")
        )
        value = read_user_input(starting_value=starting_input).strip()

        # Check that value has been changed
        if (
            starting_input is not None
            and hashlib.sha256(starting_input).hexdigest()
            == hashlib.sha256(value.encode()).hexdigest()
        ):
            exit_prompt(
                prompt="Warning: Secret value not changed, continue? (y/n)",
                correct="y",
            )

    # Ensure the empty value is what's desired
    if value == "":
        exit_prompt(
            prompt="Warning: You've entered an empty value, continue? (y/n)",
            correct="y",
        )

    # Update existing secret with new value
    secret["data"][key_to_update] = base64.b64encode(value.encode("utf-8")).decode("utf-8")

    # Encrypt value using kubeseal
    resealed_secret = seal_secret(secret)

    # Update all the values of the original sealed_secret "spec.encryptedData" field, to preserve comments, etc.
    for k, v in resealed_secret["spec"]["encryptedData"].items():
        sealed_secret["spec"]["encryptedData"][k] = v

    # Update secret dict and save
    secret_docs[secret_index] = sealed_secret
    with open(secrets_file, "w") as f:
        yl.dump_all(secret_docs, f)

    # Give user feedback
    click.echo(click.style("Secret value successfully sealed", fg="green"))
