# Generated by Django 3.2.23 on 2024-09-09 19:57

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('readux_ingest_ecds', '0004_s3ingest'),
    ]

    operations = [
        migrations.AddField(
            model_name='local',
            name='warnings',
            field=models.CharField(blank=True, max_length=10000),
        ),
    ]
