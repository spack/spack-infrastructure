import json
from datetime import datetime, timezone
from itertools import batched

import djclick as click
from django.db import connections
from tqdm import tqdm

from analytics.core.models.facts import JobFact
from analytics.job_processor import process_job

WEBHOOK_QUERY = """
SELECT
    'build' AS object_kind,
    p_ci_builds.ref AS ref,
    p_ci_builds.tag AS tag,
    -- TODO: before_sha, sha, retries_count
    p_ci_builds.id AS build_id,
    p_ci_builds.name AS build_name,
    p_ci_stages.name AS build_stage,
    p_ci_builds.status AS build_status,
    p_ci_builds.created_at AS build_created_at,
    p_ci_builds.started_at AS build_started_at,
    p_ci_builds.finished_at AS build_finished_at,
    CAST(
        EXTRACT(
            'epoch'
            FROM (p_ci_builds.finished_at - p_ci_builds.started_at)
        ) AS double precision
    ) AS build_duration,
    CAST(
        EXTRACT(
            'epoch'
            FROM (p_ci_builds.started_at - p_ci_builds.created_at)
        ) AS double precision
    ) AS build_queued_duration,
    p_ci_builds.allow_failure AS build_allow_failure,
    p_ci_builds.failure_reason AS build_failure_reason,
    p_ci_pipelines.id AS pipeline_id,
    json_build_object (
        'id',           p_ci_builds.runner_id,
        'description',  ci_runners.description,
        'runner_type',  ci_runners.runner_type,
        'active',       ci_runners.active,
        'is_shared',    CASE WHEN ci_runners.runner_type = 1 THEN true ELSE false END, -- Only "instance_type" runners are considered shared
        'tags',         tag_list.tags
    ) as runner,
    projects.id AS project_id,
    projects.name AS project_name,
    json_build_object (
        'id',           p_ci_builds.user_id,
        'name',         users.name,
        'username',     users.username,
        'avatar_url',   users.avatar,
        'email',        '[REDACTED]'
    ) as user,
    json_build_object (
        'id',               p_ci_pipelines.id,
        'name',             null,
        'sha',              p_ci_pipelines.sha,
        'message',          '',
        'author_name',      users.name,
        'author_email',     '[REDACTED]',
        'author_url',       CONCAT ('mailto:', users.email),
        'status',           p_ci_pipelines.status,
        'duration',         p_ci_pipelines.duration,
        'started_at',       p_ci_pipelines.started_at,
        'finished_at',      p_ci_pipelines.finished_at
    ) as commit,
    json_build_object (
        'name',             'spack-packages',
        'url',              'git@ssh.gitlab.spack.io:spack/spack-packages.git',
        'description',      '',
        'homepage',         'https://gitlab.spack.io/spack/spack-packages',
        'git_http_url',     'https://gitlab.spack.io/spack/spack-packages.git',
        'git_ssh_url',      'git@ssh.gitlab.spack.io:spack/spack-packages.git',
        'visibility_level', projects.visibility_level
    ) AS repository,
    json_build_object (
        'id',                   projects.id,
        'name',                 projects.name,
        'description',          projects.description,
        'web_url',              'https://gitlab.spack.io/spack/spack-packages',
        'avatar_url',           null,
        'git_ssh_url',          'git@ssh.gitlab.spack.io:spack/spack-packages.git',
        'git_http_url',         'https://gitlab.spack.io/spack/spack-packages.git',
        'namespace',            'spack',
        'visibility_level',     projects.visibility_level,
        'path_with_namespace',  'spack/spack-packages',
        'default_branch',       'develop',
        'ci_config_path',       projects.ci_config_path
    ) as project,
    p_ci_builds.environment AS environment,
    json_build_object (
        'project', json_build_object (
            'id',                   projects.id,
            'web_url',              'https://gitlab.spack.io/spack/spack-packages',
            'path_with_namespace',  'spack/spack-packages'
        ),
        'job_id',                   ci_sources_pipelines.source_job_id,
        'pipeline_id',              ci_sources_pipelines.source_pipeline_id
    ) AS source_pipeline
FROM
    p_ci_builds
    LEFT JOIN projects ON projects.id = p_ci_builds.project_id
    LEFT JOIN p_ci_stages ON p_ci_stages.id = p_ci_builds.stage_id
    LEFT JOIN ci_runners ON ci_runners.id = p_ci_builds.runner_id
    LEFT JOIN users ON users.id = p_ci_builds.user_id
    LEFT JOIN p_ci_pipelines ON p_ci_pipelines.id = p_ci_builds.commit_id
    LEFT JOIN ci_sources_pipelines ON ci_sources_pipelines.pipeline_id = p_ci_pipelines.id
    LEFT JOIN ci_refs ON ci_refs.id = p_ci_pipelines.ci_ref_id
    LEFT JOIN (
        SELECT
            ci_runner_taggings.runner_id,
            array_agg (DISTINCT tags.name) AS tags
        FROM
            ci_runner_taggings
            LEFT JOIN tags ON ci_runner_taggings.tag_id = tags.id
        GROUP BY
            ci_runner_taggings.runner_id
    ) AS tag_list ON tag_list.runner_id = p_ci_builds.runner_id
WHERE
    p_ci_builds.id IN %(job_ids)s
ORDER BY p_ci_builds.id
"""

# Query to fetch p_ci_builds IDs that finished within the specified date range
ID_FETCH_QUERY = """
    SELECT p_ci_builds.id
    FROM p_ci_builds
    LEFT JOIN projects ON projects.id = p_ci_builds.project_id
    WHERE
        projects.id = 57  -- The project ID for spack/spack_packages
        AND p_ci_builds.finished_at BETWEEN %(start)s AND %(end)s
        AND p_ci_builds.type = 'Ci::Build'
        AND status IN ('success', 'failed')
    ;
"""

# Taken from https://gitlab.com/gitlab-org/gitlab/-/blob/master/app/models/concerns/enums/ci/commit_status.rb
# It's possible this changes slightly in the future, but for our purposes, it probably won't.
FAILURE_REASON_MAP = {
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
    1_013: "duo_workflow_not_allowed",
}

# https://gitlab.com/gitlab-org/gitlab/-/blob/master/app/models/ci/runner.rb?ref_type=heads#L43-47
RUNNER_TYPE_MAP = {
    1: "instance_type",
    2: "group_type",
    3: "project_type",
}

# Define the number of records to fetch in each iteration
BATCH_SIZE = 10_000


def dict_fetchall(cursor):
    "Returns all rows from a cursor as a dict"
    desc = cursor.description
    return [dict(zip([col[0] for col in desc], row)) for row in cursor.fetchall()]


@click.command()
@click.option("--start", type=click.DateTime(), help="The datetime to start at")
@click.option(
    "--end",
    type=click.DateTime(),
    help="The datetime to end at (UTC). Defaults to now.",
    default=datetime.now(),
)
@click.option(
    "--dry-run", "dry_run", is_flag=True, help="Don't actually process the jobs"
)
def backfill_jobs(start: datetime, end: datetime, dry_run: bool) -> None:
    # Ensure in UTC timezone
    start = start.astimezone(timezone.utc)
    end = end.astimezone(timezone.utc)

    with connections["gitlab"].cursor() as cursor:
        click.echo(f"Querying for jobs between <{start}> and <{end}>...")

        # Fetch the p_ci_builds IDs
        cursor.execute(ID_FETCH_QUERY, {"start": start, "end": end})
        build_ids = [row[0] for row in cursor.fetchall()]

        # Cross reference these IDs with existing job facts, so that we don't process duplicate jobs
        # Use the `finished_at` field to match the ID query above
        existing_job_facts = set(
            JobFact.objects.filter(finished_at__range=(start, end)).values_list(
                "job_id", flat=True
            )
        )
        build_ids = [_id for _id in build_ids if _id not in existing_job_facts]
        build_ids.sort()

        click.echo(
            f"Found {len(build_ids)} unprocessed jobs between {start} and {end}."
        )

        pbar = tqdm(total=len(build_ids))
        for i, ids_chunk in enumerate(batched(build_ids, BATCH_SIZE)):
            pbar.set_description(
                f"Querying jobs {i * BATCH_SIZE} - {i * BATCH_SIZE + len(ids_chunk)}..."
            )

            # Make query that formulates the webhook shape using the relevant database tables
            cursor.execute(WEBHOOK_QUERY, {"job_ids": ids_chunk})
            results = dict_fetchall(cursor)

            pbar.set_description(
                f"Processing records {i * BATCH_SIZE} - {i * BATCH_SIZE + len(ids_chunk)}"
            )

            # Process each result
            for result in results:
                # If the "build_started_at" field is None, set it to the created_at value. This seems
                # to occurs when a job was queued for too long and marked as "failed", before it ever
                # actually started. This means that technically, we shouldn't overwrite this field in
                # this way, since we are misrepresenting the job info. However, at the moment, we rely
                # solely on the "started_at" field. Once this changes, this behavior can be removed.
                # https://github.com/spack/spack-infrastructure/issues/1284
                if result.get("build_started_at") is None:
                    result["build_started_at"] = result["build_created_at"]

                # The Gitlab DB returns a nullable integer, but the webhooks we
                # receive use a string from the enum.
                result["build_failure_reason"] = FAILURE_REASON_MAP[
                    result["build_failure_reason"]
                ]

                # Convert integer into string from enum. If the runner no longer exists,
                # the join will fail, and this value will be None
                if result["runner"]["runner_type"] is not None:
                    result["runner"]["runner_type"] = RUNNER_TYPE_MAP[
                        result["runner"]["runner_type"]
                    ]

                # Format the datetime fields into strings for the webhook payload
                for field in [
                    "build_created_at",
                    "build_started_at",
                    "build_finished_at",
                ]:
                    result[field] = result[field].strftime("%Y-%m-%d %H:%M:%S ") + "UTC"

            if dry_run:
                click.echo(
                    f"[Dry Run] Would process records {i * BATCH_SIZE} - {i * BATCH_SIZE + len(ids_chunk)}"
                )
                pbar.update(len(results))
                continue

            for webhook_dict in results:
                process_job(json.dumps(webhook_dict))
                pbar.update(1)

    click.echo(f"Total records processed: {len(build_ids)}")
