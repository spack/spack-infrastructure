#!/usr/bin/env python3

import curses
import os
import typing
from pathlib import Path
from subprocess import PIPE, Popen

import click
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
    stdscr.clear()
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
        win.clear()

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
    yl.representer.add_representer(type(None), represent_none)

    return yl


def sealed_secret_cert_path() -> str:
    default_cert = (
        Path(__file__).parent.parent
        / "k8s"
        / "production"
        / "sealed-secrets"
        / "cert.pem"
    )

    cert_path = os.getenv("SEALED_SECRETS_CERT", default_cert)
    if not Path(cert_path).exists():
        raise click.ClickException(
            f"Sealed Secrets Cert file not found: {cert_path.absolute()}"
        )

    return cert_path


@click.command(help="Update an existing secret")
@click.argument("secrets_file", type=click.Path(exists=True, dir_okay=False))
def main(secrets_file: str):
    # Read in secrets file with comments
    yl = get_yaml_reader()
    with open(secrets_file) as f:
        docs = list(yl.load_all(f))

    # Maps secret names to their data
    secret_map = {doc["metadata"]["name"]: doc["spec"]["encryptedData"] for doc in docs}

    # Select which secret to modify
    secret_names = [doc["metadata"]["name"] for doc in docs]
    secret_index = select_secret(secret_names) if len(secret_map) > 1 else 0

    # Select which key to modify
    secret = docs[secret_index]
    secret_name = secret["metadata"]["name"]
    secret_namespace = secret["metadata"]["namespace"]

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
    if key_to_update == keys[-1]:
        key_to_update = click.prompt("Please enter new secret name")

    # Retrieve value
    value = click.prompt("Please enter new secret value")

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
            sealed_secret_cert_path(),
        ],
        stdin=PIPE,
        stdout=PIPE,
    )
    output, _ = p.communicate(value.encode("utf-8"))
    encrypted_value = output.decode("utf-8")

    # Check return
    rc = p.returncode
    if rc != 0:
        raise click.ClickException(
            f"Error sealing secret {secret_name}.{key_to_update}"
        )

    # Update secret dict and save
    secret["spec"]["encryptedData"][key_to_update] = encrypted_value
    docs[secret_index] = secret
    with open(secrets_file, "w") as f:
        yl.dump_all(docs, f)


if __name__ == "__main__":
    main()
