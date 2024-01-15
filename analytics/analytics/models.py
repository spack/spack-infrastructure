from django.contrib.postgres.fields import ArrayField
from django.db import models


class NodeCapacityType(models.TextChoices):
    SPOT = "spot"
    ON_DEMAND = "on-demand"


class Node(models.Model):
    name = models.CharField(max_length=64, null=True, default=None)
    system_uuid = models.UUIDField(null=True, default=None)
    cpu = models.PositiveIntegerField(null=True, default=None)
    memory = models.PositiveIntegerField(null=True, default=None)
    capacity_type = models.CharField(
        max_length=12, choices=NodeCapacityType.choices, null=True, default=None
    )
    instance_type = models.CharField(max_length=32, null=True, default=None)
    instance_type_spot_price = models.FloatField(
        null=True,
        default=None,
        help_text=(
            "The price per hour (in USD) of the spot instnce this job ran on, at the time of"
            " running. If ever the job runs on an on-demand node, this field will be null."
        ),
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                name="unique-name-system-uuid", fields=["name", "system_uuid"]
            ),
        ]


class JobPod(models.Model):
    """Information about the kubernetes pod that a job ran on."""

    name = models.CharField(max_length=128)

    # Equivalent to the amount of a node this job had available to it, with respect to other jobs
    # on that node, over its lifetime. If a job was alone on a node for its entire lifetime, it
    # would have a value of 1. If it ran with 5 other jobs for its entire lifetime, it would have
    # a value of 0.2
    node_occupancy = models.FloatField()

    # Resource usage
    cpu_usage_seconds = models.FloatField()
    max_mem = models.PositiveBigIntegerField()
    avg_mem = models.PositiveBigIntegerField()

    # Technically limits and requests can be missing, so these are nullable
    cpu_request = models.FloatField(null=True, default=None)
    cpu_limit = models.FloatField(null=True, default=None)
    memory_request = models.PositiveBigIntegerField(null=True, default=None)
    memory_limit = models.PositiveBigIntegerField(null=True, default=None)


class Job(models.Model):
    # Core job fields
    job_id = models.PositiveBigIntegerField(primary_key=True)
    project_id = models.PositiveBigIntegerField()
    name = models.CharField(max_length=128)
    started_at = models.DateTimeField()
    duration = models.DurationField()
    ref = models.CharField(max_length=256)
    tags = ArrayField(base_field=models.CharField(max_length=32), default=list)
    package_name = models.CharField(max_length=128)

    # Whether this job ran in the cluster or not
    aws = models.BooleanField(default=True)

    # Node and pod will be null for non-aws jobs
    node = models.ForeignKey(
        Node, related_name="jobs", on_delete=models.PROTECT, null=True
    )
    pod = models.OneToOneField(JobPod, on_delete=models.PROTECT, null=True)

    # Extra data fields (null allowed to accomodate historical data)
    package_version = models.CharField(max_length=128, null=True)
    compiler_name = models.CharField(max_length=128, null=True)
    compiler_version = models.CharField(max_length=128, null=True)
    arch = models.CharField(max_length=128, null=True)
    package_variants = models.TextField(null=True)
    build_jobs = models.CharField(max_length=128, null=True)
    job_size = models.CharField(max_length=128, null=True)
    stack = models.CharField(max_length=128, null=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                name="non-empty-package-name", check=~models.Q(package_name="")
            ),
            # If a job ran in aws, it must have a node, otherwise it can't
            models.CheckConstraint(
                name="aws-node-presence",
                check=(
                    models.Q(aws=False, node__isnull=True)
                    | models.Q(aws=True, node__isnull=False)
                ),
            ),
            # If a job ran in aws, it must have a pod, otherwise it can't
            models.CheckConstraint(
                name="aws-pod-presence",
                check=(
                    models.Q(aws=False, pod__isnull=True)
                    | models.Q(aws=True, pod__isnull=False)
                ),
            ),
        ]


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


class ErrorTaxonomy(models.Model):
    job_id = models.PositiveBigIntegerField(primary_key=True)

    created = models.DateTimeField(auto_now_add=True)

    attempt_number = models.PositiveSmallIntegerField()
    retried = models.BooleanField()

    error_taxonomy = models.CharField(max_length=64)
    error_taxonomy_version = models.CharField(max_length=32)

    webhook_payload = models.JSONField(
        help_text="The JSON payload received from the GitLab job webhook."
    )
