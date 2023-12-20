import curses
import typing

import click

from .utils import ensure_document_kind

if typing.TYPE_CHECKING:
    from curses import _CursesWindow


def select_value(stdscr, values: list[str], titles: list[str] = list):
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
    return curses.wrapper(select_value, secrets, titles=["Please select the secret to update:"])


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


def select_secret_and_key(secret_docs: list[dict]):
    # Select which secret to modify
    secret_names = [doc["metadata"]["name"] for doc in secret_docs]
    secret_index = select_secret(secret_names) if len(secret_docs) > 1 else 0

    # Select which key to modify
    secret = secret_docs[secret_index]
    secret_name = secret["metadata"]["name"]

    # Check that object we're modifying is a sealed secret to begin with
    ensure_document_kind(secret)

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
