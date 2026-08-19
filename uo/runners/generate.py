#!/usr/bin/env python3
"""Expand the compact ``fleet.toml`` into full GitLab-runner ``config.toml`` files.

All of the boilerplate that is identical across every runner (the docker/cache
blocks, the pre-build bootstrap script, the session server) lives here; only the
per-host / per-runner variation lives in ``fleet.toml``.

Typical use::

    # regenerate every <host>.config.toml next to this script
    python3 generate.py

    # print one host's config to stdout (e.g. to pipe onto a machine)
    python3 generate.py --host athena --stdout

    # render with the real registration token injected, ready to apply
    GITLAB_TOKEN=glrt-xxxx python3 generate.py --host athena --stdout
"""

from __future__ import annotations

import argparse
import os
import sys

import tomllib

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SOURCE = os.path.join(HERE, "fleet.toml")
TOKEN_PLACEHOLDER = "%%GITLAB_TOKEN%%"

# The value for `connection_max_age` when it's not overridden
DEFAULT_CONNECTION_MAX_AGE = "15m0s"

PRE_BUILD_SCRIPT = """\
  echo 'Executing Spack pre-build setup script'
  for cmd in "${PY3:-}" python3 python; do
    if command -v > /dev/null "$cmd"; then
      export PY3="$(command -v "$cmd")"
      break
    fi
  done
  if [ -z "${PY3:-}" ]; then
    echo "Unable to find python3 executable"
    exit 1
  fi
  $PY3 -c "import urllib.request;urllib.request.urlretrieve('https://raw.githubusercontent.com/spack/spack-infrastructure/main/scripts/gitlab_runner_pre_build/pre_build.py', 'pre_build.py')"
  $PY3 pre_build.py > envvars
  . ./envvars
  rm -f envvars
  unset GITLAB_OIDC_TOKEN
  """


def _toml_basic_string(value: str) -> str:
    """Render a Python string as a single-line TOML basic string."""
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


# The config.toml is assembled from these templates.
GLOBAL_TEMPLATE = """\
concurrent = {concurrent}
check_interval = 10
{connection_max_age}
shutdown_timeout = 0"""

SESSION_TEMPLATE = """\
[session_server]
  session_timeout = 1800"""

RUNNER_TEMPLATE = """\
[[runners]]
  name = "{name}"
  url = "https://gitlab.spack.io"
  id = {id}
  limit = {limit}
  token = {token}
  executor = "docker"
  {environment}
  pre_build_script = {pre_build_script}
  [runners.cache]
    MaxUploadedArchiveSize = 0
    [runners.cache.s3]
      AssumeRoleMaxConcurrency = 0
    [runners.cache.gcs]
    [runners.cache.azure]
  [runners.docker]
    tls_verify = false
    image = "ubuntu:26.04"
    privileged = false
    allowed_pull_policies = ["always", "if-not-present"]
    pull_policy = ["if-not-present"]
    disable_entrypoint_overwrite = false
    oom_kill_disable = false
    disable_cache = false
    volumes = ["/cache"]
    volume_keep = false
    shm_size = 0
    network_mtu = 0"""


def _section(template: str, **values: object) -> str:
    """Format a template, dropping any line left blank by an empty optional field.

    Sections never contain intentional blank lines of their own; those are added
    between sections by render_host().
    """
    block = template.format(**values)
    return "\n".join(line for line in block.splitlines() if line.strip())


def _runner_block(runner: dict, token: str) -> str:
    environment = ""
    if runner.get("environment"):
        envs = ", ".join(f'"{e}"' for e in runner["environment"])
        environment = f"environment = [{envs}]"
    return _section(
        RUNNER_TEMPLATE,
        name=runner["name"],
        id=runner["id"],
        limit=runner["limit"],
        token=_toml_basic_string(token),
        environment=environment,
        pre_build_script=_toml_basic_string(PRE_BUILD_SCRIPT),
    )


def render_host(host: dict, token: str) -> str:
    conn = host.get("connection_max_age", DEFAULT_CONNECTION_MAX_AGE)
    connection_max_age = f'connection_max_age = "{conn}"' if conn else ""
    sections = [
        _section(
            GLOBAL_TEMPLATE,
            concurrent=host["concurrent"],
            connection_max_age=connection_max_age,
        ),
        _section(SESSION_TEMPLATE),
        *(_runner_block(runner, token) for runner in host["runners"]),
    ]
    return "\n\n".join(sections) + "\n"


def load_fleet(source: str) -> dict:
    with open(source, "rb") as fh:
        return tomllib.load(fh)["hosts"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=DEFAULT_SOURCE, help="fleet source TOML")
    parser.add_argument("--host", help="only render this host (default: all)")
    parser.add_argument(
        "--out-dir", default=HERE, help="where to write <host>.config.toml"
    )
    parser.add_argument(
        "--stdout", action="store_true", help="print instead of writing files"
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("GITLAB_TOKEN", TOKEN_PLACEHOLDER),
        help=f"token to substitute (default: $GITLAB_TOKEN or the {TOKEN_PLACEHOLDER} placeholder)",
    )
    args = parser.parse_args(argv)

    hosts = load_fleet(args.source)
    if args.host:
        if args.host not in hosts:
            parser.error(
                f"unknown host '{args.host}'; known: {', '.join(sorted(hosts))}"
            )
        hosts = {args.host: hosts[args.host]}

    for name, host in hosts.items():
        text = render_host(host, args.token)
        if args.stdout:
            sys.stdout.write(text)
        else:
            path = os.path.join(args.out_dir, f"{name}.config.toml")
            with open(path, "w") as fh:
                fh.write(text)
            print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
