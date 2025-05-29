from concurrent.futures import Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import timedelta
import itertools
import re

from django.db import connections
import djclick as click

from analytics.core.models import JobFact
from analytics.job_processor.utils import get_gitlab_handle

# The URL of the webhook handler service specified in the GitLab project settings.
# This is the URL in the web_hook_logs table in the GitLab DB.
WEBHOOK_URL = "http://webhook-handler.custom.svc.cluster.local"


@dataclass
class WebhookEvent:
    created_at: str
    build_id: int
    project_id: int
    webhook_id: int
    webhook_event_id: int

    def __str__(self) -> str:
        return f"[{self.created_at}] build_id: {self.build_id}, project_id: {self.project_id}, webhook_id: {self.webhook_id}, webhook_event_id: {self.webhook_event_id}"


def retry_webhook(webhook_event: WebhookEvent, dry_run: bool) -> None:
    if dry_run:
        click.echo(f"Would retry webhook {webhook_event}")
        return

    click.echo(f"Retrying webhook {webhook_event}")
    gl = get_gitlab_handle()

    # https://docs.gitlab.com/ee/api/project_webhooks.html#resend-a-project-webhook-event
    retry_url = f"/projects/{webhook_event.project_id}/hooks/{webhook_event.webhook_id}/events/{webhook_event.webhook_event_id}/resend"
    gl.http_post(retry_url)


@click.command()
@click.option(
    "--seconds",
    type=int,
    default=timedelta(days=1).total_seconds(),
    help="Retry webhooks that failed in the last N seconds",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print the webhooks that would be retried without actually retrying them",
)
def retry_failed_job_webhooks(seconds: int, dry_run: bool) -> None:
    with connections["gitlab"].cursor() as cursor:
        cursor.execute("BEGIN;")

        cursor.execute(
            """
            DECLARE
                webhook_cursor
            CURSOR FOR
                SELECT
                    created_at,
                    request_data,
                    web_hook_id,
                    id
                FROM
                    public.web_hook_logs
                WHERE
                    url = %s AND
                    created_at > NOW() - INTERVAL %s;
        """,
            [WEBHOOK_URL, f"{seconds} seconds"],
        )

        futures: list[Future] = []

        with ThreadPoolExecutor() as executor:
            while True:
                # Fetch a batch of rows from the cursor
                cursor.execute("FETCH FORWARD %s FROM webhook_cursor", [5000])
                rows = cursor.fetchall()
                if not rows:
                    break

                webhook_events = [
                    WebhookEvent(
                        created_at=row[0],
                        build_id=int(re.search(r"build_id: (\d+)", row[1]).group(1)),
                        project_id=int(re.search(r"project_id: (\d+)", row[1]).group(1)),
                        webhook_id=row[2],
                        webhook_event_id=row[3],
                    )
                    for row in rows
                ]

                # We only want to retry webhooks for builds that have finished (i.e.
                # status is 'success' or 'failed'). Skipped or cancelled builds are
                # not stored in the analytics DB.
                cursor.execute(
                    """
                    SELECT
                        id
                    FROM
                        ci_builds
                    WHERE
                        id IN %s AND
                        status IN ('success', 'failed');
                """,
                    [tuple(event.build_id for event in webhook_events)],
                )
                finished_jobs: set[int] = set(itertools.chain.from_iterable(cursor.fetchall()))

                # Build a mapping of build ID to webhook event object for fast lookup by build ID
                build_id_to_webhook_mapping: dict[int, WebhookEvent] = {
                    event.build_id: event
                    for event in webhook_events
                    if event.build_id in finished_jobs
                }

                # Collect all build IDs
                build_ids: set[int] = set(build_id_to_webhook_mapping.keys())

                # Filter out build IDs that already have a corresponding analytics DB record
                existing_build_ids: set[int] = set(
                    JobFact.objects.filter(job_id__in=build_ids).values_list("job_id", flat=True)
                )

                # Calculate the missing build IDs
                missing_build_ids: set[int] = build_ids - existing_build_ids

                # Retry the webhooks for the missing build IDs
                for build_id in missing_build_ids:
                    futures.append(
                        executor.submit(
                            retry_webhook, build_id_to_webhook_mapping[build_id], dry_run
                        )
                    )

        cursor.execute("CLOSE webhook_cursor;")
        cursor.execute("COMMIT;")

        wait(futures)
