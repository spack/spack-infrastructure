import datetime

from dateutil.parser import isoparse
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.db.models import Q
from django.db.models.functions import Length


class DateDimension(models.Model):
    date_key = models.CharField(
        max_length=8,
        primary_key=True,
        db_comment="The date this row represents formatted as <YYYY><MM><DD>",
    )
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

    @staticmethod
    def date_key_from_datetime(d: datetime.datetime | datetime.date | str):
        if isinstance(d, str):
            d = isoparse(d)

        return d.strftime("%Y%m%d")

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
    time_key = models.CharField(
        primary_key=True,
        max_length=6,
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
                condition=(models.Q(am_or_pm="AM") | models.Q(am_or_pm="PM")),
            ),
            models.CheckConstraint(
                # Max value is the last minute and second of the day,
                name="time-key-value",
                condition=models.Q(time_key__range=(0, 23_59_59)),
            ),
        ]

    @staticmethod
    def time_key_from_datetime(t: datetime.datetime | datetime.time | str):
        if isinstance(t, str):
            t = isoparse(t)

        return t.strftime("%H%M%S")

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


class JobType(models.TextChoices):
    BUILD = "build", "Build"
    DOTENV = "dotenv", "Dotenv"
    GENERATE = "generate", "Generate"
    NO_SPECS = "no-specs-to-rebuild", "No Specs to Rebuild"
    REBUILD_INDEX = "rebuild-index", "Rebuild Index"
    COPY = "copy", "Copy"
    UNSUPPORTED_COPY = "unsupported-copy", "Unsupported Copy"
    SIGN_PKGS = "sign-pkgs", "Sign Packages"
    PROTECTED_PUBLISH = "protected-publish", "Protected Publish"


class SpackJobDataDimension(models.Model):
    stack = models.CharField(max_length=128)
    job_size = models.CharField(max_length=128)
    job_type = models.CharField(
        max_length=max(len(c) for c, _ in JobType.choices), choices=JobType.choices
    )

    @classmethod
    def get_empty_row(cls):
        return cls.objects.get(job_size="", stack="", job_type="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                name="unique-spack-job-data",
                fields=[
                    "stack",
                    "job_size",
                    "job_type"
                ],
            ),
        ]


class GitlabJobDataDimension(models.Model):
    gitlab_runner_version = models.CharField(max_length=16)
    ref = models.CharField(max_length=256)
    tags = ArrayField(base_field=models.CharField(max_length=32), default=list)
    pipeline_id = models.PositiveBigIntegerField(null=True)
    parent_pipeline_id = models.PositiveBigIntegerField(null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                name="unique-gitlab-job-data",
                fields=[
                    "gitlab_runner_version",
                    "ref",
                    "tags",
                    "pipeline_id",
                    "parent_pipeline_id",
                ],
            ),
        ]


class JobResultDimension(models.Model):
    class Meta:
        constraints = [
            models.CheckConstraint(
                name="error-taxonomy-only-on-failed-status",
                condition=models.Q(status="failed")
                | models.Q(error_taxonomy__isnull=True),
            ),
        ]

    status = models.CharField(max_length=32)
    error_taxonomy = models.CharField(max_length=64, null=True)
    unnecessary = models.BooleanField(
        default=False,
        db_comment="Whether this job has 'No need to rebuild' in its trace.",
    )  # type: ignore

    # This field is duplicated here (from the gitlab job data dimension)
    # to allow for the generated `infrastructure_error` field
    job_type = models.CharField(
        max_length=max(len(c) for c, _ in JobType.choices), choices=JobType.choices
    )
    infrastructure_error = models.GeneratedField(
        output_field=models.BooleanField(),
        db_persist=True,
        expression=Q(
            Q(status="failed")
            & ~Q(
                error_taxonomy__in=[
                    "spack_error",
                    "build_error",
                    "concretization_error",
                    "module_not_found",
                ]
            )
            & ~Q(
                # This is a special case for the rebuild-index job type.
                # If a reindex job fails to get specs, it's not an infrastructure error,
                # but only if both those conditions are met.
                job_type=JobType.REBUILD_INDEX,
                error_taxonomy="failed_to_get_specs",
            ),
        ),
        help_text='Whether or not this job is an "infrastructure error", or a legitimate CI failure.',
    )
    gitlab_failure_reason = models.CharField(
        max_length=256,
        help_text="The failure reason reported by GitLab",
    )
    job_exit_code = models.IntegerField(
        help_text="The exit code of the job reported by GitLab",
        null=True,
        # TODO: we should add a constraint here to ensure this is non-null when gitlab_failure_reason
        # is 'script-error'. We'll leave it nullable for now until we can confirm that that
        # constraint is valid.
    )


class JobRetryDimension(models.Model):
    is_retry = models.BooleanField()
    is_manual_retry = models.BooleanField()
    attempt_number = models.PositiveSmallIntegerField()
    final_attempt = models.BooleanField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                name="unique-retry-pairing",
                fields=[
                    "is_retry",
                    "is_manual_retry",
                    "attempt_number",
                    "final_attempt",
                ],
            ),
        ]


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
                # Must have at least name, hash, and version, or all table rows must be empty (for the 'empty' row).
                # We only require name, hash, and version because we allow for partial creation of
                # the package spec if neccesary, to be later completed by another job.
                name="no-missing-fields",
                condition=(
                    models.Q(
                        name__length__gt=0,
                        hash__length=32,
                        version__length__gt=0,
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
                condition=(
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
