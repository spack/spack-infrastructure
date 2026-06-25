import argparse
from concurrent.futures import ThreadPoolExecutor
import boto3
import os
import sys
import re

from datetime import datetime, timedelta, timezone
import github
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
PRUNE_SINCE_DAYS = int(os.environ.get("PRUNE_SINCE_DAYS", 14))


def active_prs(gh: Github, repo: str) -> Iterable[int]:
    """Get all of the open PR numbers for a github org/repo"""
    repo = gh.get_repo(repo, lazy=True)

    dt = timedelta(days=PRUNE_SINCE_DAYS)
    cutoff = datetime.now(tz=timezone.utc) - dt

    for pr in repo.get_pulls(state="open"):
        if pr.draft:
            print(f"PR {pr.number}: Marking draft PR as prunable")
            continue

        # Caches are considered stale if the PR has been untouched
        # for more than the pruning window
        if pr.updated_at < cutoff:
            print(f"PR {pr.number}: Marking stale PR as prunable: {pr.updated_at}")
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


def delete_batch(s3, bucket, batch):
    del_resp = s3.delete_objects(
        Bucket=bucket,
        Delete={"Objects": batch, "Quiet": True}
    )
    # If there are errors during delete report them
    errs = del_resp.get("Errors", [])
    if errs:
        print("Errors: ", file=sys.stderr)
        for err in errs:
            print(err, file=sys.stderr)


def delete_prefix(s3, bucket: str, prefix: str, dryrun: bool = True):
    """Delete everything under a prefix"""

    note = ""
    if dryrun:
        note = "DRYRUN: "
    print(note + f"Deleting: s3://{bucket}/{prefix}")
    listing_args = dict(
        Bucket=bucket,
        Prefix=prefix,
    )

    paginator = s3.get_paginator("list_objects_v2")
    objects = paginator.paginate(**listing_args)
    total_size = 0
    futures = []
    batch = []
    with ThreadPoolExecutor(max_workers=16) as executor:
        for obj in objects.search("Contents"):
            total_size += obj["Size"]
            batch.append({k: obj[k] for k in ("Key", "ETag")})
            if dryrun:
                continue

            if len(batch) == 100:
                futures.append(executor.submit(delete_batch, s3, bucket, batch))
                batch = []

    _ = [f.result() for f in futures]

    if not dryrun and batch:
        delete_batch(s3, bucket, batch)

    return total_size


def list_dirs(s3, bucket: str, prefix: str | None = None) -> Iterable[str]:
    listing_args = dict(
        Bucket=bucket,
        Prefix=prefix or "",
        Delimiter="/",
    )
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

    print(f"""
    repos: {args.repo}
    bucket: {args.bucket}
    dryrun: {args.dryrun}
""")

    gh = Github(os.environ.get("GITHUB_TOKEN"))
    session = boto3.Session()
    s3 = session.client("s3")

    total_bytes = 0
    # Delete any "top-level" PR prefixes since they should now live under
    # "spack" or "spack-packages" prefixes.
    for prefix in list_dirs(s3, args.bucket):
        if _prno_from_prefix(prefix):
            total_bytes += delete_prefix(s3, args.bucket, prefix, args.dryrun)

    # For each repo, delete the S3 mirror prefixes not associated with open PRs
    for repo in args.repo:
        # Get the list of PR mirrors
        pr_mirror_map = {
            prno: p
            for p in list_dirs(s3, args.bucket, _repo_s3_prefix(repo))
            if (prno := _prno_from_prefix(p)) is not None
        }

        # Search PR mirrors not associated with an open PR
        # Note: listing open PRs after getting list of mirrors to avoid races
        for prno in active_prs(gh, repo):
            if prno in pr_mirror_map:
                pr_mirror_map.pop(prno)

        for p in pr_mirror_map.values():
            total_bytes += delete_prefix(s3, args.bucket, p, args.dryrun)

    # Only go up to petabytes, anything more than than is concerning
    unit = ("", "M", "G", "T", "P")
    index = 0
    while total_bytes > 10240 and index < 4:
        index += 1
        total_bytes /= 1024

    print(f"Pruned: {total_bytes}{unit[index]}B")
