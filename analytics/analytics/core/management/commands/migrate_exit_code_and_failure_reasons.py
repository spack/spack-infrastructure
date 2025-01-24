from itertools import batched

from django.db import connections
import djclick as click

from analytics.core.models import JobDataDimension


def _migrate_exit_codes(dry_run: bool) -> None:
    # Only failed jobs have an exit code in the database
    failed_jobs = JobDataDimension.objects.filter(status="failed")

    # Batch the job ids to avoid hitting the max query length/memory limit
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

        click.echo(f"Updating {len(job_id_to_exit_code_mapping.keys())} jobs")
        jobs_to_update = list(
            JobDataDimension.objects.filter(job_id__in=job_id_to_exit_code_mapping.keys())
        )
        for job in jobs_to_update:
            job.job_exit_code = job_id_to_exit_code_mapping[job.job_id]

        JobDataDimension.objects.bulk_update(jobs_to_update, ["job_exit_code"])


# From https://gitlab.com/gitlab-org/gitlab/-/blob/master/app/models/concerns/enums/ci/commit_status.rb#L7
FAILURE_REASONS = {
    None: "unknown_failure",
    1: "script_failure",
    2: "api_failure",
    3: "stuck_or_timeout_failure",
    4: "runner_system_failure",
    5: "missing_dependency_failure",
    6: "runner_unsupported",
    7: "stale_schedule",
    8: "job_execution_timeout",
    9: "archived_failure",
    10: "unmet_prerequisites",
    11: "scheduler_failure",
    12: "data_integrity_failure",
    13: "forward_deployment_failure",  # Deprecated in favor of failed_outdated_deployment_job.
    14: "user_blocked",
    15: "project_deleted",
    16: "ci_quota_exceeded",
    17: "pipeline_loop_detected",
    18: "no_matching_runner",
    19: "trace_size_exceeded",
    20: "builds_disabled",
    21: "environment_creation_failure",
    22: "deployment_rejected",
    23: "failed_outdated_deployment_job",
    1_000: "protected_environment_failure",
    1_001: "insufficient_bridge_permissions",
    1_002: "downstream_bridge_project_not_found",
    1_003: "invalid_bridge_trigger",
    1_004: "upstream_bridge_project_not_found",
    1_005: "insufficient_upstream_permissions",
    1_006: "bridge_pipeline_is_child_pipeline",  # not used anymore, but cannot be deleted because of old data
    1_007: "downstream_pipeline_creation_failed",
    1_008: "secrets_provider_not_found",
    1_009: "reached_max_descendant_pipelines_depth",
    1_010: "ip_restriction_failure",
    1_011: "reached_max_pipeline_hierarchy_size",
    1_012: "reached_downstream_pipeline_trigger_rate_limit",
}


def _migrate_failure_reasons(dry_run: bool) -> None:
    # All success jobs have a failure reason of "unknown_failure"
    JobDataDimension.objects.filter(status="success").update(
        gitlab_failure_reason="unknown_failure"
    )

    failed_jobs = JobDataDimension.objects.filter(status="failed")

    BATCH_SIZE = 5_000
    for job_ids in batched(
        failed_jobs.values_list("job_id", flat=True).iterator(chunk_size=BATCH_SIZE), BATCH_SIZE
    ):
        with connections["gitlab"].cursor() as cursor:
            QUERY = "SELECT id, failure_reason FROM public.ci_builds WHERE id IN %s"
            cursor.execute(QUERY, [tuple(job_ids)])
            rows = cursor.fetchall()

        job_id_to_failure_reason_mapping = {row[0]: FAILURE_REASONS[row[1]] for row in rows}

        if dry_run:
            click.echo(f"Would update {len(job_id_to_failure_reason_mapping.keys())} jobs")
            continue

        click.echo(f"Updating {len(job_id_to_failure_reason_mapping.keys())} jobs")
        jobs_to_update = list(
            JobDataDimension.objects.filter(job_id__in=job_id_to_failure_reason_mapping.keys())
        )
        for job in jobs_to_update:
            job.gitlab_failure_reason = job_id_to_failure_reason_mapping[job.job_id]

        JobDataDimension.objects.bulk_update(jobs_to_update, ["gitlab_failure_reason"])


@click.command()
@click.option("--dry-run", is_flag=True, default=False)
def migrate_exit_code_and_failure_reasons(dry_run: bool) -> None:
    click.echo("Migrating job exit codes")
    _migrate_exit_codes(dry_run)
    click.echo("Done")

    click.echo("Migrating job failure reasons")
    _migrate_failure_reasons(dry_run)
    click.echo("Done")
