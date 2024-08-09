from django.test import TestCase
import os
import boto3
from moto import mock_aws
from django.core.files.uploadedfile import SimpleUploadedFile
from readux_ingest_ecds.models import Local
from readux_ingest_ecds.tasks import local_ingest_task_ecds
from shutil import rmtree
from django.conf import settings
from .factories import ImageServerFactory, LocalFactory


@mock_aws
class TaskTest(TestCase):
    """Test Celery tasks success and failure."""

    def setUp(self):
        """Set instance variables."""
        super().setUp()
        rmtree(settings.INGEST_TMP_DIR, ignore_errors=True)
        self.fixture_path = settings.FIXTURE_DIR
        self.image_server = ImageServerFactory()

        conn = boto3.resource("s3", region_name="us-east-1")
        conn.create_bucket(Bucket=settings.INGEST_TRIGGER_BUCKET)

    def teardown_class():
        rmtree(settings.INGEST_TMP_DIR, ignore_errors=True)

    def test_it_deletes_ingest_on_success(self):
        local = LocalFactory.create(
            bundle=SimpleUploadedFile(
                name="no_meta_file.zip",
                content=open(
                    os.path.join(self.fixture_path, "no_meta_file.zip"), "rb"
                ).read(),
            )
        )
        local.metadata = {"pid": "808", "publisher": "Goodie Mob"}
        local.prep()
        local_ingest_task_ecds(local.id)
        assert True
