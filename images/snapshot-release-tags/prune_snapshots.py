#!/usr/bin/env python3

import argparse
import os
import re
import subprocess

import sentry_sdk
from github import Github


sentry_sdk.init(
    # This cron job only runs once weekly,
    # so just record all transactions.
    traces_sample_rate=1.0,
)

TAG_REF_REGEX = re.compile(r"^refs/tags/(develop-\d{4}-\d{2}-\d{2})$")


def main():
    if "GITHUB_TOKEN" not in os.environ:
        raise Exception("GITHUB_TOKEN environment is not set")

    parser = argparse.ArgumentParser(
        prog="prune_snapshots.py",
        description="Prune expired snapshots",
    )

    parser.add_argument(
        "-k",
        "--keep-last-n",
        type=int,
        default=8,
        help="Prune all but most recent --keep-last-n",
    )
    parser.add_argument(
        "-m",
        "--mirror-root",
        default="s3://spack-binaries",
        help=("Root url of mirror where snapshot binaries are mirrored"),
    )

    args = parser.parse_args()

    keep_n = args.keep_last_n
    mirror_root_url = args.mirror_root

    # Use the GitHub API to create a tag for this commit of develop.
    github_token = os.environ.get("GITHUB_TOKEN")
    py_github = Github(github_token)
    py_gh_repo = py_github.get_repo("spack/spack", lazy=True)

    # Get a list of all the tags matching the develop snapshot pattern
    snapshot_tags = py_gh_repo.get_git_matching_refs("tags/develop-")

    # Sort them so we can prune all but the KEEP_LAST_N most recent
    pruning_candidates = sorted(snapshot_tags, key=lambda ref: ref.ref)[:-keep_n]

    print("Deleting the following snapshots:")
    for tag in pruning_candidates:
        m = TAG_REF_REGEX.search(tag.ref)

        if not m:
            print(f"Unable to parse {tag.ref}, skipping")
            continue

        mirror_prefix = m.group(1)
        url_to_prune = f"{mirror_root_url}/{mirror_prefix}"

        print(f"  Ref: {tag.ref}, Mirror: {url_to_prune}")

        # First, try to delete the mirror associated with the snapshot
        try:
            subprocess.run(["aws", "s3", "rm", "--recursive", url_to_prune], check=True)
        except subprocess.CalledProcessError as cpe:
            print(f"Failed to delete the mirror url {url_to_prune}, skipping")
            continue

        # If mirror deletion succeeded, also delete the tag from GitHub
        tag.delete()


if __name__ == "__main__":
    main()
