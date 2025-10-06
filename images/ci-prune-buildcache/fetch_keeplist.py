#!/usr/bin/env python3

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import gitlab
from gitlab.v4.objects import Project, ProjectPipeline
import sys
from typing import List, Set, Tuple
import sentry_sdk

sentry_sdk.init(
    traces_sample_rate=1.0,
)


def fetch_job_hashes(project: Project, job_id: int, job_name: str) -> List[str]:
    """Fetch hashes from a generate job's spack.lock artifact."""
    job = project.jobs.get(job_id, lazy=True)
    stack_name = job_name.replace("-generate", "")
    artifact_path = f"jobs_scratch_dir/{stack_name}/concrete_environment/spack.lock"
    artifact = job.artifact(artifact_path)
    lock = json.loads(artifact)
    hashes = list(lock["concrete_specs"].keys())
    return hashes


def process_pipeline(
    project: Project, pipeline: ProjectPipeline, max_workers: int = 10
) -> Set[str]:
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
    all_hashes: Set[str] = set()
    if generate_jobs:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_job = {
                executor.submit(fetch_job_hashes, project, job_id, job_name): (
                    job_id,
                    job_name,
                )
                for job_id, job_name in generate_jobs
            }

            for future in as_completed(future_to_job):
                hashes = future.result()
                all_hashes.update(hashes)

    return all_hashes


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch keep hashes from GitLab pipelines"
    )
    parser.add_argument(
        "--gitlab-url",
        required=True,
        help="GitLab instance URL",
    )
    parser.add_argument(
        "--project",
        required=True,
        help="GitLab project path (e.g., spack/spack-packages)",
    )
    parser.add_argument(
        "--ref",
        default="develop",
        help="Git ref to fetch pipelines from",
    )
    parser.add_argument(
        "--since-days",
        type=int,
        default=14,
        help="Number of days to look back for pipelines",
    )
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        help="Output file for keep list",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=os.cpu_count(),
        help="Maximum number of parallel workers for fetching artifacts",
    )

    args = parser.parse_args()

    # Connect to GitLab
    print(
        f"Connecting to {args.gitlab_url}...",
    )
    gl = gitlab.Gitlab(url=args.gitlab_url, retry_transient_errors=True, timeout=60)
    project: Project = gl.projects.get(args.project)

    # Calculate date range
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=args.since_days)

    print(
        f"Fetching pipelines from {args.ref} between {since.isoformat()} and {now.isoformat()}...",
    )

    # Collect all pipelines first
    pipelines = list(
        project.pipelines.list(
            iterator=True, updated_before=now, updated_after=since, ref=args.ref
        )
    )

    print(
        f"Found {len(pipelines)} pipelines to process",
    )

    # Process pipelines in parallel
    all_hashes: Set[str] = set()
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        future_to_pipeline = {
            executor.submit(
                process_pipeline, project, pipeline, args.max_workers
            ): pipeline.id
            for pipeline in pipelines
        }

        for future in as_completed(future_to_pipeline):
            hashes = future.result()
            all_hashes.update(hashes)

    print(
        f"\nProcessed {len(pipelines)} pipelines",
    )
    print(
        f"Total unique hashes to keep: {len(all_hashes)}",
    )

    # Write keeplist file (one hash per line)
    with open(args.output, "w") as f:
        for hash_val in sorted(all_hashes):
            f.write(f"{hash_val}\n")

    print(
        f"Keep list written to {args.output}",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
