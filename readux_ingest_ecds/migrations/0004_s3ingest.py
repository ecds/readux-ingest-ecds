# Generated by Django 3.2.23 on 2024-08-08 15:27

from django.conf import settings
import django.core.validators
from django.db import migrations, models
import django.db.models.deletion
import uuid

ImageServer = settings.IIIF_IMAGE_SERVER_MODEL


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("readux_ingest_ecds", "0003_bulk_metadata_file"),
    ]

    operations = [
        migrations.CreateModel(
            name="S3Ingest",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "s3_bucket",
                    models.CharField(
                        help_text="The name of a publicly-accessible S3 bucket containing volumes to\n        ingest, either at the bucket root or within subfolder(s). Each volume should have its own\n        subfolder, with the volume's PID as its name.\n        <br />\n        <strong>Example:</strong> if the bucket's URL is\n        https://my-bucket.s3.us-east-1.amazonaws.com/, its name is <strong>my-bucket</strong>.",
                        max_length=255,
                    ),
                ),
                (
                    "metadata_spreadsheet",
                    models.FileField(
                        help_text="A spreadsheet file with a row for each volume, including the\n        volume PID (column name <strong>pid</strong>).",
                        upload_to="",
                        validators=[
                            django.core.validators.FileExtensionValidator(
                                allowed_extensions=["csv", "xlsx"]
                            )
                        ],
                    ),
                ),
                (
                    "collections",
                    models.ManyToManyField(
                        blank=True,
                        help_text="Optional: Collections to attach to ALL volumes ingested in this form.",
                        to="iiif.Collection",
                    ),
                ),
                (
                    "creator",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="ecds_ingest_created_s3",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "image_server",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="ecds_s3_ingest_image_server",
                        to=ImageServer,
                    ),
                ),
            ],
            options={
                "verbose_name_plural": "Amazon S3 Ingests",
            },
        ),
    ]
