#!/usr/bin/env python3

import argparse
import dateparser
import github
import gitlab
import json
import os
import sys

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
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


def fetch_and_cache_job(project: Project, job_id: int, job_name: str, tmpdir: Path) -> Tuple[str, List[str]]:
    """Fetch hashes from a generate job's spack.lock artifact."""
    job = project.jobs.get(job_id, lazy=True)
    stack_name = job_name.replace("-generate", "")
    stack_env_dir = (tmpdir / f"{stack_name}/{job.id}/").resolve()

    if not stack_name:
        print(f"Skipping: {job_id}: {job_name}")
        return "", [], None

    if not (stack_env_dir / "spack.lock").exists():
        artifact_path = f"jobs_scratch_dir/{stack_name}/concrete_environment/spack.lock"
        artifact = job.artifact(artifact_path)
        # Save the concrete lockfile to a env_dir
        # This will be used later to create a new index for the stack
        # Make parents as needed
        # Each stack should be unique for a job
        stack_env_dir.mkdir(parents=True, exist_ok=False)
        (stack_env_dir / "spack.lock").write_bytes(artifact)
        lock = json.loads(artifact)
    else:
        with (stack_env_dir / "spack.lock").open("r") as fd:
            lock = json.load(fd)

    # Always write this, doesn't hurt and avoid odd errors
    (stack_env_dir / "spack.yaml").write_text("spack: {}")
    hashes = list(lock["concrete_specs"].keys())
    return stack_name, hashes, stack_env_dir


def process_pipeline(
    project: Project, pipeline: ProjectPipeline, output_dir: Path, max_workers: int = 10, cat_env: bool = True
) -> set[str]:
    """Process all generate jobs in a pipeline in parallel."""
    print(
        f"\nProcessing pipeline {pipeline.id}...",
    )

    # Collect all generate jobs
    generate_jobs: List[Tuple[int, str]] = []
    for job in pipeline.jobs.list(iterator=True, scope="success"):
        if job.stage == "generate":
            generate_jobs.append((job.id, job.name))

    # Fetch artifacts in parallel
    keep_hashes = set()
    if generate_jobs:
        stack_envs: dict[str, dict] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_job = {
                executor.submit(fetch_and_cache_job, project, job_id, job_name, output_dir / ".tmp"): (
                    job_id,
                    job_name,
                )
                for job_id, job_name in generate_jobs
            }

            for future in as_completed(future_to_job):
                stack_name, hashes, env_dir = future.result()
                if not hashes:
                    continue

                keep_hashes.update(hashes)

                if not cat_env:
                    continue

                with (env_dir / "spack.lock").open("r") as fd:
                    env = json.load(fd)

                stack_envs[stack_name] = env

    return keep_hashes, stack_envs


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
        default="14 days ago",
        help="Number of days to look back for pipelines",
    )
    parser.add_argument(
        "--snapshots-since",
        default="1 month ago",
        help="Number of days to look back for pipelines",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=os.cpu_count(),
        help="Maximum number of parallel workers for fetching artifacts",
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
    pipelines_since = dateparser.parse(args.pipelines_since + " UTC")
    snapshots_since = dateparser.parse(args.snapshots_since + " UTC")

    print(
        f"Fetching pipelines from {args.ref} between {pipelines_since.isoformat()} and {now.isoformat()}...",
    )

    # Collect rolling window pipelines first
    pipelines = [(p, True) for p in list(
        project.pipelines.list(
            iterator=True, updated_before=now, updated_after=pipelines_since, ref=args.ref
        )
    )]

    snapshot_shas = []
    # TODO: Collect snapshot pipelines (these are not included in the rolling window)
    gh = github.Github(auth=github.Auth.Token(GITHUB_TOKEN))
    gh_project = gh.get_repo(args.project)
    refs = gh_project.get_git_matching_refs("snapshots")
    for ref in refs:
        # Snapshot format is snapshots/develop-YYYY-MM-DD
        parts = ref.ref.split("/")
        date = parts[-1].split("-", 1)[-1]
        if date == "latest":
            continue
        snapshot_date = datetime.strptime(date, "%Y-%M-%d")
        snapshot_date = snapshot_date.replace(tzinfo = timezone.utc)
        if snapshot_date >= snapshots_since:
            snapshot_shas.append(ref.object.sha)

    # Grab pipelines that are older than the window and newer than the snapshot cut-off
    # All of the snapshot hashes in the window will arleady be accounted for.
    snapshot_pipelines = [(p, False) for p in list(
        project.pipelines.list(
            iterator=True, updated_before=pipelines_since, updated_after=snapshots_since, ref=args.ref
        )
    ) if p.sha in snapshot_shas]

    print(
        f"Found {len(pipelines)} pipelines to process",
    )

    # Process pipelines in parallel
    all_keep_hashes = set()
    combined_stack_envs: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        future_to_pipeline = {
            executor.submit(
                process_pipeline, project, pipeline, output_dir, args.max_workers, cat_stack
            ): pipeline.id
            for pipeline, cat_stack in pipelines + snapshot_pipelines
        }

        for future in as_completed(future_to_pipeline):
            pipeline_hashes, stack_envs  = future.result()
            all_keep_hashes.update(pipeline_hashes)
            for stack_name, env in stack_envs.items():
                cur_env = combined_stack_envs.get(stack_name)
                if cur_env:
                    # Update concrete specs
                    cur_env["concrete_specs"].update(
                        env["concrete_specs"]
                    )
                    # Add new roots
                    all_roots = set(r["hash"] for r in combined_stack_envs[stack_name]["roots"])
                    roots = [r for r in env["roots"] if r["hash"] not in all_roots]
                    cur_env["roots"].extend(
                        roots
                    )
                else:
                    cur_env = env

                combined_stack_envs[stack_name] = cur_env

    for stack_name in combined_stack_envs:
        # Concatenate all of the environments for pipelines into a single common environment
        all_env_dir = (output_dir / f"stacks/{stack_name}/").resolve()
        all_env_dir.mkdir(parents=True, exist_ok=True)

        (all_env_dir / "spack.yaml").write_text("spack: {}")
        with (all_env_dir / "spack.lock").open("w") as fd:
            json.dump(combined_stack_envs[stack_name], fd)

    print(
        f"\nProcessed {len(pipelines)} pipelines",
    )
    print(
        f"Total unique hashes to keep: {len(all_keep_hashes)}",
    )

    keep_list_f = output_dir / "keeplist.txt"
    with keep_list_f.open("w") as fd:
        fd.write("\n".join(sorted(all_keep_hashes)))
    print(f"Keep list written to {keep_list_f.as_posix()}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
