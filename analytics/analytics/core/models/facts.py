from django.db import models
from django.db.models import expressions
from django.db.models.fields.generated import GeneratedField

from analytics.core.models.dimensions import (
    DateDimension,
    GitlabJobDataDimension,
    JobResultDimension,
    JobRetryDimension,
    NodeDimension,
    PackageDimension,
    PackageSpecDimension,
    RunnerDimension,
    SpackJobDataDimension,
    TimeDimension,
    TimerDataDimension,
    TimerPhaseDimension,
)

started_at_sql = """
iso_timestamp(  -- Custom function implemented in the migration
    SUBSTR(start_date_id, 1, 4)
    || '-' ||
    SUBSTR(start_date_id, 5, 2)
    || '-' ||
    SUBSTR(start_date_id, 7, 2)
    || 'T' ||  -- Separation between date and time
    SUBSTR(start_time_id, 1, 2)
    || ':' ||
    SUBSTR(start_time_id, 3, 2)
    || ':' ||
    SUBSTR(start_time_id, 5, 2)
)
"""


class JobFact(models.Model):
    job_id = models.PositiveBigIntegerField(primary_key=True)

    # Foreign Keys
    start_date = models.ForeignKey(DateDimension, on_delete=models.PROTECT)
    start_time = models.ForeignKey(TimeDimension, on_delete=models.PROTECT)

    node = models.ForeignKey(NodeDimension, on_delete=models.PROTECT)
    runner = models.ForeignKey(RunnerDimension, on_delete=models.PROTECT)
    package = models.ForeignKey(PackageDimension, on_delete=models.PROTECT)
    spec = models.ForeignKey(PackageSpecDimension, on_delete=models.PROTECT)
    spack_job_data = models.ForeignKey(SpackJobDataDimension, on_delete=models.PROTECT)
    gitlab_job_data = models.ForeignKey(
        GitlabJobDataDimension, on_delete=models.PROTECT
    )
    job_result = models.ForeignKey(JobResultDimension, on_delete=models.PROTECT)
    job_retry = models.ForeignKey(JobRetryDimension, on_delete=models.PROTECT)

    # ######################
    # Small Descriptive Data
    # ######################
    job_url = models.URLField()
    name = models.CharField(max_length=128)
    pod_name = models.CharField(max_length=128)

    # Since metabase is very lacking when it comes to datetime and duration manipulation,
    # we need to create these generated fields here. This is generally not aligned with a
    # star schema approach, but we don't have much choice.
    started_at = GeneratedField(
        expression=expressions.RawSQL(
            sql=started_at_sql,
            params=[],
            output_field=models.DateTimeField(),
        ),
        output_field=models.DateTimeField(),
        null=False,
        db_persist=True,
        db_comment="Represented in UTC",
    )
    finished_at = GeneratedField(
        expression=expressions.RawSQL(
            sql=started_at_sql + " + duration",
            params=[],
            output_field=models.DateTimeField(),
        ),
        output_field=models.DateTimeField(),
        null=False,
        db_persist=True,
        db_comment="Represented in UTC",
    )

    # ############
    # Numeric Data
    # ############
    duration = models.DurationField()
    duration_seconds = models.FloatField(
        db_comment="The duration of this job represented as seconds"
    )  # type: ignore

    # Pod and node info (null if not run in cluster)
    pod_node_occupancy = models.FloatField(null=True, default=None)
    pod_cpu_usage_seconds = models.FloatField(null=True, default=None)
    pod_max_mem = models.PositiveBigIntegerField(null=True, default=None)
    pod_avg_mem = models.PositiveBigIntegerField(null=True, default=None)
    node_price_per_second = models.DecimalField(
        max_digits=9,
        decimal_places=8,
        db_comment="The price per second (in USD) of the spot instance this job ran on, at the time of running.",
        null=True,
        default=None,
    )  # type: ignore
    node_cpu = models.PositiveIntegerField(null=True, default=None)
    node_memory = models.PositiveBigIntegerField(null=True, default=None)

    # These fields can be null even if we have pod and node info
    build_jobs = models.PositiveSmallIntegerField(null=True, default=None)
    pod_cpu_request = models.FloatField(null=True, default=None)
    pod_cpu_limit = models.FloatField(null=True, default=None)
    pod_memory_request = models.PositiveBigIntegerField(null=True, default=None)
    pod_memory_limit = models.PositiveBigIntegerField(null=True, default=None)

    # Gitlab section timer data
    gitlab_clear_worktree = models.PositiveIntegerField(default=0)
    gitlab_after_script = models.PositiveIntegerField(default=0)
    gitlab_cleanup_file_variables = models.PositiveIntegerField(default=0)
    gitlab_download_artifacts = models.PositiveIntegerField(default=0)
    gitlab_get_sources = models.PositiveIntegerField(default=0)
    gitlab_prepare_executor = models.PositiveIntegerField(default=0)
    gitlab_prepare_script = models.PositiveIntegerField(default=0)
    gitlab_resolve_secrets = models.PositiveIntegerField(default=0)
    gitlab_step_script = models.PositiveIntegerField(default=0)
    gitlab_upload_artifacts_on_failure = models.PositiveIntegerField(default=0)
    gitlab_upload_artifacts_on_success = models.PositiveIntegerField(default=0)

    # Derived Fields
    cost = models.DecimalField(
        max_digits=13,
        decimal_places=10,
        db_comment="The cost of this job, determined by the node occupancy, duration, and node price.",
        null=True,
        default=None,
    )  # type: ignore

    class Meta:
        indexes = [
            models.Index(fields=["started_at"], name="core_jobfact_started_at"),
            models.Index(fields=["finished_at"], name="core_jobfact_finished_at"),
        ]
        constraints = [
            # Ensure that these nullable fields are consistent
            models.CheckConstraint(
                name="nullable-field-consistency",
                condition=(
                    models.Q(
                        pod_node_occupancy__isnull=True,
                        pod_cpu_usage_seconds__isnull=True,
                        pod_max_mem__isnull=True,
                        pod_avg_mem__isnull=True,
                        node_price_per_second__isnull=True,
                        node_cpu__isnull=True,
                        node_memory__isnull=True,
                    )
                    | models.Q(
                        pod_node_occupancy__isnull=False,
                        pod_cpu_usage_seconds__isnull=False,
                        pod_max_mem__isnull=False,
                        pod_avg_mem__isnull=False,
                        node_price_per_second__isnull=False,
                        node_cpu__isnull=False,
                        node_memory__isnull=False,
                    )
                ),
            ),
        ]


class TimerFact(models.Model):
    job_id = models.PositiveBigIntegerField()
    date = models.ForeignKey(DateDimension, on_delete=models.PROTECT)
    time = models.ForeignKey(TimeDimension, on_delete=models.PROTECT)
    timer_data = models.ForeignKey(TimerDataDimension, on_delete=models.PROTECT)
    package = models.ForeignKey(PackageDimension, on_delete=models.PROTECT)
    spec = models.ForeignKey(PackageSpecDimension, on_delete=models.PROTECT)

    total_duration = models.FloatField()

    class Meta:
        constraints = [
            # All FKs should make up the composite primary key
            models.UniqueConstraint(
                name="timer-fact-composite-key",
                fields=[
                    "job_id",
                    "date",
                    "time",
                    "timer_data",
                    "package",
                    "spec",
                ],
            )
        ]


class TimerPhaseFact(models.Model):
    job_id = models.PositiveBigIntegerField()
    date = models.ForeignKey(DateDimension, on_delete=models.PROTECT)
    time = models.ForeignKey(TimeDimension, on_delete=models.PROTECT)
    timer_data = models.ForeignKey(TimerDataDimension, on_delete=models.PROTECT)
    package = models.ForeignKey(PackageDimension, on_delete=models.PROTECT)
    spec = models.ForeignKey(PackageSpecDimension, on_delete=models.PROTECT)

    phase = models.ForeignKey(TimerPhaseDimension, on_delete=models.PROTECT)

    duration = models.FloatField()
    ratio_of_total = models.FloatField(
        db_comment="The fraction of the timer total that this phase contributes to."
    )  # type: ignore

    class Meta:
        constraints = [
            # All FKs should make up the composite primary key
            models.UniqueConstraint(
                name="timerphase-fact-composite-key",
                fields=[
                    "job_id",
                    "date",
                    "time",
                    "timer_data",
                    "package",
                    "spec",
                    "phase",
                ],
            )
        ]
