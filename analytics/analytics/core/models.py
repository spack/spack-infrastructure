from django.contrib.postgres.fields import ArrayField
from django.db import IntegrityError, models, transaction


class NodeCapacityType(models.TextChoices):
    SPOT = "spot"
    ON_DEMAND = "on-demand"


class Node(models.Model):
    name = models.CharField(max_length=64)
    system_uuid = models.UUIDField()
    cpu = models.PositiveIntegerField()
    memory = models.PositiveBigIntegerField()
    capacity_type = models.CharField(max_length=12, choices=NodeCapacityType.choices)
    instance_type = models.CharField(max_length=32)

    # Specify a decimal field with 3 digits left of the decimal, and 6 right of it
    instance_type_spot_price = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        help_text=(
            "The price per hour (in USD) of the spot instance this job ran on, at the time of running."
        ),
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(name="unique-name-system-uuid", fields=["name", "system_uuid"]),
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


class JobAttempt(models.Model):
    class Meta:
        constraints = [
            models.CheckConstraint(
                name="error-taxonomy-only-on-failed",
                check=models.Q(status="failed") | models.Q(error_taxonomy__isnull=True),
            ),
        ]

    job_id = models.PositiveBigIntegerField(primary_key=True)
    project_id = models.PositiveBigIntegerField()
    commit_id = models.PositiveBigIntegerField()
    name = models.CharField(max_length=128)
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField()
    ref = models.CharField(max_length=256)

    is_retry = models.BooleanField()
    is_manual_retry = models.BooleanField()
    attempt_number = models.PositiveSmallIntegerField()
    final_attempt = models.BooleanField()

    status = models.CharField(max_length=32)

    error_taxonomy = models.CharField(max_length=64, null=True)
    section_timers = models.JSONField(
        default=dict, null=True, help_text="The GitLab CI section timers for this job."
    )


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
    node = models.ForeignKey(Node, related_name="jobs", on_delete=models.PROTECT, null=True)
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

    unnecessary = models.BooleanField(
        default=False, help_text="Whether this job has 'No need to rebuild' in its trace."
    )

    @property
    def midpoint(self):
        """A datetime representing the midpoint (in time) of the job."""
        return self.started_at + (self.duration / 2)

    @property
    def finished_at(self):
        return self.started_at + self.duration

    def save_or_set_node(self):
        if self.node is None:
            return
        if self.node.pk is not None:
            return

        try:
            with transaction.atomic():
                self.node.save()
            return
        except IntegrityError as e:
            if "unique-name-system-uuid" not in str(e):
                raise

        # Node already exists, set node field to the existing node
        self.node = Node.objects.get(name=self.node.name, system_uuid=self.node.system_uuid)

    class Meta:
        indexes = [
            models.Index(fields=["started_at"]),
        ]
        constraints = [
            models.CheckConstraint(name="non-empty-package-name", check=~models.Q(package_name="")),
            # Ensure that either pod and node are both null or both not null
            models.CheckConstraint(
                name="node-pod-consistency",
                check=models.Q(node__isnull=True, pod__isnull=True)
                | models.Q(node__isnull=False, pod__isnull=False),
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
            models.UniqueConstraint(name="unique-hash-name-job", fields=["hash", "name", "job"]),
            # Ensure that if a timer name starts with a "." (internal timer), that cache and hash
            # are null, and that otherwise they are present
            models.CheckConstraint(
                name="internal-timer-consistent-hash-and-cache",
                check=(
                    models.Q(name__startswith=".", hash__isnull=True, cache__isnull=True)
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
