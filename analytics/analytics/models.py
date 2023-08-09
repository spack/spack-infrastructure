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

    # Derived fields
    package_name = models.CharField(max_length=128)
    aws = models.BooleanField(default=True)


class Timer(models.Model):
    job = models.ForeignKey(Job, related_name="timers", on_delete=models.CASCADE)
    name = models.CharField(max_length=256)
    time_total = models.FloatField()
    hash = models.CharField(max_length=128, null=True)
    cache = models.BooleanField(null=True)


class Phase(models.Model):
    timer = models.ForeignKey(Timer, related_name="phases", on_delete=models.CASCADE)
    name = models.CharField(max_length=128)
    path = models.CharField(max_length=128)
    seconds = models.FloatField()
    count = models.PositiveIntegerField()
