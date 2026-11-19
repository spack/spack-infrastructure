import json
from datetime import UTC, datetime
from itertools import batched

import djclick as click
from analytics.core.management.commands.backfill_jobs import fetch_webhook_payloads
from analytics.core.models.facts import JobFact
from analytics.job_processor import process_job
from django.db import connections
from tqdm import tqdm

# Query to fetch the IDs of the `wait-for-build-jobs` jobs that finished within the date range
ID_FETCH_QUERY = """
    SELECT p_ci_builds.id
    FROM p_ci_builds
    WHERE
        p_ci_builds.project_id = 57  -- The project ID for spack/spack-packages
        AND p_ci_builds.name = 'wait-for-build-jobs'
        AND p_ci_builds.finished_at BETWEEN %(start)s AND %(end)s
        AND p_ci_builds.type = 'Ci::Build'
        AND p_ci_builds.status IN ('success', 'failed')
    ORDER BY p_ci_builds.id
"""

BATCH_SIZE = 1_000


@click.command()
@click.option(
    "--start",
    type=click.DateTime(),
    required=True,
    help="Backfill jobs that finished after this datetime (UTC).",
)
@click.option(
    "--end",
    type=click.DateTime(),
    default=None,
    help="Backfill jobs that finished before this datetime (UTC). Defaults to now.",
)
@click.option(
    "--dry-run",
    "dry_run",
    is_flag=True,
    help="Only report the number of jobs that would be processed.",
)
def backfill_wait_for_build_jobs(
    start: datetime, end: datetime | None, dry_run: bool
) -> None:
    """
    Process the `wait-for-build-jobs` jobs that were dropped as an unrecognized job type.

    These jobs have been failing to process since they were introduced (first seen 2025-06-12).
    Jobs that already have a job fact are skipped, so it's safe to run this more than once, or
    over a range that was already (partially) backfilled.

    A job that fails to process is reported and skipped, rather than aborting the backfill.
    """
    start = start.replace(tzinfo=UTC)
    end = (end or datetime.now(UTC)).replace(tzinfo=UTC)

    with connections["gitlab"].cursor() as cursor:
        click.echo(f"Querying for jobs between <{start}> and <{end}>...")
        cursor.execute(ID_FETCH_QUERY, {"start": start, "end": end})
        build_ids: list[int] = [row[0] for row in cursor.fetchall()]

        # Don't process jobs that already have a job fact
        existing_job_facts: set[int] = set()
        for ids_chunk in batched(build_ids, BATCH_SIZE):
            existing_job_facts.update(
                JobFact.objects.filter(job_id__in=ids_chunk).values_list(
                    "job_id", flat=True
                )
            )
        build_ids = [_id for _id in build_ids if _id not in existing_job_facts]

        click.echo(f"Found {len(build_ids)} unprocessed wait-for-build-jobs jobs.")
        if dry_run or not build_ids:
            return

        failed: dict[str, int] = {}
        pbar = tqdm(total=len(build_ids))
        for ids_chunk in batched(build_ids, BATCH_SIZE):
            for webhook_dict in fetch_webhook_payloads(cursor, ids_chunk):
                pbar.set_description(
                    f"Processing records for {webhook_dict['build_started_at']}"
                )

                try:
                    process_job(json.dumps(webhook_dict))
                except Exception as e:  # noqa: BLE001
                    # Keep going, so that one bad job doesn't abort the whole backfill
                    reason = type(e).__name__
                    failed[reason] = failed.get(reason, 0) + 1
                    pbar.write(f"Job {webhook_dict['build_id']} failed: {e!r}")

                pbar.update(1)
        pbar.close()

    click.echo(f"Jobs processed: {len(build_ids) - sum(failed.values())}")
    for reason, count in sorted(failed.items()):
        click.echo(f"Jobs failed ({reason}): {count}")
