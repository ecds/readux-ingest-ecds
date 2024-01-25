""" Tests for local ingest """
import os
from shutil import rmtree
import pytest
import boto3
from uuid import UUID
from zipfile import ZipFile
from moto import mock_s3
from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings
from .factories import ImageServerFactory
from readux_ingest_ecds.models import Local
from readux_ingest_ecds.services.iiif_services import create_manifest
from iiif.models import Canvas, OCR

pytestmark = pytest.mark.django_db(transaction=True) # pylint: disable = invalid-name

@mock_s3
class LocalTest(TestCase):
    """ Tests for ingest.models.Local """

    def setUp(self):
        """ Set instance variables. """
        super().setUp()
        rmtree(settings.INGEST_TMP_DIR, ignore_errors=True)
        self.fixture_path = settings.FIXTURE_DIR
        self.image_server = ImageServerFactory()

        conn = boto3.resource('s3', region_name='us-east-1')
        conn.create_bucket(Bucket=settings.INGEST_TRIGGER_BUCKET)

    # def teardown_class():
    #     rmtree(settings.INGEST_TMP_DIR, ignore_errors=True)

    def mock_local(self, bundle, with_manifest=False, metadata={}, from_bulk=False):
        # Note, I tried to use the factory here, but could not get it to override the file for bundle.
        local = Local(
            image_server = self.image_server,
            metadata = metadata
        )
        local.save()
        file = SimpleUploadedFile(
                name=bundle,
                content=open(os.path.join(self.fixture_path, bundle), 'rb').read()
            )
        if from_bulk:
            local.bundle_from_bulk.save(bundle, file)
        else:
            local.bundle = file

        local.save()

        if with_manifest:
            local.manifest = create_manifest(local)
            local.save()

        local.refresh_from_db()
        return local


    def test_bundle_upload(self):
        """ It should upload the images using a fake S3 service from moto. """
        for bundle in ['bundle.zip', 'nested_volume.zip', 'csv_meta.zip']:
            self.mock_local(bundle)
            assert bundle in os.listdir(settings.INGEST_TMP_DIR)

    def test_open_excel_metadata(self):
        """ It should open the metadata Excel file. """
        local = self.mock_local('bundle.zip')
        local.open_metadata()
        assert local.metadata['pid'] == 'sqn75'

    def test_open_csv_metadata(self):
        """ It should open the metadata CSV file. """
        local = self.mock_local('csv_meta.zip')
        local.open_metadata()
        assert local.metadata['pid'] == 'sqn75'

    def test_open_tsv_metadata(self):
        """ It should open the metadata TSV file. """
        local = self.mock_local('tsv.zip')
        local.open_metadata()
        assert local.metadata['pid'] == 'cdc-ledger-1'

    def test_creating_manifest(self):
        """ It should open the metadata CSV file. """
        local = self.mock_local('csv_meta.zip')
        local.manifest = create_manifest(local)
        assert local.manifest.pid == 'sqn75'

    def test_metadata_from_excel(self):
        """ It should create a manifest with metadata supplied in an Excel file. """
        local = self.mock_local('bundle.zip')
        local.prep()

        assert 'pid' in local.metadata.keys()

        for key in local.metadata.keys():
            assert str(local.metadata[key]) == str(getattr(local.manifest, key))

    def test_metadata_from_csv(self):
        """ It should create a manifest with metadata supplied in a CSV file. """
        local = self.mock_local('csv_meta.zip', with_manifest=True)
        local.prep()

        assert 'pid' in local.metadata.keys()

        for key in local.metadata.keys():
            assert local.metadata[key] == getattr(local.manifest, key)

    def test_metadata_from_tsv(self):
        """ It should create a manifest with metadata supplied in a TSV file. """
        local = self.mock_local('tsv.zip', with_manifest=True)
        local.open_metadata()

        assert 'pid' in local.metadata.keys()

        for key in local.metadata.keys():
            assert local.metadata[key] == getattr(local.manifest, key)

    def test_no_metadata_file(self):
        """ It should create a Manifest even when no metadata file is supplied. """
        local = self.mock_local('no_meta_file.zip', with_manifest=True)
        local.prep()

        # New manifest should have a default pid - UUID in test app.
        assert UUID(local.manifest.pid, version=4)

    def test_unzip_bundle(self):
        local = self.mock_local('csv_meta.zip')
        local.prep()
        local.refresh_from_db()
        local.unzip_bundle()

        assert os.path.isfile(os.path.join(settings.INGEST_PROCESSING_DIR, f'{local.manifest.pid}_00000005.jpg'))
        assert os.path.isfile(os.path.join(settings.INGEST_OCR_DIR, local.manifest.pid, f'{local.manifest.pid}_00000007.tsv'))

    def test_create_canvases(self):
        local = self.mock_local('csv_meta.zip')
        local.prep()
        local.refresh_from_db()
        local.unzip_bundle()
        local.create_canvases()

        assert local.manifest.canvas_set.count() == 10

    def test_ignoring_junk(self):
        """
        Any hidden files should not be uploaded.
        """
        local = self.mock_local('bundle_with_junk.zip')
        local.prep()
        local.unzip_bundle()

        with ZipFile(os.path.join(self.fixture_path, 'bundle_with_junk.zip'), 'r') as zip_ref:
            files_in_bundle = zip_ref.namelist()

        assert os.path.isfile(os.path.join(settings.INGEST_PROCESSING_DIR, f'{local.manifest.pid}_00000009.jpg'))
        assert os.path.isfile(os.path.join(settings.INGEST_OCR_DIR, local.manifest.pid, f'{local.manifest.pid}_00000003.tsv'))
        assert 'images/.00000010.jpg' in files_in_bundle
        assert '__MACOSX/images/._00000010.jpg' in files_in_bundle
        assert 'ocr/.junk.tsv' in files_in_bundle
        assert os.path.isfile(os.path.join(settings.INGEST_PROCESSING_DIR, f'{local.manifest.pid}.000000010.jpg')) is False
        assert os.path.isfile(os.path.join(settings.INGEST_OCR_DIR, local.manifest.pid, f'{local.manifest.pid}.junk.tsv')) is False

    def test_when_metadata_in_filename(self):
        """
        Make sure it doesn't get get confused when the word "metadata" is in
        every path.
        """
        local = self.mock_local('metadata.zip', with_manifest=True)
        local.open_metadata()

        assert local.metadata['pid'] == 't9wtf-sample'

    def test_creating_canvases(self):
        """
        Make sure it doesn't get get confused when the word "metadata" is in
        every path.
        """
        local = self.mock_local('bundle.zip', with_manifest=True)
        local.prep()
        local.unzip_bundle()
        local.create_canvases()

        pid = local.manifest.pid

        assert local.manifest.canvas_set.all().count() == 10
        assert Canvas.objects.get(pid=f'{pid}_00000001.tiff').position == 1
        assert Canvas.objects.get(pid=f'{pid}_00000002.tiff').position == 2
        assert Canvas.objects.get(pid=f'{pid}_00000003.tiff').position == 3
        assert Canvas.objects.get(pid=f'{pid}_00000004.tiff').position == 4
        assert Canvas.objects.get(pid=f'{pid}_00000005.tiff').position == 5
        assert Canvas.objects.get(pid=f'{pid}_00000006.tiff').position == 6
        assert Canvas.objects.get(pid=f'{pid}_00000007.tiff').position == 7
        assert Canvas.objects.get(pid=f'{pid}_00000008.tiff').position == 8
        assert Canvas.objects.get(pid=f'{pid}_00000009.tiff').position == 9
        assert Canvas.objects.get(pid=f'{pid}_00000010.tiff').position == 10
        assert Canvas.objects.get(pid=f'{pid}_00000010.tiff').width == 32
        assert Canvas.objects.get(pid=f'{pid}_00000010.tiff').height == 43

    def test_it_creates_manifest_with_metadata_property(self):
        metadata = {
            'pid': '808',
            'title': 'Goodie Mob'
        }
        local = self.mock_local('no_meta_file.zip', metadata=metadata)
        local.manifest = create_manifest(local)
        local.prep()
        assert local.manifest.pid == '808'
        assert local.manifest.title == 'Goodie Mob'
