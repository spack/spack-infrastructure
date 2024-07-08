import argparse
import boto3
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import gitlab
import multiprocessing as mp
import multiprocessing.pool as pool
import os
from io import StringIO
from urllib.parse import urlparse

import buildcache
import helper
from pruner import DirectPruner, IndexPruner, OrphanPruner

try:
    import sentry_sdk
    sentry_sdk.init(
        # This cron job only runs once weekly,
        # so just record all transactions.
        traces_sample_rate=1.0,
    )
except Exception:
    print("Could not configure sentry.")

# Script Config
PRUNE_REF = os.environ.get("PRUNE_REF", "develop")
SINCE_DAYS = int(os.environ.get("PRUNE_SINCE_DAYS", 14))

# Gitlab API (for fetching artifacts)
GITLAB_URL = os.environ["GITLAB_URL"]
GITLAB_PROJECT = os.environ.get("GITLAB_PROJECT", "spack/spack")
gl = gitlab.Gitlab(GITLAB_URL)

# S3
BUILDCACHE_URL = os.environ["BUILDCACHE_URL"].rstrip("/")

TODAY = datetime.today()
TODAY_STR = TODAY.strftime("%Y.%m.%d")

enable_delete = os.environ.get("AWS_ACCESS_KEY_ID", True)


class Cache:
    def __init__(self):
        self.cache_dir = None

    def write(self, key: str, stream):
        if not self.cache_dir:
            return

        key_path = os.path.join(self.cache_dir, key)
        if os.path.exists(key_path):
            raise Exception(f"Duplicate cache key: {key_path}")

        # This is happening in parallel, try it but don't fail
        if not os.path.isdir(os.path.dirname(key_path)):
            try:
                os.makedirs(os.path.dirname(key_path))
            except Exception:
                pass

        print(f"writing to cache: {key}")
        with open(key_path, "w") as fd:
            if type(stream) == str:
                fd.write(stream)
            elif type(stream) in (dict, list):
                helper.write_json(fd, stream)
            else:
                fd.write(stream.read())

    def read(self, key: str, op=None):
        buf = None
        if self.exists(key):
            print(f"loading from cache: {key}")
            with open(os.path.join(self.cache_dir, key), "r") as fd:
                buf = fd.read()
            if op:
                buf = op(buf)
        return buf

    def exists(self, key: str):
        return os.path.exists(os.path.join(self.cache_dir, key))

    @contextmanager
    def open(self, key: str, mode: str = "r"):
        yield open(os.path.join(self.cache_dir, key), mode)

    def set_dir(self, dirname: str):
        if self.cache_dir:
            raise Exception(f"Cache dir already set to {self.cache_dir}")

        self.cache_dir = dirname
        if not os.path.exists(self.cache_dir):
            print(f"Creating cache directory {self.cache_dir}")
            os.makedirs(self.cache_dir)


cache = Cache()


def _project_jobs_gitlabapi(project, ref: str, start_date=None, since=None):
    if not start_date:
        start_date = datetime.now()
    if not since:
        since = start_date - timedelta(days=SINCE_DAYS)

    for pipeline in project.pipelines.list(iterator=True, updated_before=start_date, updated_after=since, ref=ref):
        print(f"Processing pipeline {pipeline.id}")

        for job in pipeline.jobs.list(iterator=True, scope="success"):
            if not job.stage == 'generate':
                continue

            yield job


def fetch_job_hashes(pipeline_job: gitlab.v4.objects.ProjectPipelineJob):
    jid = pipeline_job.id
    stack = pipeline_job.name.replace("-generate", "")

    # Re-map deprecated stack
    if stack == "deprecated-ci":
        stack = "deprecated"

    job = project.jobs.get(jid, lazy=True)
    try:
        lock_key = f"{pipeline_job.pipeline['id']}/{jid}-lock"
        lock = cache.read(lock_key, op=helper.load_json)
        if not lock:
            artifact_path = "jobs_scratch_dir/concrete_environment/spack.lock"
            artifact = job.artifact(artifact_path)
            lock = helper.load_json(artifact)
            cache.write(lock_key, helper.json.dumps(lock))

        return stack, [h for h in lock["concrete_specs"].keys()]
    except gitlab.exceptions.GitlabHttpError as e:
        print(f"-- Failed to fetch spack.lock for {jid}/{pipeline_job.name}")
        print(f"--   url: {GITLAB_URL}/{GITLAB_PROJECT}/-/jobs/{jid}")
        print("--   ", str(e))
        return "<invalid lock>", []


def configure_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        help="Configuration file containing initial settings",
    )
    parser.add_argument(
        "--start-date",
        help="Starting date for pruning window",
        default=datetime.now(timezone.utc).isoformat(),
    )
    parser.add_argument(
        "--since-days",
        help="Ending date for pruning window",
        default=SINCE_DAYS
    )
    parser.add_argument(
        "-j", "--nprocs",
        help="Numer of process to use",
        type=int,
        metavar="N",
        default=mp.cpu_count(),
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
        "-s", "--stack",
        help="stack to prune from",
        action="append"
    )
    parser.add_argument(
        "--prune-dead-stacks",
        help="delete all files in un-generate stacks",
        action="store_true",
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
    parser.add_argument(
        "--fail-fast",
        help="Fail immediately on an error, otherwise continue until"
             "there is not more work.",
        action="store_true",
    )

    return parser


if __name__ == "__main__":

    parser = configure_parser()
    args = parser.parse_args()

    config = {}
    if args.config:
        with open(args.config, "r") as fd:
            config = helper.load_json(fd)

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

    args.output_dir = args.output_dir.rstrip("/")
    if not os.path.exists(args.output_dir):
        print(f"Creating output directory {args.output_dir}")
        os.makedirs(args.output_dir)

    if not args.snapshot_dir and "snapshot_dir" in config:
        args.snapshot_dir = config["snapshot_dir"]

    if args.snapshot_dir:
        args.snapshot_dir = args.snapshot_dir.rstrip("/")
        cache.set_dir(args.snapshot_dir)

    if not enable_delete and args.delete:
        print("Deletion not possible without AWS credentials")
        exit(1)

    if not args.delete:
        print("=====================================================")
        print("=========  Dry Run  =  Dry Run  =  Dry Run  =========")
        print("=====================================================")
    print(f"--      Parallel Level: {args.nprocs}")
    print(f"--      Pruning Method: {prune_method}")
    print(f"-- Pruning dead stacks: {args.prune_dead_stacks}")

    # Collect a list of hashes referenced on develop in the pruning period
    project = gl.projects.get(GITLAB_PROJECT)
    now = datetime.fromisoformat(args.start_date)
    # now = datetime.now(timezone.utc)
    since = now - timedelta(days=int(args.since_days))
    yesterday = now - timedelta(days=1)

    keep_hashes = defaultdict(set)
    stacks = defaultdict(int)
    if args.stack:
        stacks.update([(k, 0) for k in args.stack])
    else:
        if "stacks" in config:
            stacks.update([(k, 0) for k in config["stacks"].keys()])
        else:
            stacks.update([("_global", 0)])

    if not args.keep_hashes and not (args.delete_only or args.orphaned):
        jobs = [(jid, ) for jid in _project_jobs_gitlabapi(project, ref=PRUNE_REF, start_date=now, since=since)]
        with pool.ThreadPool(args.nprocs) as tp:
            for stack, hashes in tp.imap_unordered(helper.star(fetch_job_hashes), jobs):
                # Skip stacks that are not being pruned
                if not args.stack:
                    stacks[stack] += 1
                elif stack not in stacks:
                    continue

                # TODO
                # Count number of times each stack was seen
                keep_hashes[stack].update(hashes)
                if "_global" in stacks:
                    stacks["_global"] += 1
                    keep_hashes["_global"].update(hashes)

        with cache.open("keep_hashes", "w") as fd:
            helper.write_json(fd, keep_hashes)

        npipeline = max([count for name, count in stacks.items() if not name == "_global"])
        print(f"-- Detected {npipeline} pipelines")
        if not min(stacks.values()) == npipeline:
            print("Warning -- : Not all pipelines had all stacks")
            for stack, count in stacks.items():
                if stack == "_global":
                    continue

                if count == npipeline:
                    continue

                    print(f"Warning --   Found {stack} {count} times")

    elif args.keep_hashes:
        keep_hashes = helper.load_json(args.keep_hashes)
        if args.stack:
            stacks.update([(k, 1) for k in keep_hashes.keys() if k in args.stack])
        else:
            stacks.update([(k, 1) for k in keep_hashes.keys()])

    if not cache.exists("config"):
        with cache.open("config", "w") as fd:
            data = {
                "method": prune_method_safe,
                "start_date": args.start_date,
                "since_days": args.since_days,
            }
            if args.snapshot_dir:
                data["snapshot_dir"] = args.snapshot_dir
            stacks_mirrors = {}
            for stack in stacks:
                if stack == "_global":
                    url = f"{BUILDCACHE_URL}"
                else:
                    url = f"{BUILDCACHE_URL}/{stack}"
                stacks_mirrors[stack] = url

            if stacks_mirrors:
                data["stacks"] = stacks_mirrors

            helper.write_json(fd, data)

    print("-- Pruning stacks: ", ", ".join(stacks.keys()))

    buildcaches = {}
    for stack in stacks:
        if stack == "_global":
            url = f"{BUILDCACHE_URL}/build_cache/"
        else:
            url = f"{BUILDCACHE_URL}/{stack}/build_cache/"

        bc = buildcache.S3BuildCache(url)

        snapshot_key = f"s3-snapshot-{stack}"
        if cache.exists(snapshot_key):
            print(f"-- Loading snapshot {snapshot_key}")
            with cache.open(snapshot_key, "r") as fd:
                bc.load(helper.load_json(fd))
        else:
            print(f"-- Taking snapshot of {url}")
            count = len(bc.snapshot())
            if count == 0:
                print("Error -- Detected empty buildcache")
            else:
                with cache.open(snapshot_key, "w") as fd:
                    helper.write_json(fd, [f.__dict__ for f in bc.list()])

        buildcaches[stack] = bc

    # Prune each stacks buildcache
    for stack in stacks:
        meta_file = None
        prune_file = None
        try:
            print(f"-- Pruning stack: {stack}")
            bc = buildcaches[stack]

            if args.delete_only:
                if os.path.exists(f"{args.output_dir}/{stack}{log_suffix}_prunable.txt"):
                    prune_list_file = f"{args.output_dir}/{stack}{log_suffix}_prunable.txt"
                elif os.path.exists(f"{args.output_dir}/{stack}.txt"):
                    prune_list_file = f"{args.output_dir}/{stack}.txt"
                else:
                    print("--   Could not find prune lists:")
                    print(f"--     {args.output_dir}/{stack}{log_suffix}_prunable.txt")
                    print(f"--     {args.output_dir}/{stack}.txt")
                    continue

                prune_file = open(prune_list_file)

            # In mode that requires computing prune list
            else:
                if args.delete:
                    print(f"--   No delete list file for {stack}, computing...")

                if args.check_index:
                    pruner = IndexPruner(bc, keep_hashes[stack], args)
                elif args.orphaned:
                    pruner = OrphanPruner(bc, since, args)
                elif args.direct:
                    pruner = DirectPruner(bc, keep_hashes[stack], args)

                print("--   Computing prunable hashes")
                prunable_hashes = pruner.determine_prunable_hashes()
                with open(f"{args.output_dir}/prunable-hashes-{stack}{log_suffix}.json", "w") as fd:
                    helper.write_json(fd, prunable_hashes)

                pruned = []
                if prunable_hashes:
                    print("--   Finding prunable files")
                    pruned.extend(pruner.prune(prunable_hashes))
                    print(f"--   Found prunable {len(pruned)} files in buildcache")
                else:
                    print("--   Nothing to prune")
                    continue

                meta_file = StringIO()
                for f in pruned:
                    meta = f"{f.last_modified} s3://{f.bucket_name}/{f.key} {f.method}\n"
                    meta_file.write(meta)
                print(f"--   Writing meta file: {stack}{log_suffix}_meta.txt")
                with open(f"{args.output_dir}/{stack}{log_suffix}_meta.txt", "w") as fd:
                    fd.write(meta_file.getvalue())
                meta_file.seek(0)

                prune_list_file = f"{args.output_dir}/{stack}{log_suffix}_prunable.txt"
                prune_file = StringIO()
                for f in pruned:
                    prune_file.write(f.key)
                    prune_file.write("\n")
                print(f"--   Writing file list: {prune_list_file}")
                with open(f"{prune_list_file}", "w") as fd:
                    fd.write(prune_file.getvalue())
                prune_file.seek(0)

            if args.delete or args.delete_only:
                if not prune_file:
                    raise Exception("")
                lines = [line.strip("\n") for line in prune_file.readlines()]
                if lines:
                    print(f"--   Pruning {stack} build cache")
                    if args.delete:
                        err, fail = bc.delete(lines, processes=args.nprocs)

                        fname_template = f"{args.output_dir}/delete-{{0}}-{stack}{log_suffix}.json"
                        if err:
                            print(f"errors: {stack}")
                            with open(fname_template.format("errors", "w")) as fd:
                                helper.write_json(fd, err)

                        if fail:
                            print(f"failures: {stack}")
                            with open(fname_template.format("failures", "w")) as fd:
                                helper.write_json(fd, fail)
                    else:
                        print(f"--   Would have deleted of {len(lines)} from {stack} buildcache")

                parsed = urlparse(BUILDCACHE_URL)
                if False and parsed.scheme == "s3":
                    s3 = boto3.resource("s3")
                    bucket = s3.Bucket(parsed.netloc)
                    prefix = parsed.path.lstrip("/")
                    if meta_file:
                        bucket.put_object(
                            Key=f"{prefix}/pruning/{TODAY_STR}-{stack}{log_suffix}-meta.txt",
                            Body=meta_file.getvalue().encode(),
                        )

                    bucket.put_object(
                        Key=f"{prefix}/{stack}/pruning/{TODAY_STR}-{stack}{log_suffix}.txt",
                        Body=prune_file.getvalue().encode(),
                    )
        except Exception as e:
            print(f"Error -- Skipping pruning of {stack}")
            if args.fail_fast:
                raise e
            else:
                print(str(e))
        finally:
            if prune_file:
                prune_file.close()
            # continue
