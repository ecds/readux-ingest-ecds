from django.contrib.admin.sites import AdminSite
from django.test import TestCase
from django.test.client import RequestFactory
from moto import mock_aws
from iiif.models import Manifest, Canvas, OCR
from .factories import (
    RemoteFactory,
)
from readux_ingest_ecds.models import Remote
from readux_ingest_ecds.admin import RemoteAdmin


class RemoteIngestAdminTest(TestCase):
    """Tests Ingest Admin"""

    def test_local_admin_save(self):
        """It should add a create a manifest, canvases and OCR."""
        remote = RemoteFactory.build()
        remote.image_server.save()

        original_manifest_count = Manifest.objects.count()
        original_canvas_count = Canvas.objects.count()
        original_ocr_count = OCR.objects.count()

        request_factory = RequestFactory()

        req = request_factory.post("/admin/readux_ingest_ecds/remote/add/", data={})

        remote_model_admin = RemoteAdmin(model=Remote, admin_site=AdminSite())
        remote_model_admin.save_model(obj=remote, request=req, form=None, change=None)

        assert Manifest.objects.count() == original_manifest_count + 1
        assert Canvas.objects.count() == original_canvas_count + 3
        assert OCR.objects.count() == original_ocr_count + 9
