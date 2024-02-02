import os
from shutil import rmtree
import boto3
from moto import mock_s3
from django.contrib.admin.sites import AdminSite
from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test.client import RequestFactory
from django.conf import settings
from readux_ingest_ecds.admin import BulkAdmin
from readux_ingest_ecds.models import Bulk, VolumeFile
from .factories import BulkFactory, UserFactory

@mock_s3
class BulkIngestAdminTest(TestCase):
    """ Tests Ingest Admin """
    def setUp(self):
        """ Set instance variables. """
        conn = boto3.resource('s3', region_name='us-east-1')
        conn.create_bucket(Bucket=settings.INGEST_TRIGGER_BUCKET)

        self.fixture_path = os.path.join(settings.FIXTURE_DIR, 'bulk')
        self.request_factory = RequestFactory()
        self.user = UserFactory.create(is_superuser=True)
        self.bulk = BulkFactory.create()
        metadata_file = VolumeFile.objects.create(
            file=SimpleUploadedFile(
                name='metadata.csv',
                content=open(
                    os.path.join(self.fixture_path, 'metadata.csv'),
                    'rb'
                ).read()
            )
        )
        self.bundle_file = VolumeFile.objects.create(
            file=SimpleUploadedFile(
                name='volume2.zip',
                content=open(
                    os.path.join(self.fixture_path, 'volume2.zip'),
                    'rb'
                ).read()
            )
        )

        self.bulk.volume_files.add(metadata_file)
        self.bulk.volume_files.add(self.bundle_file)


    # def teardown_class():
    #     rmtree(settings.INGEST_TMP_DIR, ignore_errors=True)

    def test_bulk_admin_save(self):
        req = self.request_factory.post('/admin/readux_ingest_ecds/bulk/add/', data={})
        req.user = self.user
        bulk_model_admin = BulkAdmin(model=Bulk, admin_site=AdminSite())
        bulk_model_admin.save_model(obj=self.bulk, request=req, form=None, change=None)

        assert os.path.isfile(os.path.join(settings.INGEST_PROCESSING_DIR, 'pid2_00000005.jpg'))
