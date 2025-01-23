from itertools import batched

from django.db import connections, transaction
import djclick as click

from analytics.core.models import JobDataDimension


@click.command()
@click.option("--dry-run", is_flag=True, default=False)
def migrate_exit_codes(dry_run: bool) -> None:
    failed_jobs = JobDataDimension.objects.filter(status="failed")

    BATCH_SIZE = 5_000
    for job_ids in batched(
        failed_jobs.values_list("job_id", flat=True).iterator(chunk_size=BATCH_SIZE), BATCH_SIZE
    ):
        with connections["gitlab"].cursor() as cursor:
            QUERY = "SELECT build_id, exit_code FROM public.ci_builds_metadata WHERE build_id IN %s"
            cursor.execute(QUERY, [tuple(job_ids)])
            rows = cursor.fetchall()

        job_id_to_exit_code_mapping = {row[0]: row[1] for row in rows if row[1] is not None}

        if dry_run:
            click.echo(f"Would update {len(job_id_to_exit_code_mapping.keys())} jobs")
            continue

        jobs_to_update = list(
            JobDataDimension.objects.filter(job_id__in=job_id_to_exit_code_mapping.keys())
        )
        for job in jobs_to_update:
            job.job_exit_code = job_id_to_exit_code_mapping[job.job_id]

        JobDataDimension.objects.bulk_update(jobs_to_update, ["job_exit_code"])
