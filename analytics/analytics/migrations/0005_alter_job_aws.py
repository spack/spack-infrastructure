# Generated by Django 4.2.4 on 2024-01-11 16:42

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("analytics", "0004_errortaxonomy"),
    ]

    operations = [
        migrations.AlterField(
            model_name="job",
            name="aws",
            field=models.BooleanField(default=True, null=True),
        ),
    ]