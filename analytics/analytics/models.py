from django.contrib.postgres.fields import ArrayField
from django.db import models


class NodeCapacityType(models.TextChoices):
    SPOT = "spot"
    ON_DEMAND = "on-demand"


class Job(models.Model):
    # Core job fields
    job_id = models.PositiveBigIntegerField(primary_key=True)
    project_id = models.PositiveBigIntegerField()
    name = models.CharField(max_length=128)
    started_at = models.DateTimeField()
    duration = models.FloatField(null=True)
    ref = models.CharField(max_length=256)
    tags = ArrayField(base_field=models.CharField(max_length=32), default=list)
    package_name = models.CharField(max_length=128)

    # Whether this job ran in the cluster or not
    aws = models.BooleanField(default=True)

    # Kubernetes specific data (will be null for non-aws jobs)
    job_cpu_request = models.FloatField(null=True, default=None)
    job_memory_request = models.PositiveBigIntegerField(null=True, default=None)
    node_name = models.CharField(max_length=64, null=True, default=None)
    node_uid = models.UUIDField(null=True, default=None)
    node_cpu = models.PositiveIntegerField(null=True, default=None)
    node_mem = models.PositiveIntegerField(null=True, default=None)
    node_capacity_type = models.CharField(
        max_length=12, choices=NodeCapacityType.choices, null=True, default=None
    )
    node_instance_type = models.CharField(max_length=32, null=True, default=None)
    node_instance_type_spot_price = models.FloatField(
        null=True,
        default=None,
        help_text=(
            "The price per hour (in USD) of the spot instnce this job ran on, at the time of"
            " running. If ever the job runs on an on-demand node, this field will be null."
        ),
    )

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
            # Ensure that if the aws field is null, all aws data is also null
            models.CheckConstraint(
                name="aws-consistent-null-data",
                check=(
                    models.Q(
                        aws__isnull=True,
                        job_cpu_request__isnull=True,
                        job_memory_request__isnull=True,
                        node_name__isnull=True,
                        node_uid__isnull=True,
                        node_cpu__isnull=True,
                        node_mem__isnull=True,
                        node_capacity_type__isnull=True,
                        node_instance_type__isnull=True,
                        node_instance_type_spot_price__isnull=True,
                    )
                    | models.Q(
                        aws__isnull=False,
                        job_cpu_request__isnull=False,
                        job_memory_request__isnull=False,
                        node_name__isnull=False,
                        node_uid__isnull=False,
                        node_cpu__isnull=False,
                        node_mem__isnull=False,
                        node_capacity_type__isnull=False,
                        node_instance_type__isnull=False,
                        node_instance_type_spot_price__isnull=False,
                    )
                ),
            )
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
    created = models.DateTimeField(auto_now_add=True)
    job = models.OneToOneField(
        Job, related_name="error_taxonomy", on_delete=models.CASCADE
    )

    attempt_number = models.PositiveSmallIntegerField()
    retried = models.BooleanField()

    error_taxonomy = models.CharField(max_length=64)
    error_taxonomy_version = models.CharField(max_length=32)

    webhook_payload = models.JSONField(
        help_text="The JSON payload received from the GitLab job webhook."
    )
