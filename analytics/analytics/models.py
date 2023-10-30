from django.contrib.postgres.fields import ArrayField
from django.db import models


class Job(models.Model):
    # Core job fields
    job_id = models.PositiveBigIntegerField(primary_key=True)
    project_id = models.PositiveBigIntegerField()
    name = models.CharField(max_length=128)
    started_at = models.DateTimeField()
    duration = models.FloatField()
    ref = models.CharField(max_length=256)
    tags = ArrayField(base_field=models.CharField(max_length=32), default=list)
    package_name = models.CharField(max_length=128)

    # Fields allow null to accomodate historical data
    package_version = models.CharField(max_length=128, null=True)
    compiler_name = models.CharField(max_length=128, null=True)
    compiler_version = models.CharField(max_length=128, null=True)
    arch = models.CharField(max_length=128, null=True)
    package_variants = models.TextField(null=True)
    build_jobs = models.CharField(max_length=128, null=True)
    job_size = models.CharField(max_length=128, null=True)
    stack = models.CharField(max_length=128, null=True)
    aws = models.BooleanField(default=True)


class Timer(models.Model):
    job = models.ForeignKey(Job, related_name="timers", on_delete=models.CASCADE)
    name = models.CharField(max_length=256)
    time_total = models.FloatField()
    hash = models.CharField(max_length=128, null=True)
    cache = models.BooleanField(null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                name="unique-hash-name-job", fields=["hash", "name", "job"]
            ),
            # Ensure that if a timer name starts with a "." (internal timer), that cache and hash
            # are null, and that otherwise they are present
            models.CheckConstraint(
                name="internal-timer-consistent-hash-and-cache",
                check=(
                    models.Q(
                        name__startswith=".", hash__isnull=True, cache__isnull=True
                    )
                    | (
                        ~models.Q(name__startswith=".")
                        & models.Q(hash__isnull=False, cache__isnull=False)
                    )
                ),
            ),
        ]


class TimerPhase(models.Model):
    timer = models.ForeignKey(Timer, related_name="phases", on_delete=models.CASCADE)
    name = models.CharField(max_length=128)
    is_subphase = models.BooleanField(default=False)
    path = models.CharField(max_length=128)
    seconds = models.FloatField()
    count = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["path", "timer"], name="unique-phase-path"),
        ]
