import argparse
import helper
import os

from datetime import datetime, timedelta, timezone
from fs_buildcache import FileSystemBuildCache
from pruner import pruner_factory


def configure_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "path",
        help="location of the buildcache",
    )
    parser.add_argument(
        "--start-date",
        help="Starting date for pruning window",
        default=datetime.now(timezone.utc).isoformat(),
    )
    parser.add_argument(
        "--since-days",
        help="Ending date for pruning window",
        type=int,
        default=30
    )
    parser.add_argument(
        "-j", "--nprocs",
        help="Numer of process to use",
        type=int,
        metavar="N",
        default=1
    )
    parser.add_argument(
        "--prune-hashes",
        help="json file with hash list to prune",
        type=argparse.FileType("r"),
        metavar="prune.json",
    )
    parser.add_argument(
        "--keep-hashes",
        help="json file with hash list to keep",
        type=argparse.FileType("r"),
        metavar="keep.json",
    )
    parser.add_argument(
        "--snapshot-dir",
        help="Directory containering snapshots of mirrors."
             "If it exists they will be loaded, if it does not they will be written",
        metavar="DIR",
    )
    parser.add_argument(
        "-o", "--output-dir",
        help="output directory",
    )
    parser.add_argument(
        "-S", "--suffix",
        help="logging file suffix",
    )
    parser.add_argument(
        "-D", "--delete",
        help="Dry run",
        action="store_true",
    )

    pruner_group = parser.add_mutually_exclusive_group(required=True)
    pruner_group.add_argument(
        "--direct",
        help="use the buildcache index to check for buildcache hashes",
        action="store_true",
    )
    pruner_group.add_argument(
        "--orphaned",
        help="Enable orphan pruning",
        action="store_true",
    )
    pruner_group.add_argument(
        "--check-index",
        help="use the buildcache index to check for buildcache hashes",
        action="store_true",
    )
    parser.add_argument(
        "--delete-only",
        help="use the buildcache index to check for buildcache hashes",
        action="store_true",
    )

    return parser


if __name__=="__main__":

    args = configure_parser().parse_args()
    keep_hashes=[]
    if args.keep_hashes:
        keep_hashes = helper.load_json(args.keep_hashes)

    cache = FileSystemBuildCache(args.path)

    now = datetime.fromisoformat(args.start_date)
    time_window = now - timedelta(days=args.since_days)

    pruner = pruner_factory(cache, args, keep_hashes, since=time_window)

    print("--   Computing prunable hashes")
    prunable_hashes = pruner.determine_prunable_hashes()
    with open(f"log.json", "w") as fd:
        helper.write_json(fd, prunable_hashes)

    pruned = []
    if prunable_hashes:
        print("--   Finding prunable files")
        pruned.extend(pruner.prune(prunable_hashes))
        pruned_keys = [ obj.key for obj in pruned ]
        print(f"--   Found prunable {len(pruned)} files in buildcache")
        with open(f"files_to_prune.json", "w") as fd:
            helper.write_json(fd, pruned_keys)
    else:
        print("--   Nothing to prune")

