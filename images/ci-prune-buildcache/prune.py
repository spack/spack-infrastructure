#!/usr/bin/env spack-python
"""
This script is meant to be run using:
    `spack python prune.py`
"""

import argparse
from typing import Optional

import sentry_sdk

from spack.buildcache_prune import prune_buildcache
from spack.mirrors.utils import require_mirror_name

sentry_sdk.init(
    # This cron job only runs once weekly,
    # so just record all transactions.
    traces_sample_rate=1.0,
)

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
    args = parser.parse_args()

    mirror = require_mirror_name(args.mirror)
    keeplist: Optional[str] = args.keeplist

    prune_buildcache(mirror=mirror, keeplist=keeplist)
