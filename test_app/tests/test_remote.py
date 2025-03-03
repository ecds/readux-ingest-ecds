from django.test import TestCase
from .factories import RemoteFactory
from iiif.models import Manifest, Canvas, OCR


class RemoteIngestTest(TestCase):
    def setUp(self):
        """Set instance variables."""
        super().setUp()

    def test_remote_ingest(self):
        """It should create manifest/volume, canvases, and OCR based on remote manifest."""
        ingest = RemoteFactory.create()
        ingest.ingest()
        manifest = Manifest.objects.get(pid="1878-Helpin-EMU")
        assert manifest.canvas_set.count() == 3
        assert manifest.canvas_set.all()[0].ocr_set.count() == 4
