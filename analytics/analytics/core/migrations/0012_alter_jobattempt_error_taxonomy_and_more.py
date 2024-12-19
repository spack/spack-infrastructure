# Generated by Django 4.2.4 on 2024-02-14 14:16

from django.db import migrations, models


def set_error_taxonomy_to_null(apps, schema_editor):
    JobAttempt = apps.get_model("core", "JobAttempt")
    JobAttempt.objects.filter(status="success").update(error_taxonomy=None)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0011_jobattempt_section_timers"),
    ]

    operations = [
        migrations.AlterField(
            model_name="jobattempt",
            name="error_taxonomy",
            field=models.CharField(max_length=64, null=True),
        ),
        # migrations.RunPython(set_error_taxonomy_to_null),
        migrations.AddConstraint(
            model_name="jobattempt",
            constraint=models.CheckConstraint(
                check=models.Q(
                    ("status", "failed"),
                    ("error_taxonomy__isnull", True),
                    _connector="OR",
                ),
                name="error-taxonomy-only-on-failed",
            ),
        ),
    ]
