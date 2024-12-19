# Generated by Django 4.2.4 on 2024-05-31 17:32
# type: ignore

import django.contrib.postgres.fields
import django.db.models.deletion
from django.db import migrations, models


def remove_all_other_projects(apps, schema_editor):
    Job = apps.get_model("core", "Job")
    JobAttempt = apps.get_model("core", "JobAttempt")

    Job.objects.exclude(project_id=2).delete()
    JobAttempt.objects.exclude(project_id=2).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0013_job_core_job_started_b88deb_idx"),
    ]

    operations = [
        # migrations.RunPython(
        #     remove_all_other_projects, reverse_code=migrations.RunPython.noop
        # ),
        migrations.CreateModel(
            name="DateDimension",
            fields=[
                (
                    "date_key",
                    models.PositiveIntegerField(primary_key=True, serialize=False),
                ),
                ("date", models.DateField(unique=True)),
                ("date_description", models.CharField(max_length=32)),
                ("day_of_week", models.PositiveSmallIntegerField()),
                ("day_of_month", models.PositiveSmallIntegerField()),
                ("day_of_year", models.PositiveSmallIntegerField()),
                ("day_name", models.CharField(max_length=16)),
                ("weekday", models.BooleanField()),
                ("month", models.PositiveSmallIntegerField()),
                ("month_name", models.CharField(max_length=16)),
                ("quarter", models.PositiveSmallIntegerField()),
                ("year", models.PositiveSmallIntegerField()),
            ],
        ),
        migrations.CreateModel(
            name="JobDataDimension",
            fields=[
                (
                    "job_id",
                    models.PositiveBigIntegerField(primary_key=True, serialize=False),
                ),
                ("commit_id", models.PositiveBigIntegerField(null=True)),
                ("job_url", models.URLField()),
                ("name", models.CharField(max_length=128)),
                ("ref", models.CharField(max_length=256)),
                (
                    "tags",
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.CharField(max_length=32),
                        default=list,
                        size=None,
                    ),
                ),
                ("job_size", models.CharField(max_length=128, null=True)),
                ("stack", models.CharField(max_length=128, null=True)),
                ("is_retry", models.BooleanField()),
                ("is_manual_retry", models.BooleanField()),
                ("attempt_number", models.PositiveSmallIntegerField()),
                ("final_attempt", models.BooleanField()),
                ("status", models.CharField(max_length=32)),
                ("error_taxonomy", models.CharField(max_length=64, null=True)),
                (
                    "unnecessary",
                    models.BooleanField(
                        default=False,
                        db_comment="Whether this job has 'No need to rebuild' in its trace.",
                    ),
                ),
                ("pod_name", models.CharField(blank=True, max_length=128, null=True)),
                ("gitlab_runner_version", models.CharField(max_length=16)),
                ("is_build", models.BooleanField()),
            ],
        ),
        migrations.CreateModel(
            name="JobFact",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("duration", models.DurationField()),
                (
                    "duration_seconds",
                    models.FloatField(
                        db_comment="The duration of this job represented as seconds"
                    ),
                ),
                ("pod_node_occupancy", models.FloatField(default=None, null=True)),
                ("pod_cpu_usage_seconds", models.FloatField(default=None, null=True)),
                (
                    "pod_max_mem",
                    models.PositiveBigIntegerField(default=None, null=True),
                ),
                (
                    "pod_avg_mem",
                    models.PositiveBigIntegerField(default=None, null=True),
                ),
                (
                    "node_price_per_second",
                    models.DecimalField(
                        decimal_places=8,
                        default=None,
                        db_comment="The price per second (in USD) of the spot instance this job ran on, at the time of running.",
                        max_digits=9,
                        null=True,
                    ),
                ),
                ("node_cpu", models.PositiveIntegerField(default=None, null=True)),
                (
                    "node_memory",
                    models.PositiveBigIntegerField(default=None, null=True),
                ),
                (
                    "build_jobs",
                    models.PositiveSmallIntegerField(default=None, null=True),
                ),
                ("pod_cpu_request", models.FloatField(default=None, null=True)),
                ("pod_cpu_limit", models.FloatField(default=None, null=True)),
                (
                    "pod_memory_request",
                    models.PositiveBigIntegerField(default=None, null=True),
                ),
                (
                    "pod_memory_limit",
                    models.PositiveBigIntegerField(default=None, null=True),
                ),
                (
                    "cost",
                    models.DecimalField(
                        decimal_places=10,
                        default=None,
                        db_comment="The cost of this job, determined by the node occupancy, duration, and node price.",
                        max_digits=13,
                        null=True,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="NodeDimension",
            fields=[
                ("system_uuid", models.UUIDField(primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=64)),
                ("cpu", models.PositiveIntegerField()),
                ("memory", models.PositiveBigIntegerField()),
                (
                    "capacity_type",
                    models.CharField(
                        choices=[("spot", "Spot"), ("on-demand", "On Demand")],
                        max_length=12,
                    ),
                ),
                ("instance_type", models.CharField(max_length=32)),
            ],
        ),
        migrations.CreateModel(
            name="PackageDimension",
            fields=[
                (
                    "name",
                    models.CharField(max_length=128, primary_key=True, serialize=False),
                ),
            ],
        ),
        migrations.CreateModel(
            name="PackageSpecDimension",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=128)),
                ("hash", models.CharField(max_length=32, unique=True)),
                ("version", models.CharField(max_length=32)),
                ("compiler_name", models.CharField(max_length=32)),
                ("compiler_version", models.CharField(max_length=32)),
                ("arch", models.CharField(max_length=64)),
                ("variants", models.TextField(blank=True, default="")),
            ],
        ),
        migrations.CreateModel(
            name="RunnerDimension",
            fields=[
                (
                    "runner_id",
                    models.PositiveIntegerField(primary_key=True, serialize=False),
                ),
                ("name", models.CharField(max_length=64, unique=True)),
                ("platform", models.CharField(max_length=64)),
                ("host", models.CharField(max_length=32)),
                ("arch", models.CharField(max_length=32)),
                (
                    "tags",
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.CharField(max_length=32),
                        default=list,
                        size=None,
                    ),
                ),
                ("in_cluster", models.BooleanField()),
            ],
        ),
        migrations.CreateModel(
            name="TimeDimension",
            fields=[
                (
                    "time_key",
                    models.PositiveIntegerField(
                        db_comment="The time this row represents formatted as <HOUR><MINUTE><SECOND>",
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "time",
                    models.TimeField(
                        db_comment="The time represented as a DB time field, with precision to the second.",
                        unique=True,
                    ),
                ),
                ("am_or_pm", models.CharField(max_length=2)),
                ("hour_12", models.PositiveSmallIntegerField()),
                ("hour_24", models.PositiveSmallIntegerField()),
                ("minute", models.PositiveSmallIntegerField()),
                ("minute_of_day", models.PositiveSmallIntegerField()),
                ("second", models.PositiveSmallIntegerField()),
                ("second_of_hour", models.PositiveSmallIntegerField()),
                ("second_of_day", models.PositiveIntegerField()),
            ],
        ),
        migrations.AddConstraint(
            model_name="timedimension",
            constraint=models.CheckConstraint(
                check=models.Q(("am_or_pm", "AM"), ("am_or_pm", "PM"), _connector="OR"),
                name="am-or-pm-value",
            ),
        ),
        migrations.AddConstraint(
            model_name="timedimension",
            constraint=models.CheckConstraint(
                check=models.Q(("time_key__range", (0, 235959))), name="time-key-value"
            ),
        ),
        migrations.AddConstraint(
            model_name="packagespecdimension",
            constraint=models.CheckConstraint(
                check=models.Q(
                    models.Q(
                        ("arch__length__gt", 0),
                        ("compiler_name__length__gt", 0),
                        ("compiler_version__length__gt", 0),
                        ("hash__length", 32),
                        ("name__length__gt", 0),
                        ("version__length__gt", 0),
                    ),
                    models.Q(
                        ("arch", ""),
                        ("compiler_name", ""),
                        ("compiler_version", ""),
                        ("hash", ""),
                        ("name", ""),
                        ("variants", ""),
                        ("version", ""),
                    ),
                    _connector="OR",
                ),
                name="no-missing-fields",
            ),
        ),
        migrations.AddConstraint(
            model_name="nodedimension",
            constraint=models.UniqueConstraint(
                fields=("name", "system_uuid"), name="node-unique-name-system-uuid"
            ),
        ),
        migrations.AddField(
            model_name="jobfact",
            name="job",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT, to="core.jobdatadimension"
            ),
        ),
        migrations.AddField(
            model_name="jobfact",
            name="node",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT, to="core.nodedimension"
            ),
        ),
        migrations.AddField(
            model_name="jobfact",
            name="package",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT, to="core.packagedimension"
            ),
        ),
        migrations.AddField(
            model_name="jobfact",
            name="spec",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                to="core.packagespecdimension",
            ),
        ),
        migrations.AddField(
            model_name="jobfact",
            name="runner",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT, to="core.runnerdimension"
            ),
        ),
        migrations.AddField(
            model_name="jobfact",
            name="start_date",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT, to="core.datedimension"
            ),
        ),
        migrations.AddField(
            model_name="jobfact",
            name="start_time",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT, to="core.timedimension"
            ),
        ),
        migrations.AddConstraint(
            model_name="jobdatadimension",
            constraint=models.CheckConstraint(
                check=models.Q(
                    ("status", "failed"),
                    ("error_taxonomy__isnull", True),
                    _connector="OR",
                ),
                name="error-taxonomy-only-on-failed-status",
            ),
        ),
        migrations.AddConstraint(
            model_name="datedimension",
            constraint=models.CheckConstraint(
                check=models.Q(("date_key__lt", 20440101)), name="date-key-value"
            ),
        ),
        migrations.AddConstraint(
            model_name="jobfact",
            constraint=models.CheckConstraint(
                check=models.Q(
                    models.Q(
                        ("node_cpu__isnull", True),
                        ("node_memory__isnull", True),
                        ("node_price_per_second__isnull", True),
                        ("pod_avg_mem__isnull", True),
                        ("pod_cpu_usage_seconds__isnull", True),
                        ("pod_max_mem__isnull", True),
                        ("pod_node_occupancy__isnull", True),
                    ),
                    models.Q(
                        ("node_cpu__isnull", False),
                        ("node_memory__isnull", False),
                        ("node_price_per_second__isnull", False),
                        ("pod_avg_mem__isnull", False),
                        ("pod_cpu_usage_seconds__isnull", False),
                        ("pod_max_mem__isnull", False),
                        ("pod_node_occupancy__isnull", False),
                    ),
                    _connector="OR",
                ),
                name="nullable-field-consistency",
            ),
        ),
        migrations.AddConstraint(
            model_name="jobfact",
            constraint=models.UniqueConstraint(
                fields=(
                    "start_date",
                    "start_time",
                    "node",
                    "runner",
                    "package",
                    "spec",
                    "job",
                ),
                name="job-fact-composite-key",
            ),
        ),
    ]
