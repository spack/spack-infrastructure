import argparse
import base64
import os
import re
import subprocess
import sys
import tempfile
from contextlib import contextmanager

try:
    import sentry_sdk
    sentry_sdk.init(
        # This cron job only runs once weekly,
        # so just record all transactions.
        traces_sample_rate=1.0,
    )
except Exception:
    print("Could not configure sentry.")


# Copied from SpackCIBridge.py
def setup_ssh(self, ssh_key_base64):
    """Start the ssh agent."""
    print("Starting ssh-agent")
    output = subprocess.run(["ssh-agent", "-s"], check=True, stdout=subprocess.PIPE).stdout

    # Search for PID in output.
    pid_regexp = re.compile(r"SSH_AGENT_PID=([0-9]+)")
    match = pid_regexp.search(output.decode("utf-8"))
    if match is None:
        print("WARNING: could not detect ssh-agent PID.", file=sys.stderr)
        print("ssh-agent will not be killed upon program termination", file=sys.stderr)
    else:
        pid = match.group(1)
        os.environ["SSH_AGENT_PID"] = pid
        self.cleanup_ssh_agent = True

    # Search for socket in output.
    socket_regexp = re.compile(r"SSH_AUTH_SOCK=([^;]+);")
    match = socket_regexp.search(output.decode("utf-8"))
    if match is None:
        print("WARNING: could not detect ssh-agent socket.", file=sys.stderr)
        print("Key will be added to caller's ssh-agent (if any)", file=sys.stderr)
    else:
        socket = match.group(1)
        os.environ["SSH_AUTH_SOCK"] = socket

    # Add the key.
    ssh_key = base64.b64decode(ssh_key_base64)
    ssh_key = ssh_key.replace(b"\r", b"")
    with tempfile.NamedTemporaryFile() as fp:
        fp.write(ssh_key)
        fp.seek(0)
        subprocess.run(["ssh-add", fp.name], check=True)


def setup_repo(pull_remote, push_remote, branch):
    subprocess.run(["git", "init"], check=True)
    subprocess.run(["git", "config", "user.email", "noreply@spack.io"], check=True)
    subprocess.run(["git", "config", "user.name", "spackbot"], check=True)
    subprocess.run(["git", "config", "advice.detachedHead", "false"], check=True)

    subprocess.run(["git", "remote", "add", "origin", pull_remote], check=True)
    subprocess.run(["git", "remote", "set-url", "--push", "origin", push_remote], check=True)

    fetch_args = ["git", "fetch", "-q", "origin", branch]
    subprocess.run(fetch_args, check=True, stdout=subprocess.PIPE).stdout
    subprocess.run(["git", "checkout", branch], check=True)


@contextmanager
def chworkingdir(path):
    save_dir = os.path.realpath(os.curdir)
    if path:
        if not os.path.exists(path):
            os.makedirs(path)
        os.chdir(path)
        yield path
    else:
        with tempfile.TemporaryDirectory() as tmpdir:
            os.chdir(tmpdir)
            yield tmpdir

    os.chdir(save_dir)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pull and repush a branch from one remote to another")
    parser.add_argument("--push-remote", help="Host to push to")
    parser.add_argument("--push-branch", help="Name of pushed branch")

    parser.add_argument("--tag", action="store_true", help="Use a tag instead of a branch alias")

    parser.add_argument("--pull-remote", help="Host to pull to")
    parser.add_argument("--pull-branch", help="Name of pulled branch")

    parser.add_argument("--working-dir", help="Set the working directory")

    args = parser.parse_args()

    # Configure ssh for pushing to gitlab
    ssh_key_base64 = os.getenv("GITLAB_SSH_KEY_BASE64")
    if ssh_key_base64 is None:
        raise Exception("GITLAB_SSH_KEY_BASE64 environment is not set")
    setup_ssh(ssh_key_base64)

    with chworkingdir(args.working_dir):
        setup_repo(args.pull_remote, args.push_remote, args.pull_branch)

        if args.tag:
            subprocess.run(["git", "tag", args.push_branch], check=True)
        else:
            subprocess.run(["git", "checkout", "-b", args.push_branch], check=True)

        # Push the renamed branch to the push remote
        subprocess.run(["git", "push", "-f", "origin", args.push_branch], check=True)
