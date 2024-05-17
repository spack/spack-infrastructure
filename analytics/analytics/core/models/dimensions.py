from django.contrib.postgres.fields import ArrayField
from django.db import models


class DateDimension(models.Model):
    date_key = models.PositiveIntegerField(primary_key=True)
    date = models.DateField(unique=True)
    date_description = models.CharField(max_length=32)

    day_of_week = models.PositiveSmallIntegerField()
    day_of_month = models.PositiveSmallIntegerField()
    day_of_year = models.PositiveSmallIntegerField()
    day_name = models.CharField(max_length=16)
    weekday = models.BooleanField()

    month = models.PositiveSmallIntegerField()
    month_name = models.CharField(max_length=16)

    quarter = models.PositiveSmallIntegerField()
    year = models.PositiveSmallIntegerField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                name="date-key-value", check=models.Q(date_key__lt=2044_01_01)
            ),
        ]


class TimeDimension(models.Model):
    time_key = models.PositiveIntegerField(
        primary_key=True,
        help_text="The time this row represents formatted as <HOUR><MINUTE><SECOND>",
    )
    time = models.TimeField(
        unique=True,
        help_text="The time represented as a DB time field, with precision to the second.",
    )
    am_or_pm = models.CharField(max_length=2)

    hour_12 = models.PositiveSmallIntegerField()
    hour_24 = models.PositiveSmallIntegerField()

    minute = models.PositiveSmallIntegerField()
    minute_of_day = models.PositiveSmallIntegerField()

    second = models.PositiveSmallIntegerField()
    second_of_hour = models.PositiveSmallIntegerField()
    second_of_day = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                name="am-or-pm-value",
                check=(models.Q(am_or_pm="AM") | models.Q(am_or_pm="PM")),
            ),
            models.CheckConstraint(
                # Max value is the last minute and second of the day,
                name="time-key-value",
                check=models.Q(time_key__range=(0, 23_59_59)),
            ),
        ]


class JobDataDimension(models.Model):
    class Meta:
        constraints = [
            models.CheckConstraint(
                name="error-taxonomy-only-on-failed-status",
                check=models.Q(status="failed") | models.Q(error_taxonomy__isnull=True),
            ),
        ]

    job_id = models.PositiveBigIntegerField(primary_key=True)
    commit_id = models.PositiveBigIntegerField(null=True)
    job_url = models.URLField()
    name = models.CharField(max_length=128)
    ref = models.CharField(max_length=256)
    tags = ArrayField(base_field=models.CharField(max_length=32), default=list)
    job_size = models.CharField(max_length=128, null=True)
    stack = models.CharField(max_length=128, null=True)

    is_retry = models.BooleanField()
    is_manual_retry = models.BooleanField()
    attempt_number = models.PositiveSmallIntegerField()
    final_attempt = models.BooleanField()

    status = models.CharField(max_length=32)
    error_taxonomy = models.CharField(max_length=64, null=True)
    unnecessary = models.BooleanField(
        default=False,
        help_text="Whether this job has 'No need to rebuild' in its trace.",
    )

    pod_name = models.CharField(max_length=128, null=True, blank=True)
    gitlab_runner_version = models.CharField(max_length=16)
    is_build = models.BooleanField()


class NodeCapacityType(models.TextChoices):
    SPOT = "spot"
    ON_DEMAND = "on-demand"


class NodeDimension(models.Model):
    system_uuid = models.UUIDField(primary_key=True)
    name = models.CharField(max_length=64)
    cpu = models.PositiveIntegerField()
    memory = models.PositiveBigIntegerField()
    capacity_type = models.CharField(max_length=12, choices=NodeCapacityType.choices)
    instance_type = models.CharField(max_length=32)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                name="node-unique-name-system-uuid", fields=["name", "system_uuid"]
            ),
        ]


class RunnerDimension(models.Model):
    runner_id = models.PositiveIntegerField(primary_key=True)
    name = models.CharField(max_length=64, unique=True)
    platform = models.CharField(max_length=64)
    host = models.CharField(max_length=64)
    metal = models.BooleanField()
    in_cluster = models.BooleanField()


class PackageDimension(models.Model):
    name = models.CharField(max_length=128)
    version = models.CharField(max_length=32, blank=True)
    compiler_name = models.CharField(max_length=32, blank=True)
    compiler_version = models.CharField(max_length=32, blank=True)
    arch = models.CharField(max_length=64, blank=True)
    variants = models.TextField(default="", blank=True)

    class Meta:
        unique_together = [
            "name",
            "version",
            "compiler_name",
            "compiler_version",
            "arch",
            "variants",
        ]

        constraints = [
            models.CheckConstraint(name="no-empty-name", check=~models.Q(name=""))
        ]


class PackageHashDimension(models.Model):
    hash = models.CharField(max_length=32, unique=True)


class TimerPhaseDimension(models.Model):
    path = models.CharField(max_length=64, unique=True)
    is_subphase = models.BooleanField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                name="consistent-subphase-path",
                check=(
                    models.Q(is_subphase=True, path__contains="/")
                    | (models.Q(is_subphase=False) & ~models.Q(path__contains="/"))
                ),
            )
        ]


class TimerDataDimension(models.Model):
    cache = models.BooleanField()

    class Meta:
        unique_together = [
            "cache",
        ]
