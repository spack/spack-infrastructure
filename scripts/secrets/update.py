#!/usr/bin/env python3

import base64
import curses
import functools
import json
import os
import subprocess
import tempfile
import typing
from contextlib import contextmanager
from pathlib import Path
from subprocess import PIPE, Popen

import click
import kubernetes
from kubernetes.client.models.v1_secret_list import V1SecretList
from ruamel.yaml import YAML

if typing.TYPE_CHECKING:
    from curses import _CursesWindow


def select_value(stdscr, values: list[str], titles: list[str] = []):
    value_index = 0

    # Start colors in curses
    curses.start_color()
    curses.init_pair(1, curses.COLOR_CYAN, curses.COLOR_BLACK)
    curses.init_pair(2, curses.COLOR_RED, curses.COLOR_BLACK)
    curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_WHITE)
    curses.init_pair(4, curses.COLOR_WHITE, curses.COLOR_BLACK)

    # Clear and refresh the screen for a blank canvas
    stdscr.erase()
    stdscr.refresh()
    curses.noecho()

    # Render titles
    for i, title in enumerate(titles):
        stdscr.addstr(i, 0, title)

    # Create window for value selection
    win_start = len(titles)
    win: _CursesWindow = curses.newwin(len(values), stdscr.getmaxyx()[1], win_start, 0)
    stdscr.move(win_start, 0)

    # Store last character passed
    k = None
    while True:
        # Initialization
        win.erase()

        # Check value
        if k == curses.KEY_DOWN:
            value_index += 1
        elif k == curses.KEY_UP:
            value_index -= 1
        elif k in [curses.KEY_ENTER, ord("\n"), ord("\r")]:
            return value_index

        # Clamp to within value list
        value_index = min(len(values) - 1, max(0, value_index))

        # Render values
        for i, val in enumerate(values):
            number_str = f"{i + 1}.) "
            win.addstr(i, 0, number_str, curses.color_pair(1))
            win.addstr(i, len(number_str), val, curses.color_pair(4))

        # Move cursor
        win.move(value_index, 0)

        # Refresh the screen
        win.refresh()

        # Wait for next input
        k = stdscr.getch()


def select_secret(secrets: list[str]):
    return curses.wrapper(
        select_value, secrets, titles=["Please select the secret to update:"]
    )


def select_key(secret_name: str, keys: list[str]):
    return curses.wrapper(
        select_value,
        keys,
        titles=[
            f"Updating: {secret_name}",
            "",
            "Please select key to update:",
        ],
    )


def get_yaml_reader():
    def represent_none(self, data):
        return self.represent_scalar("tag:yaml.org,2002:null", "null")

    yl = YAML()
    yl.preserve_quotes = True  # type: ignore
    yl.representer.add_representer(type(None), represent_none)

    return yl


@functools.cache
def fetch_key_pairs() -> list[tuple[str, str]]:
    """
    Fetches all sealed secrets key pairs found in the cluster, in order of ascending creation date
    (most recent last).
    """
    kubernetes.config.load_config()
    client = kubernetes.client.CoreV1Api()

    # Fetch list of secrets
    secrets: V1SecretList = client.list_namespaced_secret(
        namespace="kube-system",
        label_selector="sealedsecrets.bitnami.com/sealed-secrets-key=active",
    )
    if not secrets.items:
        raise Exception(
            "Could not find sealed-secret key pair in namespace kube-system"
        )

    ordered_secrets = sorted(
        secrets.items, key=lambda item: item.metadata.creation_timestamp
    )
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
    """A context manager that takes care of populating a temporary file's contents."""
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


def read_user_input(starting_value: bytes | None = None):
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

    raise Exception(f"Could not decrypt secret {secret['metadata']['name']}")


def get_secret_value(secret: dict, key: str, new_key=False):
    starting_value = None

    # Don't populate existing if a new key is being created
    if not new_key:
        # Decrypt existing value for the secret that's being updated
        decrypted_secret = decrypt_sealed_secret(secret)
        starting_value = base64.b64decode(decrypted_secret["data"][key] or "")

    return read_user_input(starting_value=starting_value).strip()


def select_secret_and_key(secret_docs: list[dict]):
    # Maps secret names to their data
    secret_map = {
        doc["metadata"]["name"]: doc["spec"]["encryptedData"] for doc in secret_docs
    }

    # Select which secret to modify
    secret_names = [doc["metadata"]["name"] for doc in secret_docs]
    secret_index = select_secret(secret_names) if len(secret_map) > 1 else 0

    # Select which key to modify
    secret = secret_docs[secret_index]
    secret_name = secret["metadata"]["name"]

    # Ensure encryptedData field is present and at least an empty object
    if not secret["spec"].get("encryptedData"):
        secret["spec"]["encryptedData"] = {}

    # Retrieve data
    data_dict = secret["spec"]["encryptedData"]

    # Add all keys plus the final option for a new entry
    keys = list(data_dict.keys())
    keys.append("<Add New Key>")
    key_to_update = keys[select_key(secret_name, keys)]

    # If last key, prompt for key name
    adding_new_key = False
    if key_to_update == keys[-1]:
        adding_new_key = True
        key_to_update = click.prompt("Please enter new secret name")

    return (secret, secret_index, key_to_update, adding_new_key)


def seal_secret_value(secret_namespace: str, secret_name: str, value: str):
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


def handle_raw_secret_input():
    secret_name = click.prompt("Secret name")
    secret_namespace = click.prompt("Secret namespace")
    secret_value = read_user_input()
    encrypted_value = seal_secret_value(
        secret_namespace=secret_namespace,
        secret_name=secret_name,
        value=secret_value,
    )
    click.echo(click.style("-------------------", fg="green"))
    click.echo(click.style("Secret value successfully sealed", fg="green"))
    click.echo(click.style("-------------------", fg="green"))
    click.echo(encrypted_value)


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
def main(secrets_file: str, value: str, raw: bool):
    if secrets_file is None:
        if not raw:
            raise click.ClickException(
                "Argument SECRETS_FILE must be supplied when --raw is not specified"
            )

        # Raw input
        handle_raw_secret_input()
        exit(0)

    # Normal secret file input
    secrets_file_path = Path(secrets_file)
    if not secrets_file_path.exists():
        raise click.ClickException(f"File {secrets_file} not found")
    if secrets_file_path.is_dir():
        raise click.ClickException(
            "Argument SECRETS_FILE must be a file, not a folder."
        )

    # Read in supplied secret file
    yl = get_yaml_reader()
    with open(secrets_file) as f:
        secret_docs = list(yl.load_all(f))

    # Retrieve the secret and key to update
    secret, secret_index, key_to_update, adding_new_key = select_secret_and_key(
        secret_docs=secret_docs
    )

    # Retrieve value, if not already supplied
    value = value or get_secret_value(
        secret=secret, key=key_to_update, new_key=adding_new_key
    )

    # Ensure the empty value is what's desired
    if value == "":
        answer = click.prompt(
            click.style(
                "Warning: You've entered an empty value, continue? (y/n)", fg="yellow"
            )
        )
        if answer != "y":
            click.echo(click.style("Exiting...", fg="yellow"))
            exit(0)

    # Encrypt value using kubeseal
    encrypted_value = seal_secret_value(
        secret_namespace=secret["metadata"]["namespace"],
        secret_name=secret["metadata"]["name"],
        value=value,
    )

    # Update secret dict and save
    secret["spec"]["encryptedData"][key_to_update] = encrypted_value
    secret_docs[secret_index] = secret
    with open(secrets_file, "w") as f:
        yl.dump_all(secret_docs, f)

    # Give user feedback
    click.echo(click.style("Secret value successfully sealed", fg="green"))


if __name__ == "__main__":
    main()
