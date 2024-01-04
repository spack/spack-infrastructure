import subprocess

from spack_secrets.update import read_user_input


def test_read_user_input(monkeypatch):
    data = "foo bar"

    def _write_data(args):
        _, filepath = args
        with open(filepath, "w") as f:
            f.write(data)

        return 0

    monkeypatch.setattr(subprocess, "call", _write_data)

    resp = read_user_input()
    assert resp == data
