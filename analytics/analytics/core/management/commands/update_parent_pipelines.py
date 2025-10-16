import logging
from itertools import batched
from django.db import connections
from django.core.management.base import BaseCommand
from analytics.core.models import GitlabJobDataDimension
from django.db.models import F
from tqdm import tqdm

QUERY_BATCH_SIZE = 5_000
UPDATE_BATCH_SIZE = 100

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    def handle(self, *args, **options):
        # Get all the unique pipeline IDs
        pipeline_id_query = (
            GitlabJobDataDimension.objects.filter(
                parent_pipeline_id__isnull=True, pipeline_id__isnull=False
            )
            .distinct("pipeline_id")
            .values_list("pipeline_id", flat=True)
        )

        row_count = pipeline_id_query.count()
        if not row_count:
            logger.info("Nothing to do...")
            return
        logger.info("Rows to process: %s", row_count)

        # Process in batches to avoid loading too much into memory at once
        for pipeline_ids in batched(
            tqdm(
                pipeline_id_query.iterator(chunk_size=QUERY_BATCH_SIZE), total=row_count
            ),
            QUERY_BATCH_SIZE,
        ):
            with connections["gitlab"].cursor() as cursor:
                query = """
                    SELECT
                        pipeline_id,
                        source_pipeline_id
                    FROM public.ci_sources_pipelines
                    WHERE
                        pipeline_id IN %s
                        AND source_pipeline_id IS NOT NULL
                """
                cursor.execute(query, [tuple(pipeline_ids)])
                pipeline_id_to_source_pipeline_id = {
                    row[0]: row[1] for row in cursor.fetchall()
                }

            if not pipeline_id_to_source_pipeline_id:
                continue

            # Get all objects that will have `parent_pipeline_id` updated. The result of this query is
            # almost always larger than the batch size, since pipeline IDs are not unique in this table.
            objects_to_update = GitlabJobDataDimension.objects.filter(
                pipeline_id__in=pipeline_id_to_source_pipeline_id.keys()
            )
            for obj in objects_to_update:
                obj.parent_pipeline_id = pipeline_id_to_source_pipeline_id.get(obj.pipeline_id)

            # Django creates a CASE statement and Postgres chooses not to use the
            # primary key index if there are too many conditions.  We use a smaller
            # batch size to work around this.
            GitlabJobDataDimension.objects.bulk_update(
                objects_to_update,
                ["parent_pipeline_id"],
                batch_size=UPDATE_BATCH_SIZE
            )

        # Set the parent_pipeline_id for all pipelines without a parent.
        # This update happens entirely on the DB side, so no need to update in batches.
        GitlabJobDataDimension.objects.filter(
            parent_pipeline_id__isnull=True, pipeline_id__isnull=False
        ).update(parent_pipeline_id=F('pipeline_id'))
