from os.path import join
from django.conf import settings
from django.contrib.admin.sites import AdminSite
from django.core import files
# from django.http import HttpResponseRedirect
from django.test import TestCase
from django.test.client import RequestFactory
# from django.urls.base import reverse
# from django_celery_results.models import TaskResult
from moto import mock_s3
from iiif.models import Manifest, Canvas
from .factories import ImageServerFactory, UserFactory, LocalFactory
from readux_ingest_ecds.models import Local
from readux_ingest_ecds.admin import LocalAdmin

@mock_s3
class IngestAdminTest(TestCase):
    # @classmethod
    # def setUpClass(cls):
    #     cls.sftp_server = MockSFTP()

    # @classmethod
    # def tearDownClass(cls):
    #     cls.sftp_server.stop_server()

    def setUp(self):
        """ Set instance variables. """
        self.fixture_path = settings.FIXTURE_DIR

        self.image_server = ImageServerFactory.create()

        self.user = UserFactory.create(is_superuser=True)

        # Create fake bucket for moto's mock S3 service.
        # conn = boto3.resource('s3', region_name='us-east-1')
        # conn.create_bucket(Bucket='readux')
        # conn.create_bucket(Bucket='readux-ingest')

    def test_local_admin_save(self):
        """It should add a create a manifest and canvases and delete the Local object"""
        local = LocalFactory.build(image_server=self.image_server)

        original_manifest_count = Manifest.objects.count()
        original_canvas_count = Canvas.objects.count()

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
        try:
            local.refresh_from_db()
            assert False
        except Local.DoesNotExist:
            assert True

        # A new `Manifest` should have been created along with the canvases
        # in the ingest
        assert Manifest.objects.count() == original_manifest_count + 1
        assert Canvas.objects.count() == original_canvas_count + 10

    # def test_local_admin_response_add(self):
    #     """It should redirect to new manifest"""

    #     local = LocalFactory.create(manifest=ManifestFactory.create())

    #     local_model_admin = LocalAdmin(model=Local, admin_site=AdminSite())
    #     response = local_model_admin.response_add(obj=local, request=None)

    #     assert isinstance(response, HttpResponseRedirect)
    #     assert response.url == f'/admin/manifests/manifest/{local.manifest.id}/change/'
