import os
import boto3
from faker import Faker
from moto import mock_aws
from django.test import TestCase
from django.conf import settings
from readux_ingest_ecds.services import file_services


@mock_aws
class FileServicesTest(TestCase):
    def setUp(self):
        """Set instance variables."""
        super().setUp()
        self.fake = Faker()
        self.fixture_path = settings.FIXTURE_DIR
        self.s3 = boto3.resource("s3", region_name="us-east-1")
        self.s3.create_bucket(Bucket=settings.INGEST_TRIGGER_BUCKET)
        self.s3.create_bucket(Bucket=settings.INGEST_BUCKET)
        self.s3.create_bucket(Bucket="source")

    def test_s3_copy(self):
        fixture_dir = os.path.join(self.fixture_path, "s3_copy")
        files = os.listdir(fixture_dir)
        for mock_file in files:
            with open(os.path.join(fixture_dir, mock_file), "rb") as f:
                if mock_file.endswith("jpg"):
                    self.s3.Bucket("source").upload_fileobj(
                        f, f"pid/images/{mock_file}"
                    )
                else:
                    self.s3.Bucket("source").upload_fileobj(f, f"pid/ocr/{mock_file}")

        images, ocr_files = file_services.s3_copy("source", "pid")

        for image in images:
            self.s3.Object(
                settings.INGEST_BUCKET,
                f"{settings.INGEST_STAGING_PREFIX}/{image}",
            ).load()

        for ocr in ocr_files:
            self.s3.Object(
                settings.INGEST_BUCKET,
                ocr,
            ).load()
        assert len(images) == 10
        assert len(ocr_files) == 10
