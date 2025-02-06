import argparse
import os
import sys
from datetime import datetime

import sentry_sdk

from .common import (
    get_workdir_context,
    list_prefix_contents,
    spec_catalogs_from_listing,
)

sentry_sdk.init(traces_sample_rate=1.0)


################################################################################
# Migrate method
#
# Expects public and secret parts of whatever key was used to sign the existing
# binaries in the mirror to be already imported and ready to use for verifying
# and subsequent re-signing.
def migrate(mirror_url: str, workdir: str, force: bool = False):
    listing_file = os.path.join(workdir, "full_listing.txt")
    tmp_storage_dir = os.path.join(workdir, "specfiles")

    if not os.path.isdir(tmp_storage_dir):
        os.makedirs(tmp_storage_dir)

    if not os.path.isfile(listing_file) or force:
        list_prefix_contents(mirror_url, listing_file)

    all_catalogs = spec_catalogs_from_listing(listing_file)

    print(f"Summary of catalogs:")
    for prefix, catalog in all_catalogs.items():
        print(f"  {prefix}: {len(catalog)} specs")


################################################################################
# Entry point
def main():
    start_time = datetime.now()
    print(f"Migrate script started at {start_time}")

    parser = argparse.ArgumentParser(
        prog="publish.py",
        description="Publish specs from stack-specific mirrors to the root",
    )

    parser.add_argument(
        "mirror", type=str, default=None, help="URL of mirror to migrate"
    )

    parser.add_argument(
        "-w",
        "--workdir",
        default=None,
        help="A scratch directory, defaults to a tmp dir",
    )

    parser.add_argument(
        "-f",
        "--force",
        default=False,
        action="store_true",
        help="Refetch files if they already exist",
    )

    args = parser.parse_args()
    if not args.mirror:
        print("Missing required mirror argument")
        sys.exit(1)

    # If the cli didn't provide a working directory, we will create (and clean up)
    # a temporary directory using this workdir context
    with get_workdir_context(args.workdir) as workdir:
        migrate(args.mirror, workdir=workdir, force=args.force)

    end_time = datetime.now()
    elapsed = end_time - start_time
    print(f"Migrate script finished at {end_time}, elapsed time: {elapsed}")


################################################################################
#
if __name__ == "__main__":
    main()
