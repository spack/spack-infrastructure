#!/usr/bin/env python3

import argparse
import dateparser
import github
import gitlab
import json
import os
import shutil
import sys

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from gitlab.v4.objects import Project, ProjectPipeline
from pathlib import Path
from typing import Dict, List, Set, Tuple

try:
    import sentry_sdk

    sentry_sdk.init(
        traces_sample_rate=1.0,
    )
except ImportError:
    print("Running without sentry")


GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")


class SnapshotError(Exception):
    """An unexpired snapshot's specs could not be determined."""


def past_date(value: str) -> datetime:
    """Parse a --*-since value (e.g. '14 days ago' or '2026-10-01') as a UTC datetime.

    Dates in the future are rejected: a future --snapshots-since would treat every
    snapshot as expired and let their specs be pruned.
    """
    parsed = dateparser.parse(
        value, settings={"TIMEZONE": "UTC", "RETURN_AS_TIMEZONE_AWARE": True}
    )
    if parsed is None:
        raise argparse.ArgumentTypeError(f"cannot parse {value!r} as a date")
    if parsed > datetime.now(timezone.utc):
        raise argparse.ArgumentTypeError(f"{value!r} ({parsed.isoformat()}) is in the future")
    return parsed


def list_generate_jobs(pipeline: ProjectPipeline) -> List[Tuple[int, str]]:
    """Return (job id, job name) for each successful generate job in a pipeline."""
    return [
        (job.id, job.name)
        for job in pipeline.jobs.list(iterator=True, scope="success")
        if job.stage == "generate"
    ]


def fetch_and_cache_job(
    project: Project, job_id: int, job_name: str, tmpdir: Path
) -> Tuple[str, dict | None]:
    """Fetch a generate job's spack.lock artifact, or reuse the copy cached in tmpdir.

    Returns the stack name and the parsed lockfile (None if the job has no stack name).
    """
    stack_name = job_name.replace("-generate", "")
    if not stack_name:
        print(f"Skipping: {job_id}: {job_name}")
        return "", None

    job = project.jobs.get(job_id, lazy=True)
    stack_env_dir = (tmpdir / f"{stack_name}/{job.id}/").resolve()

    if not (stack_env_dir / "spack.lock").exists():
        artifact_path = f"jobs_scratch_dir/{stack_name}/concrete_environment/spack.lock"
        artifact = job.artifact(artifact_path)
        # Cache the concrete lockfile; each job has its own directory
        stack_env_dir.mkdir(parents=True, exist_ok=True)
        (stack_env_dir / "spack.lock").write_bytes(artifact)
        lock = json.loads(artifact)
    else:
        with (stack_env_dir / "spack.lock").open("r") as fd:
            lock = json.load(fd)

    return stack_name, lock


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch keep hashes from GitLab pipelines"
    )
    parser.add_argument(
        "--gitlab-url",
        default="https://gitlab.spack.io",
        help="GitLab instance URL",
    )
    parser.add_argument(
        "--project",
        default="spack/spack-packages",
        help="GitLab project path (e.g., spack/spack-packages)",
    )
    parser.add_argument(
        "--ref",
        default="develop",
        help="Git ref to fetch pipelines from",
    )
    parser.add_argument(
        "--pipelines-since",
        type=past_date,
        default="14 days ago",
        help="How far back to look for pipelines, as a dateparser phrase or date "
        "(e.g. '14 days ago', '2026-10-01'; default: %(default)s)",
    )
    parser.add_argument(
        "--snapshots-since",
        type=past_date,
        default="2 months ago",
        help="How far back to look for snapshot pipelines, as a dateparser phrase or date "
        "(e.g. '2 months ago'; default: %(default)s)",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=8,
        help="Maximum number of concurrent GitLab requests (default: %(default)s)",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        default=".",
        help="Output directory."
    )

    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()

    # Connect to GitLab
    print(
        f"Connecting to {args.gitlab_url}...",
    )
    gl = gitlab.Gitlab(url=args.gitlab_url, retry_transient_errors=True, timeout=60)
    project: Project = gl.projects.get(args.project)

    # Calculate date range
    now = datetime.now(timezone.utc)
    pipelines_since = args.pipelines_since
    snapshots_since = args.snapshots_since

    print(
        f"Fetching pipelines from {args.ref} between {pipelines_since.isoformat()} and {now.isoformat()}...",
    )

    # Collect rolling window pipelines first
    pipelines = [(p, True) for p in list(
        project.pipelines.list(
            iterator=True, updated_before=now, updated_after=pipelines_since, ref=args.ref
        )
    )]

    # Collect snapshots that have not yet expired. Each snapshot ref points at the commit
    # of a successful develop pipeline (see images/snapshot-release-tags), which may have
    # finished days before the snapshot was taken, so look pipelines up by sha.
    # Snapshot views are named after their ref, e.g. snapshots/develop-YYYY-MM-DD.
    snapshot_views: Dict[str, List[str]] = {}  # sha -> view names
    unexpired_views = []
    if GITHUB_TOKEN:
        gh = github.Github(auth=github.Auth.Token(GITHUB_TOKEN))
    else:
        # Snapshot refs are public; anonymous access only has a lower rate limit
        print("GITHUB_TOKEN is not set; reading snapshot refs from GitHub anonymously")
        gh = github.Github()
    gh_project = gh.get_repo(args.project)
    refs = gh_project.get_git_matching_refs("snapshots")
    for ref in refs:
        view = ref.ref.removeprefix("refs/")
        date = view.split("/")[-1].split("-", 1)[-1]
        if date == "latest":
            # update_views.py decides on develop-latest from the specs its view lists
            continue
        snapshot_date = datetime.strptime(date, "%Y-%m-%d")
        snapshot_date = snapshot_date.replace(tzinfo = timezone.utc)
        if snapshot_date >= snapshots_since:
            unexpired_views.append(view)
            snapshot_views.setdefault(ref.object.sha, []).append(view)

    window_ids = {p.id for p, _ in pipelines}
    snapshot_pipeline_ids: Dict[str, List[int]] = {}  # sha -> pipeline ids
    snapshot_pipelines = []
    for sha, views in snapshot_views.items():
        found = list(project.pipelines.list(iterator=True, sha=sha, ref=args.ref))
        if not found:
            # Without a pipeline nothing protects this snapshot's specs, so stop here
            # rather than over-prune.
            raise SnapshotError(
                f"No {args.ref} pipeline found for snapshot {', '.join(views)} (sha {sha}); "
                "aborting to avoid pruning its specs"
            )
        snapshot_pipeline_ids[sha] = [p.id for p in found]
        # Pipelines already in the rolling window are processed there
        snapshot_pipelines.extend((p, False) for p in found if p.id not in window_ids)

    print(
        f"Found {len(pipelines)} pipelines and {len(snapshot_pipelines)} additional "
        f"snapshot pipelines to process ({len(snapshot_views)} unexpired snapshots)",
    )

    # Find every successful generate job, then fetch their lockfiles. Each step uses a
    # single pool, so at most --max-workers requests go to GitLab at a time.
    all_pipelines = pipelines + snapshot_pipelines
    # in_views: whether the pipeline's specs go into the stack view indices (only
    # rolling-window pipelines; snapshot-only pipelines just add to the keep list)
    generate_jobs = []  # (pipeline id, job id, job name, in_views)
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        future_to_pipeline = {
            executor.submit(list_generate_jobs, pipeline): (pipeline, in_views)
            for pipeline, in_views in all_pipelines
        }
        for future in as_completed(future_to_pipeline):
            pipeline, in_views = future_to_pipeline[future]
            jobs = future.result()
            print(f"Pipeline {pipeline.id}: {len(jobs)} generate jobs")
            generate_jobs.extend((pipeline.id, job_id, job_name, in_views) for job_id, job_name in jobs)

    print(f"Fetching lockfiles for {len(generate_jobs)} generate jobs...")
    all_keep_hashes = set()
    hash_counts: Dict[int, int] = {pipeline.id: 0 for pipeline, _ in all_pipelines}
    # Each stack's hashes from the rolling window, for its view index. Only the hashes
    # are kept, so lockfiles in different formats never need to be merged.
    stack_hashes: Dict[str, Set[str]] = {}
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        future_to_job = {
            executor.submit(
                fetch_and_cache_job, project, job_id, job_name, output_dir / ".tmp"
            ): (pipeline_id, in_views)
            for pipeline_id, job_id, job_name, in_views in generate_jobs
        }

        for future in as_completed(future_to_job):
            pipeline_id, in_views = future_to_job[future]
            stack_name, env = future.result()
            if not env or not env["concrete_specs"]:
                continue

            hash_counts[pipeline_id] += len(env["concrete_specs"])
            all_keep_hashes.update(env["concrete_specs"])

            if in_views:
                stack_hashes.setdefault(stack_name, set()).update(env["concrete_specs"])

    for sha, ids in snapshot_pipeline_ids.items():
        if not any(hash_counts.get(i) for i in ids):
            raise SnapshotError(
                f"No specs found in pipelines {ids} for snapshot "
                f"{', '.join(snapshot_views[sha])} (sha {sha}); "
                "aborting to avoid pruning its specs"
            )

    # Start from an empty directory: entrypoint.sh treats every file in it as an
    # active stack, so a file left by an earlier run would keep a retired stack alive
    stacks_dir = output_dir / "stacks"
    shutil.rmtree(stacks_dir, ignore_errors=True)
    stacks_dir.mkdir(parents=True)
    for stack_name, hashes in stack_hashes.items():
        with (stacks_dir / f"{stack_name}.txt").open("w") as fd:
            for hash_val in sorted(hashes):
                fd.write(f"{hash_val}\n")
    print(f"Hashes for {len(stack_hashes)} stack views written to {stacks_dir.as_posix()}")

    print(
        f"\nProcessed {len(all_pipelines)} pipelines",
    )
    print(
        f"Total unique hashes to keep: {len(all_keep_hashes)}",
    )

    keep_list_f = output_dir / "keeplist.txt"
    with keep_list_f.open("w") as fd:
        for hash_val in sorted(all_keep_hashes):
            fd.write(f"{hash_val}\n")
    print(f"Keep list written to {keep_list_f.as_posix()}")

    # Unexpired snapshot views; update_views.py empties any other snapshot view
    snapshot_views_f = output_dir / "snapshot_views.json"
    with snapshot_views_f.open("w") as fd:
        json.dump({"unexpired": sorted(unexpired_views)}, fd, indent=2)
    print(f"Snapshot views written to {snapshot_views_f.as_posix()}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
