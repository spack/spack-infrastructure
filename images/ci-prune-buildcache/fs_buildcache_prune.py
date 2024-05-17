#!/usr/bin/env python3
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
        "-o", "--output-dir",
        default=os.getcwd(),
        help="output directory",
    )
    parser.add_argument(
        "-S", "--suffix",
        help="logging file suffix",
    )
    parser.add_argument(
        "-D", "--delete",
        help="attempt to delete the files",
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

    os.makedirs(args.output_dir, exist_ok=True)

    if args.check_index:
        prune_method = "Index Based"
    elif args.orphaned:
        prune_method = "Orphaned"
    elif args.direct:
        prune_method = "Direct"
    else:
        prune_method = config.get("method", "Direct")

    prune_method_safe = "_".join(prune_method.split()).lower()
    if not args.suffix:
        log_suffix = "_" + prune_method_safe
    else:
        log_suffix = args.suffix

    keep_hashes=[]
    if args.keep_hashes:
        keep_hashes = helper.load_json(args.keep_hashes)

    cache = FileSystemBuildCache(args.path)

    now = datetime.fromisoformat(args.start_date)
    time_window = now - timedelta(days=args.since_days)

    pruner = pruner_factory(cache, args, keep_hashes, since=time_window)

    print("--   Computing prunable hashes")
    prunable_hashes = pruner.determine_prunable_hashes()
    prune_hash_file = f"{args.output_dir}/prunable-hashes-{log_suffix}.txt"
    with open(f"{prune_hash_file}", "w") as fd:
        fd.writelines("\n".join(prunable_hashes))

    if prunable_hashes:
        print("--   Finding prunable files")

        pruned = pruner.prune(prunable_hashes)
        pruned_keys = [ obj.key for obj in pruned ]

        print(f"--   Found prunable {len(pruned)} files in buildcache")

        prune_list_file = f"{args.output_dir}/prunable-files-{log_suffix}.txt"
        with open(f"{prune_list_file}", "w") as fd:
            fd.writelines("\n".join(pruned_keys))
    else:
        print("--   Nothing to prune")

    if args.delete:
        print("-- Pruning build cache")
        err, fail = cache.delete(prune_keys, process=args.nprocs)
        fname_template = f"{args.output_dir}/delete-{{0}}-{log_suffix}.json"
        if err:
            print(f"errors found")
            with open(fname_template.format("errors")) as fd:
                helper.write_json(fd, err)

        if fail:
            print(f"failures found")
            with open(fname_template.format("failures")) as fd:
                helper.write_json(fd, fail)


