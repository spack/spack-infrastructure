import datetime

from dateutil.parser import isoparse
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.db.models.functions import Length


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

    @staticmethod
    def date_key_from_datetime(d: datetime.datetime | datetime.date | str):
        if isinstance(d, str):
            d = isoparse(d)

        return int(d.strftime("%Y%m%d"))

    @classmethod
    def ensure_exists(cls, d: datetime.datetime | datetime.date | str):
        if isinstance(d, str):
            d = isoparse(d)

        date = d.date() if isinstance(d, datetime.datetime) else d
        date_key = cls.date_key_from_datetime(date)
        try:
            return cls.objects.get(date_key=date_key)
        except ObjectDoesNotExist:  # For some reason cls.DoesNotExist doesn't work here
            pass

        return cls.objects.create(
            date_key=date_key,
            date=date,
            date_description=date.strftime("%B %d, %Y"),
            day_of_week=date.weekday() + 1,
            day_of_month=date.day,
            day_of_year=int(date.strftime("%j")),
            day_name=date.strftime("%A"),
            weekday=date.weekday() not in [5, 6],
            month=date.month,
            month_name=date.strftime("%B"),
            quarter=(date.month - 1) // 3,
            year=date.year,
        )


class TimeDimension(models.Model):
    time_key = models.PositiveIntegerField(
        primary_key=True,
        db_comment="The time this row represents formatted as <HOUR><MINUTE><SECOND>",
    )  # type: ignore
    time = models.TimeField(
        unique=True,
        db_comment="The time represented as a DB time field, with precision to the second.",
    )  # type: ignore
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

    @staticmethod
    def time_key_from_datetime(t: datetime.datetime | datetime.time | str):
        if isinstance(t, str):
            t = isoparse(t)

        return int(t.strftime("%H%M%S"))

    @classmethod
    def ensure_exists(cls, d: datetime.datetime | datetime.time | str):
        if isinstance(d, str):
            d = isoparse(d)

        time = d.time() if isinstance(d, datetime.datetime) else d
        time_key = cls.time_key_from_datetime(time)
        try:
            return cls.objects.get(time_key=time_key)
        except ObjectDoesNotExist:  # For some reason cls.DoesNotExist doesn't work here
            pass

        return cls.objects.create(
            time_key=time_key,
            time=time,
            am_or_pm=time.strftime("%p"),
            hour_12=int(time.strftime("%I")),
            hour_24=time.hour,
            minute=time.minute,
            minute_of_day=time.hour * 60 + time.minute,
            second=time.second,
            second_of_hour=time.minute * 60 + time.second,
            second_of_day=time.hour * 3600 + time.minute * 60 + time.second,
        )


class JobDataDimension(models.Model):
    class JobType(models.TextChoices):
        BUILD = "build", "Build"
        GENERATE = "generate", "Generate"
        NO_SPECS = "no-specs-to-rebuild", "No Specs to Rebuild"
        REBUILD_INDEX = "rebuild-index", "Rebuild Index"
        COPY = "copy", "Copy"
        UNSUPPORTED_COPY = "unsupported-copy", "Unsupported Copy"
        SIGN_PKGS = "sign-pkgs", "Sign Packages"
        PROTECTED_PUBLISH = "protected-publish", "Protected Publish"

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
        db_comment="Whether this job has 'No need to rebuild' in its trace.",
    )  # type: ignore

    pod_name = models.CharField(max_length=128, null=True, blank=True)
    gitlab_runner_version = models.CharField(max_length=16)
    job_type = models.CharField(
        max_length=max(len(c) for c, _ in JobType.choices), choices=JobType.choices
    )
    gitlab_section_timers = models.JSONField(
        default=dict, db_comment="The GitLab CI section timers for this job."
    )  # type: ignore


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

    @classmethod
    def get_empty_row(cls):
        return cls.objects.get(name="")


class RunnerDimension(models.Model):
    runner_id = models.PositiveIntegerField(primary_key=True)
    name = models.CharField(max_length=64)
    platform = models.CharField(max_length=64)
    host = models.CharField(max_length=32)
    arch = models.CharField(max_length=32)
    tags = ArrayField(base_field=models.CharField(max_length=32), default=list)
    in_cluster = models.BooleanField()

    @classmethod
    def get_empty_row(cls):
        return cls.objects.get(name="")


# TODO: Split up variants into it's own dimension
# Query to get variants (without patches) from packages
# SELECT
#     DISTINCT(TRIM(UNNEST(regexp_matches(variants, '(~[^+~ ]+|\+[^+~ ]+|\s+(?!patches)[^+~ ]+=[^+~ ]+)', 'g'))))
#     AS variant
# FROM core_packagedimension


# Necessary for the length check constraints
models.CharField.register_lookup(Length)


class PackageSpecDimension(models.Model):
    """Represents a concrete spec."""

    # Hash is unique
    hash = models.CharField(max_length=32, unique=True)

    name = models.CharField(max_length=128)
    version = models.CharField(max_length=32)
    compiler_name = models.CharField(max_length=32)
    compiler_version = models.CharField(max_length=32)
    arch = models.CharField(max_length=64)
    variants = models.TextField(default="", blank=True)

    @classmethod
    def get_empty_row(cls):
        return cls.objects.get(hash="")

    class Meta:
        constraints = [
            models.CheckConstraint(
                # All fields must either have data, or must all be empty (for the 'empty' row)
                # Variants is the only one allowed to be empty
                name="no-missing-fields",
                check=(
                    models.Q(
                        name__length__gt=0,
                        hash__length=32,
                        version__length__gt=0,
                        compiler_name__length__gt=0,
                        compiler_version__length__gt=0,
                        arch__length__gt=0,
                    )
                    | models.Q(
                        name="",
                        hash="",
                        version="",
                        compiler_name="",
                        compiler_version="",
                        arch="",
                        variants="",
                    )
                ),
            ),
        ]


class PackageDimension(models.Model):
    """A loose representation of a package."""

    name = models.CharField(max_length=128, primary_key=True)

    @classmethod
    def get_empty_row(cls):
        return cls.objects.get(name="")


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
