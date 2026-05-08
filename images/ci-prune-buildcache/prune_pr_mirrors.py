import argparse
import boto3
import sys
import re

from github import Github
from github.GithubException import GithubException

from typing import Iterable

try:
    import sentry_sdk
    sentry_sdk.init(
        # This cron job only runs once weekly,
        # so just record all transactions.
        traces_sample_rate=1.0,
    )
except ImportError:
    print("Could not find sentry, running in local mode")


PR_BUCKET = "spack-binaries-prs"
PR_PREFIX_RE = re.compile(r"pr([0-9]+)_.*")


def open_prs(gh: Github, repo: str) -> Iterable[int]:
    """Get all of the open PR numbers for a github org/repo"""
    repo = gh.get_repo(repo, lazy=True)
    for pr in repo.get_pulls(state="open"):
        if pr.draft:
            continue

        yield pr.number


def _repo_s3_prefix(repo):
    """Get the s3 prefix for the repo slug

        `<repo org>/<repo name>` -> `<repo name>/`

    """
    return repo.split("/")[1].strip() + "/"


def _prno_from_prefix(prefix):
    """Get the PR number from a mirror prefix"""
    m = PR_PREFIX_RE.search(prefix)
    if m:
        return int(m.group(1))
    return None


def delete_prefix(s3, bucket: str, prefix: str, dryrun: bool = True):
    """Delete everything under a prefix"""

    print(f"Deleting: s3://{bucket}/{prefix}")
    listing_args = dict(
        Bucket=bucket,
        Prefix=prefix,
    )
    total_size = 0
    while True:
        # List items under the prefix
        resp = s3.list_objects_v2(**listing_args)
        objects = [
            {
                "Key": o["Key"],
                "ETag": o["ETag"],
                "Size": o["Size"],
            } for o in resp.get("Contents", [])
        ]

        total_size = sum(o["Size"] for o in objects)

        # Delete all of the listed items
        if objects:
            print(f"Deleteing {len(objects)} objects")

            if not dryrun:
                del_resp = s3.delete_objects(
                    Bucket=bucket,
                    Delete=objects
                )

                # If there are errors during delete report them
                errs = del_resp.get("Errors", [])
                if errs:
                    print("Errors: ", file=sys.stderr)
                    for err in errs:
                        print(err, file=sys.stderr)
            else:
                print("-- DRYRUN -- ")
                break

        # Update listing args for pagination
        if resp.get("IsTruncated", False) and objects:
            listing_args.update({"StartAfter": objects[-1]["Key"]})
        else:
            break

    return total_size


def list_dirs(s3, bucket: str, prefix: str | None = None) -> Iterable[str]:
    listing_args = dict(
        Bucket=bucket,
        Prefix=prefix or "",
        Delimiter="/",
    )
    print(listing_args)
    paginator = s3.get_paginator("list_objects_v2")
    page_iter = paginator.paginate(**listing_args)
    for page in page_iter:
        for p in page.get("CommonPrefixes", []):
            yield p["Prefix"]


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("-n", "--dryrun", action="store_true")
    parser.add_argument("-r", "--repo", action="append")
    parser.add_argument("-b", "--bucket", default=PR_BUCKET)

    args = parser.parse_args()

    if not args.repo:
        args.repo = ["spack/spack", "spack/spack-packages"]

    gh = Github()
    session = boto3.Session()
    s3 = session.client("s3")

    # Delete everything in the top level, these are all stale
    for prefix in list_dirs(s3, args.bucket):
        if _prno_from_prefix(prefix):
            delete_prefix(s3, args.bucket, prefix)

    # For each repo, delete the S3 mirror prefixes not associated with open PRs
    for repo in args.repo:
        # Get the list of PR mirrors
        pr_mirror_map = dict(
            [
                (
                    _prno_from_prefix(p), p
                ) for p in list_dirs(s3, args.bucket, _repo_s3_prefix(repo))
            ]
        )

        # Search PR mirrors not associated with an open PR
        # Note: listing open PRs after getting list of mirrors to avoid races
        for prno in open_prs(gh, repo):
            if prno in pr_mirror_map:
                pr_mirror_map.pop(prno)

        for p in pr_mirror_map.values():
            delete_prefix(s3, args.bucket, p)
