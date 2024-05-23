#!/usr/bin/env python3

import argparse
import helper
import math
import os
import subprocess

from datetime import datetime, timedelta, timezone
from fs_buildcache import FileSystemBuildCache
from pruner import pruner_factory, PRUNER_TYPES

def convert_size(size_bytes):
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    size = round(size_bytes / p, 2)
    return f"{size} {size_name[i]}"

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
        default=0
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
        "--keep-specs",
        help="specs to preserve in the cache (includes dependencies)",
        nargs="+",
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
    parser.add_argument(
        "-m", "--method",
        help="pruning method to use on the cache",
        choices = list(PRUNER_TYPES.keys()),
        default = "direct",
    )

    return parser


def get_cache_hashes_from_specs(*args, **kwargs):
    command = ['spack-python', 'buildcache_query.py', '--format', '{hash}']
    command.extend([*args])
    result = subprocess.check_output(command, universal_newlines=True).strip().split()
    return result

def get_keep_hashes(args: argparse.Namespace):
    keep_hashes=[]
    if args.keep_hashes:
        keep_hashes.extend(helper.load_json(args.keep_hashes))
    if args.keep_specs:
        keep_hashes.extend(get_cache_hashes_from_specs("--deps", *args.keep_specs))
    return keep_hashes

if __name__=="__main__":
    args = configure_parser().parse_args()

    os.makedirs(args.output_dir, exist_ok=True)


    if not args.suffix:
        log_suffix = "_" + args.method
    else:
        log_suffix = args.suffix

    keep_hashes=get_keep_hashes(args)

    cache = FileSystemBuildCache(args.path)

    now = datetime.fromisoformat(args.start_date)
    time_window = now - timedelta(days=args.since_days)

    # combine start date and delta for passing to pruners
    args.start_date = time_window

    pruner = pruner_factory(cache, args.method, args, keep_hashes, since=time_window)

    print("--   Computing prunable hashes")
    prunable_hashes = []
    if args.prune_hashes:
        prunable_hashes.extend( helper.load_json(args.prune_hashes))
    else:
        prunable_hashes.extend(pruner.determine_prunable_hashes())

    prune_hash_file = f"{args.output_dir}/prunable-hashes-{log_suffix}.txt"
    with open(f"{prune_hash_file}", "w") as fd:
        fd.writelines("\n".join(prunable_hashes))

    if prunable_hashes:
        print("--   Finding prunable files")

        pruned = pruner.prune(prunable_hashes)

        pruned_keys = [ obj.key for obj in pruned ]

        print(f"--   Found prunable {len(pruned)} files in buildcache")
        total_size_human = convert_size(sum(obj.size for obj in pruned))
        print(f"-- Total Size of prunable files is {total_size_human}")

        prune_list_file = f"{args.output_dir}/prunable-files-{log_suffix}.txt"
        with open(f"{prune_list_file}", "w") as fd:
            fd.writelines("\n".join(pruned_keys))
    else:
        print("--   Nothing to prune")

    if args.delete:
        print("-- Pruning build cache")
        err, fail = cache.delete(pruned_keys, processes=args.nprocs)
        fname_template = f"{args.output_dir}/delete-{{0}}-{log_suffix}.json"
        if err:
            print(f"errors found")
            with open(fname_template.format("errors")) as fd:
                helper.write_json(fd, err)

        if fail:
            print(f"failures found")
            with open(fname_template.format("failures")) as fd:
                helper.write_json(fd, fail)

