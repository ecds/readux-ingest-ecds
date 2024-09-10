import os
from django.core import mail
from django.conf import settings
from django.test import TestCase
from readux_ingest_ecds.services import ocr_services
from readux_ingest_ecds.tasks import add_ocr_task_local
from .factories import CanvasFactory, LocalFactory, ManifestFactory, UserFactory


class OCRTest(TestCase):
    def setUp(self):
        """Set instance variables."""
        super().setUp()
        self.fixture_path = settings.FIXTURE_DIR

    def test_alto4_xml_file(self):
        """It should normalize keys that match a Manifest field."""
        canvas = CanvasFactory.create(
            ocr_file_path=os.path.join(self.fixture_path, "alto4.xml")
        )
        result = ocr_services.fetch_positional_ocr(canvas)
        ocr = ocr_services.parse_alto_ocr(result)
        assert ocr[1] == {"content": "No.", "h": 52, "w": 85, "x": 176, "y": 438}

    def test_empty_xml(self):
        """It should add a warning to the ingest."""
        manifest = ManifestFactory.create()
        canvas = CanvasFactory.create(
            ocr_file_path=os.path.join(self.fixture_path, "empty.xml"),
            manifest=manifest,
        )
        CanvasFactory.create(
            ocr_file_path=os.path.join(self.fixture_path, "empty.xml"),
            manifest=manifest,
        )
        local = LocalFactory.create(manifest=manifest, creator=UserFactory.create())
        add_ocr_task_local(local.id)
        local.refresh_from_db()
        local.success()
        assert local.warnings.startswith(
            f"Canvas {canvas.pid} - XMLSyntaxError: Document is empty, line 1, column 1 (<string>, line 1)\n"
        )
        assert "XMLSyntaxError" in mail.outbox[0].body
