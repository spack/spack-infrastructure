#!/usr/bin/env spack-python
"""
This script is meant to be run using:
    `spack python prune.py`
"""

import argparse
from typing import Optional

import sentry_sdk

import spack.buildcache_prune
from spack.buildcache_prune import prune_buildcache
from spack.mirrors.utils import require_mirror_name

sentry_sdk.init(
    # This cron job only runs once weekly,
    # so just record all transactions.
    traces_sample_rate=1.0,
)


class UnreadableManifestsError(spack.buildcache_prune.BuildcachePruningException):
    """Some manifests could not be read, so the orphan pass can't be trusted."""


def refuse_to_delete_after_failed_reads() -> None:
    """Make prune_buildcache stop instead of deleting once any manifest read fails.

    spack's orphan pass reads every manifest to find the blobs it references, and
    skips (with a warning) any manifest it can't read. The blobs of a skipped
    manifest then look unreferenced and would be deleted as orphans, even though the
    spec still exists, e.g. after an S3 error or expired credentials. Record failed
    reads, and refuse to delete anything once one has happened.
    """
    failed = []
    fetch_manifests = spack.buildcache_prune._fetch_manifests
    delete_entries = spack.buildcache_prune._delete_entries_from_cache

    def fetch_manifests_recording_failures(mirror):
        manifest_to_mtime, read_fn, blobs = fetch_manifests(mirror)

        def read_recording_failures(manifest):
            try:
                return read_fn(manifest)
            except Exception:
                failed.append(manifest)
                raise

        return manifest_to_mtime, read_recording_failures, blobs

    def delete_unless_reads_failed(manifests_to_delete, blobs_to_delete, dry_run):
        if failed:
            raise UnreadableManifestsError(
                f"{len(failed)} manifest(s) could not be read (first: {failed[0]}), so "
                "blobs they reference would look orphaned; refusing to delete anything"
            )
        return delete_entries(
            manifests_to_delete=manifests_to_delete,
            blobs_to_delete=blobs_to_delete,
            dry_run=dry_run,
        )

    spack.buildcache_prune._fetch_manifests = fetch_manifests_recording_failures
    spack.buildcache_prune._delete_entries_from_cache = delete_unless_reads_failed


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mirror",
        help="name of a configured mirror",
    )
    parser.add_argument(
        "--keeplist",
        default=None,
        help="file containing newline-delimited list of package hashes to keep (optional)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would be pruned without deleting anything",
    )
    args = parser.parse_args()

    mirror = require_mirror_name(args.mirror)
    keeplist: Optional[str] = args.keeplist

    refuse_to_delete_after_failed_reads()
    prune_buildcache(mirror=mirror, keeplist=keeplist, dry_run=args.dry_run)
