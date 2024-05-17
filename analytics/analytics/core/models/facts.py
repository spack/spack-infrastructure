from django.db import models

from analytics.core.models.dimensions import (
    DateDimension,
    JobDataDimension,
    NodeDimension,
    PackageDimension,
    PackageHashDimension,
    RunnerDimension,
    TimeDimension,
    TimerDataDimension,
    TimerPhaseDimension,
)


class JobFact(models.Model):
    # Foreign Keys
    start_date = models.ForeignKey(
        DateDimension, related_name="+", on_delete=models.PROTECT
    )
    start_time = models.ForeignKey(
        TimeDimension, related_name="+", on_delete=models.PROTECT
    )

    end_date = models.ForeignKey(
        DateDimension, related_name="+", on_delete=models.PROTECT
    )
    end_time = models.ForeignKey(
        TimeDimension, related_name="+", on_delete=models.PROTECT
    )

    node = models.ForeignKey(NodeDimension, on_delete=models.PROTECT)
    runner = models.ForeignKey(RunnerDimension, on_delete=models.PROTECT)
    package = models.ForeignKey(PackageDimension, on_delete=models.PROTECT)
    job = models.ForeignKey(JobDataDimension, on_delete=models.PROTECT)

    # ############
    # Numeric Data
    # ############

    duration = models.DurationField()
    duration_seconds = models.FloatField(
        help_text="The duration of this job represented as seconds"
    )

    # Pod and node info (null if not run in cluster)
    pod_node_occupancy = models.FloatField(null=True, default=None)
    pod_cpu_usage_seconds = models.FloatField(null=True, default=None)
    pod_max_mem = models.PositiveBigIntegerField(null=True, default=None)
    pod_avg_mem = models.PositiveBigIntegerField(null=True, default=None)
    node_price_per_second = models.DecimalField(
        max_digits=9,
        decimal_places=8,
        help_text="The price per second (in USD) of the spot instance this job ran on, at the time of running.",
        null=True,
        default=None,
    )
    node_cpu = models.PositiveIntegerField(null=True, default=None)
    node_memory = models.PositiveBigIntegerField(null=True, default=None)

    # These fields can be null even if we have pod and node info
    build_jobs = models.PositiveSmallIntegerField(null=True, default=None)
    pod_cpu_request = models.FloatField(null=True, default=None)
    pod_cpu_limit = models.FloatField(null=True, default=None)
    pod_memory_request = models.PositiveBigIntegerField(null=True, default=None)
    pod_memory_limit = models.PositiveBigIntegerField(null=True, default=None)

    # Derived Fields
    cost = models.DecimalField(
        max_digits=13,
        decimal_places=10,
        help_text="The cost of this job, determined by the node occupancy, duration, and node price.",
        null=True,
        default=None,
    )

    class Meta:
        # All FKs should make up the composite primary key
        unique_together = [
            "start_date",
            "start_time",
            "end_date",
            "end_time",
            "node",
            "runner",
            "package",
            "job",
        ]

        # Ensure that these nullable fields are consistent
        constraints = [
            models.CheckConstraint(
                name="nullable-field-consistency",
                check=(
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
            # models.CheckConstraint(
            #     name="duration-consistency",
            #     check=(
            #         models.Q(
            #             duration_seconds=models.functions.Extract(
            #                 models.F("duration"),
            #                 "epoch",
            #                 output_field=models.FloatField(),
            #             )
            #         )
            #     ),
            # ),
        ]


class TimerFact(models.Model):
    job = models.ForeignKey(JobDataDimension, on_delete=models.PROTECT)
    timer_data = models.ForeignKey(TimerDataDimension, on_delete=models.PROTECT)
    package = models.ForeignKey(PackageDimension, on_delete=models.PROTECT)
    package_hash = models.ForeignKey(PackageHashDimension, on_delete=models.PROTECT)

    total_time = models.FloatField()

    class Meta:
        # All FKs should make up the composite primary key
        unique_together = ["job", "timer_data", "package", "package_hash"]


class TimerPhaseFact(models.Model):
    job = models.ForeignKey(JobDataDimension, on_delete=models.PROTECT)
    timer_data = models.ForeignKey(TimerDataDimension, on_delete=models.PROTECT)
    phase = models.ForeignKey(TimerPhaseDimension, on_delete=models.PROTECT)
    package = models.ForeignKey(PackageDimension, on_delete=models.PROTECT)
    package_hash = models.ForeignKey(PackageHashDimension, on_delete=models.PROTECT)

    time = models.FloatField()
    ratio_of_total = models.FloatField(
        help_text="The fraction of the timer total that this phase contributes to."
    )

    class Meta:
        # All FKs should make up the composite primary key
        unique_together = ["job", "timer_data", "phase", "package", "package_hash"]
