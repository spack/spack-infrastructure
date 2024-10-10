import djclick as click
from django.db import connections
from datetime import datetime, timedelta
from pprint import pprint
from pathlib import Path

import requests
import json

# New query to fetch ci_builds IDs that finished within the specified date range
ID_FETCH_QUERY = """
SELECT ci_builds.id
FROM ci_builds
WHERE ci_builds.finished_at BETWEEN %s AND %s;
"""

WEBHOOK_QUERY = """
SELECT
'build' AS object_kind,
ci_builds.ref AS ref,
ci_builds.tag AS tag,
ci_builds.id AS build_id,
ci_builds.name AS build_name,
ci_builds.stage AS build_stage,
ci_builds.status AS build_status,
ci_builds.created_at AS build_created_at,
ci_builds.started_at AS build_started_at,
ci_builds.finished_at AS build_finished_at,
EXTRACT('epoch' FROM (ci_builds.finished_at - ci_builds.started_at)) AS build_duration,
EXTRACT('epoch' FROM (ci_builds.started_at - ci_builds.created_at)) AS build_queued_duration,
ci_builds.allow_failure AS build_allow_failure,
ci_builds.failure_reason AS build_failure_reason,
ci_pipelines.id AS pipeline_id,
json_build_object(
    'id', ci_builds.runner_id,
    'description', ci_runners.description,
    'runner_type', ci_runners.runner_type,
    'active', ci_runners.active,
    'is_shared', true, -- TODO
    'tags', tag_list.tags
) as runner,
projects.id AS project_id,
projects.name AS project_name,
json_build_object(
    'id', ci_builds.user_id,
    'name', users.name,
    'username', users.username,
    'avatar_url', users.avatar,
    'email', '[REDACTED]'
) as user,
json_build_object(
    'id', ci_pipelines.id,
    'name', null,
    'sha', ci_pipelines.sha,
    'message', '',
    'author_name', users.name,
    'author_email', '[REDACTED]',
    'author_url', CONCAT('mailto:', users.email),
    'status', ci_pipelines.status,
    'duration', ci_pipelines.duration,
    'started_at', ci_pipelines.started_at,
    'finished_at', ci_pipelines.finished_at
) as commit,
json_build_object(
    'name', 'spack',
    'url', 'git@ssh.gitlab.spack.io:spack/spack.git',
    'description', '',
    'homepage', 'https://gitlab.spack.io/spack/spack',
    'git_http_url', 'https://gitlab.spack.io/spack/spack.git',
    'git_ssh_url', 'git@ssh.gitlab.spack.io:spack/spack.git',
    'visibility_level', projects.visibility_level
) AS repository,
json_build_object(
    'id', projects.id,
    'name', projects.name,
    'description', projects.description,
    'web_url', 'https://gitlab.spack.io/spack/spack',
    'avatar_url', null,
    'git_ssh_url', 'git@ssh.gitlab.spack.io:spack/spack.git',
    'git_http_url', 'https://gitlab.spack.io/spack/spack.git',
    'namespace', 'spack',
    'visibility_level', projects.visibility_level,
    'path_with_namespace', CONCAT(projects.path, '/', projects.name),
    'default_branch', 'develop',
    'ci_config_path', projects.ci_config_path
) as project,
ci_builds.environment AS environment,
json_build_object() AS source_pipeline
FROM ci_builds
LEFT JOIN projects ON projects.id = ci_builds.project_id
LEFT JOIN ci_runners ON ci_runners.id = ci_builds.runner_id
LEFT JOIN users ON users.id = ci_builds.user_id
LEFT JOIN ci_pipelines ON ci_pipelines.id = ci_builds.commit_id
LEFT JOIN ci_refs ON ci_refs.id = ci_pipelines.ci_ref_id
LEFT JOIN (
    SELECT
      taggings.taggable_id AS runner_id,
      array_agg(DISTINCT tags.name) AS tags
    FROM taggings
    LEFT JOIN tags ON taggings.tag_id = tags.id
    GROUP BY taggings.taggable_id
) AS tag_list ON tag_list.runner_id = ci_builds.runner_id
WHERE ci_builds.id IN %s;
"""

WEBHOOK_URL = 'http://webhook-handler.custom.svc.cluster.local'
# STARTING_DATE = datetime(2024, 9, 18)
# ENDING_DATE = datetime(2024, 9, 22)
STARTING_DATE = datetime(2024, 9, 22)
ENDING_DATE = datetime(2024, 9, 26)
BATCH_SIZE = 10000  # Define the number of records to fetch in each iteration

webhook_payload_file = Path.cwd() / "webhook_payload.json"


def dict_fetchall(cursor):
    "Returns all rows from a cursor as a dict"
    desc = cursor.description
    return [
        dict(zip([col[0] for col in desc], row))
        for row in cursor.fetchall()
    ]

@click.command()
def backfill_jobs() -> None:
    # Step 1: Fetch the ci_builds IDs
    with connections["gitlab"].cursor() as cursor:
        cursor.execute(ID_FETCH_QUERY, [STARTING_DATE, ENDING_DATE])
        build_ids = [row[0] for row in cursor.fetchall()]  # Extract IDs from results

        click.echo(f"Fetched {len(build_ids)} build IDs.")

        offset = 0
        webhook_payload = []

        while True:
            # Prepare the IDs for the IN clause
            ids_chunk = build_ids[offset:offset + BATCH_SIZE]
            click.echo(f'Processing chunk {offset // BATCH_SIZE + 1} with {len(ids_chunk)} records.')

            if not ids_chunk:
                break  # Exit if no more IDs to process

            cursor.execute(WEBHOOK_QUERY, [tuple(ids_chunk)])  # Execute the join query
            results = dict_fetchall(cursor)

            if not results:
                break  # Exit the loop if no more results are returned

            # Process each result
            for result in results:
                # Sometimes the build_started_at field is None, so we set it to the created_at value
                if result.get('build_started_at') is None:
                    result['build_started_at'] = result['build_created_at']

                # Format the datetime fields into strings for the webhook payload
                for field in ['build_created_at', 'build_started_at', 'build_finished_at']:
                    result[field] = result[field].strftime('%Y-%m-%d %H:%M:%S ') + 'UTC'

                webhook_payload.append(result)  # Collect the results

            offset += BATCH_SIZE  # Increment the offset for the next batch

    click.echo(f"Total records processed: {len(webhook_payload)}")

    webhook_payload = json.loads(json.dumps(webhook_payload, default=str))

    # if not webhook_payload_file.exists():
    #     webhook_payload_file.write_text(json.dumps(webhook_payload, indent=4))

    for payload in webhook_payload:
        response = requests.post(
            WEBHOOK_URL,
            json=payload,
        )
        print(response.status_code)
        # print(response.text)
        # break

# touch analytics/core/management/commands/backfill.py
# rm analytics/core/management/commands/backfill.py && babi analytics/core/management/commands/backfill.py
