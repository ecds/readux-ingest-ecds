from os.path import join
from shutil import rmtree
import boto3
from django.conf import settings
from django.contrib.admin.sites import AdminSite
from django.core import files
from django.http import HttpResponseRedirect
from django.test import TestCase
from django.test.client import RequestFactory
# from django.urls.base import reverse
# from django_celery_results.models import TaskResult
from moto import mock_s3
from iiif.models import Manifest, Canvas, Collection, OCR
from .factories import ImageServerFactory, UserFactory, LocalFactory, ManifestFactory, CollectionFactory
from readux_ingest_ecds.models import Local
from readux_ingest_ecds.admin import LocalAdmin

@mock_s3
class LocalIngestAdminTest(TestCase):
    """ Tests Ingest Admin """
    def setUp(self):
        """ Set instance variables. """
        self.fixture_path = settings.FIXTURE_DIR

        self.image_server = ImageServerFactory.create()

        self.user = UserFactory.create(is_superuser=True)

        # Create fake bucket for moto's mock S3 service.
        conn = boto3.resource('s3', region_name='us-east-1')
        conn.create_bucket(Bucket=settings.INGEST_TRIGGER_BUCKET)

    def teardown_class():
        rmtree(settings.INGEST_TMP_DIR, ignore_errors=True)

    def test_local_admin_save(self):
        """It should add a create a manifest and canvases and delete the Local object"""
        local = LocalFactory.build(image_server=self.image_server)

        original_manifest_count = Manifest.objects.count()
        original_canvas_count = Canvas.objects.count()
        original_ocr_count = OCR.objects.count()

        request_factory = RequestFactory()

        with open(join(self.fixture_path, 'no_meta_file.zip'), 'rb') as f:
            content = files.base.ContentFile(f.read())

        local.bundle = files.File(content.file, 'no_meta_file.zip')

        req = request_factory.post('/admin/readux_ingest_ecds/local/add/', data={})
        req.user = self.user

        local_model_admin = LocalAdmin(model=Local, admin_site=AdminSite())
        local_model_admin.save_model(obj=local, request=req, form=None, change=None)

        # Saving should kick off the task to create the canvases and then delete
        # the `Local` ingest object when done.
        # try:
        #     local.refresh_from_db()
        #     assert False
        # except Local.DoesNotExist:
        #     assert True

        # A new `Manifest` should have been created along with the canvases
        # in the ingest
        assert Manifest.objects.count() == original_manifest_count + 1
        assert Canvas.objects.count() == original_canvas_count + 10
        assert OCR.objects.count() == original_ocr_count + 1073

    def test_local_admin_response_add(self):
        """It should redirect to new manifest"""
        local = LocalFactory.create(manifest=ManifestFactory.create())
        local_model_admin = LocalAdmin(model=Local, admin_site=AdminSite())
        response = local_model_admin.response_add(obj=local, request=None)

        assert isinstance(response, HttpResponseRedirect)
        assert response.url == f'/admin/manifests/manifest/{local.manifest.pk}/change/'

    def test_local_ingest_with_collections(self):
        """It should add chosen collections to the Local's manifests"""
        local = LocalFactory.build(image_server=self.image_server)

        # Force evaluation to get the true current list of manifests
        manifests_before = list(Manifest.objects.all())

        # Assign collections to Local
        for _ in range(3):
            CollectionFactory.create()
        collections = Collection.objects.all()
        local.save()
        local.collections.set(collections)
        assert len(local.collections.all()) == 3

        # Make a local ingest
        request_factory = RequestFactory()
        with open(join(self.fixture_path, 'no_meta_file.zip'), 'rb') as f:
            content = files.base.ContentFile(f.read())
        local.bundle = files.File(content.file, 'no_meta_file.zip')
        req = request_factory.post('/admin/ingest/local/add/', data={})
        req.user = self.user
        local_model_admin = LocalAdmin(model=Local, admin_site=AdminSite())
        local_model_admin.save_model(obj=local, request=req, form=None, change=None)

        # Get the newly created manifest by comparing current list to the list before
        manifests_after = list(Manifest.objects.all())
        new_manifests = [x for x in manifests_after if x not in manifests_before]
        assert len(new_manifests) == 1
        assert isinstance(new_manifests[0], Manifest)

        # The new manifest should get the Local's collections
        assert new_manifests[0].collections.count() == 3
