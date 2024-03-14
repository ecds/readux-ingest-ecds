""" Tests for bulk ingest """
import os
from shutil import rmtree, copyfile
import pytest
import boto3
from moto import mock_s3
from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings
from .factories import ImageServerFactory, BulkFactory
from readux_ingest_ecds.models import Bulk

pytestmark = pytest.mark.django_db(transaction=True) # pylint: disable = invalid-name

@mock_s3
class BulkTest(TestCase):
    """ Tests for ingest.models.Local """
    def setUp(self):
        """ Set instance variables. """
        super().setUp()
        rmtree(settings.INGEST_TMP_DIR, ignore_errors=True)
        self.fixture_path = os.path.join(settings.FIXTURE_DIR, 'bulk')
        self.image_server = ImageServerFactory()
        self.ingest_files = []

        conn = boto3.resource('s3', region_name='us-east-1')
        conn.create_bucket(Bucket=settings.INGEST_TRIGGER_BUCKET)

        self.bulk = BulkFactory.create(
            image_server = self.image_server,
        )
        os.makedirs(os.path.join(settings.INGEST_TMP_DIR, str(self.bulk.id)))
        for bulk_file in os.listdir(self.fixture_path):
            copyfile(
                os.path.join(self.fixture_path, bulk_file),
                os.path.join(settings.INGEST_TMP_DIR, str(self.bulk.id), bulk_file)
            )

    def teardown_class():
        rmtree(settings.INGEST_TMP_DIR, ignore_errors=True)

    # TODO: How to test the multi file upload?
    # def test_bulk_upload(self):
    #     """ It should upload all files """

    #     for ingest_file in self.bulk.volume_files:
    #         assert os.path.exists(
    #             os.path.join(
    #                 settings.INGEST_TMP_DIR,
    #                 str(self.bulk.pk),
    #                 os.path.basename(ingest_file.file.name)
    #             )
    #         )

    def test_bulk_ingest(self):
        self.bulk.ingest()

        assert os.path.isfile(os.path.join(settings.INGEST_PROCESSING_DIR, 'pid3_00000005.jpg'))
