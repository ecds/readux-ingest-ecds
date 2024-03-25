import os
from django.test import TestCase
from django.conf import settings
from readux_ingest_ecds.services import ocr_services
from .factories import CanvasFactory, ImageServerFactory

class OCRTest(TestCase):
    def setUp(self):
        """ Set instance variables. """
        super().setUp()
        self.fixture_path = settings.FIXTURE_DIR

    def test_alto4_xml_file(self):
        """ It should normalize keys that match a Manifest field. """
        canvas = CanvasFactory.create(ocr_file_path=os.path.join(self.fixture_path, 'alto4.xml'))
        result = ocr_services.fetch_positional_ocr(canvas)
        ocr = ocr_services.parse_alto_ocr(result)
        assert ocr[1] == {'content': 'No.', 'h': 52, 'w': 85, 'x': 176, 'y': 438}