""" Test admin for bulk ingest """

import os
from shutil import rmtree
import boto3
from moto import mock_s3
from django.contrib.admin.sites import AdminSite
from django.test import TestCase
from django.core import files
from django.test.client import RequestFactory
from django.conf import settings
from readux_ingest_ecds.admin import BulkAdmin
from readux_ingest_ecds.models import Local, Bulk
from readux_ingest_ecds.forms import BulkVolumeUploadForm
from .factories import BulkFactory, UserFactory


@mock_s3
class BulkIngestAdminTest(TestCase):
    """Tests Ingest Admin"""

    def setUp(self):
        """Set instance variables."""
        conn = boto3.resource("s3", region_name="us-east-1")
        conn.create_bucket(Bucket=settings.INGEST_TRIGGER_BUCKET)

        self.fixture_path = os.path.join(settings.FIXTURE_DIR, "bulk")
        self.request_factory = RequestFactory()
        self.user = UserFactory.create(is_superuser=True)
        self.bulk = BulkFactory.create()

    def teardown_class():
        """Clean up files when done"""
        rmtree(settings.INGEST_TMP_DIR, ignore_errors=True)

    def test_bulk_admin_save(self):
        """Uploaded multiple files should put files in correct places."""
        metadata_file_path = os.path.join(self.fixture_path, "metadata_admin_test.csv")
        with open(metadata_file_path, "rb") as f:
            metadata_content = files.base.ContentFile(f.read())
        metadata_file = files.File(metadata_content.file, "metadata.csv")

        bundle_file_one_path = os.path.join(
            os.path.join(self.fixture_path, "volume2.zip")
        )
        with open(bundle_file_one_path, "rb") as f:
            bundle_file_one_content = files.base.ContentFile(f.read())
        bundle_file_one = files.File(bundle_file_one_content.file, "volume2.zip")

        bundle_file_two_path = os.path.join(
            os.path.join(self.fixture_path, "volume3.zip")
        )
        with open(bundle_file_two_path, "rb") as f:
            bundle_file_two_content = files.base.ContentFile(f.read())
        bundle_file_two = files.File(bundle_file_two_content.file, "volume3.zip")

        assert not os.path.isfile(
            os.path.join(settings.INGEST_PROCESSING_DIR, "pid5_00000005.jpg")
        )
        assert not os.path.isfile(
            os.path.join(settings.INGEST_PROCESSING_DIR, "pid6_00000008.jpg")
        )

        req = self.request_factory.post("/admin/readux_ingest_ecds/bulk/add/", data={})
        req.FILES["volume_files"] = [metadata_file, bundle_file_one, bundle_file_two]
        req.user = self.user
        bulk_model_admin = BulkAdmin(model=Bulk, admin_site=AdminSite())
        bulk_model_admin.save_model(
            obj=self.bulk, request=req, form=BulkVolumeUploadForm(), change=None
        )

        assert os.path.isfile(
            os.path.join(settings.INGEST_PROCESSING_DIR, "pid5_00000005.jpg")
        )
        assert os.path.isfile(
            os.path.join(settings.INGEST_PROCESSING_DIR, "pid6_00000008.jpg")
        )

    def test_bulk_admin_save_multiple(self):
        """It should add three Local objects to this Bulk object"""
        bulk = BulkFactory.create()

        assert Local.objects.all().count() == 0

        # Add 3 files to POST request
        data = {}
        metadata_file_path = os.path.join(self.fixture_path, "metadata.csv")
        with open(metadata_file_path, "rb") as f:
            metadata_content = files.base.ContentFile(f.read())
        metadata_file = files.File(metadata_content.file, "metadata.csv")

        bundle_file_one_path = os.path.join(
            os.path.join(self.fixture_path, "volume2.zip")
        )
        with open(bundle_file_one_path, "rb") as f:
            bundle_file_one_content = files.base.ContentFile(f.read())
        bundle_file_one = files.File(bundle_file_one_content.file, "volume2.zip")

        bundle_file_two_path = os.path.join(
            os.path.join(self.fixture_path, "volume3.zip")
        )
        with open(bundle_file_two_path, "rb") as f:
            bundle_file_two_content = files.base.ContentFile(f.read())
        bundle_file_two = files.File(bundle_file_two_content.file, "volume3.zip")
        data["volume_files"] = [metadata_file, bundle_file_one, bundle_file_two]

        request_factory = RequestFactory()
        req = request_factory.post("/admin/ingest/bulk/add/", data=data)
        req.user = self.user

        bulk_model_admin = BulkAdmin(model=Bulk, admin_site=AdminSite())
        mock_form = BulkVolumeUploadForm()
        bulk_model_admin.save_model(obj=bulk, request=req, form=mock_form, change=None)

        bulk.refresh_from_db()
        assert Local.objects.all().count() == 2
