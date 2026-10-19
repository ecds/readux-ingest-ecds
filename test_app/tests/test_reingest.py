"""Re-ingesting a volume whose canvases already exist updates them in place,
except pages whose OCR has user annotations anchored to it."""

import os
from io import BytesIO
from shutil import rmtree
from unittest.mock import patch
import boto3
from moto import mock_aws
from PIL import Image
from django.conf import settings
from django.test import TestCase
from iiif.models import OCR, UserAnnotation
from readux_ingest_ecds.services import ocr_services
from .factories import CanvasFactory, LocalFactory, ManifestFactory

PID = "vol1"


@mock_aws
class ReingestTest(TestCase):
    def setUp(self):
        super().setUp()
        rmtree(settings.INGEST_TMP_DIR, ignore_errors=True)
        rmtree(os.path.join(settings.INGEST_OCR_DIR, PID), ignore_errors=True)
        s3 = boto3.resource("s3", region_name="us-east-1")
        self.ingest_bucket = s3.create_bucket(Bucket=settings.INGEST_BUCKET)
        self.trigger_bucket = s3.create_bucket(Bucket=settings.INGEST_TRIGGER_BUCKET)

        self.manifest = ManifestFactory.create(pid=PID)
        self.page1 = self.existing_page(1)
        self.page2 = self.existing_page(2)
        self.local = LocalFactory.create(manifest=self.manifest)

        os.makedirs(os.path.dirname(self.local.trigger_file), exist_ok=True)
        with open(self.local.trigger_file, "w", encoding="utf-8") as t_file:
            t_file.write(f"{PID}-0001.jpg\n{PID}-0002.jpg\n")
        self.stage(f"{PID}-0001.jpg", (640, 480))
        self.stage(f"{PID}-0002.jpg", (800, 600))

    def existing_page(self, number):
        canvas = CanvasFactory.create(
            manifest=self.manifest,
            pid=f"{PID}-000{number}.tiff",
            position=number + 6,
            width=100,
            height=100,
            ocr_file_path=f"/old/{PID}-000{number}.xml",
        )
        OCR.objects.create(canvas=canvas, x=1, y=1, w=1, h=1, content="old")
        return canvas

    def stage(self, name, size):
        image = BytesIO()
        Image.new("RGB", size).save(image, "JPEG")
        self.ingest_bucket.put_object(
            Key=f"{settings.INGEST_STAGING_PREFIX}/{name}", Body=image.getvalue()
        )

    def new_ocr_file(self, name):
        ocr_dir = os.path.join(settings.INGEST_OCR_DIR, PID)
        os.makedirs(ocr_dir, exist_ok=True)
        path = os.path.join(ocr_dir, name)
        open(path, "w", encoding="utf-8").close()
        return os.path.abspath(path)

    def converted_images(self):
        """Images listed in the trigger files uploaded for PTiff conversion."""
        listed = []
        for obj in self.trigger_bucket.objects.all():
            listed += obj.get()["Body"].read().decode().splitlines()
        return listed

    def test_existing_page_is_updated_and_its_ocr_cleared_for_rebuilding(self):
        new_path = self.new_ocr_file(f"{PID}-0001.xml")

        kept = self.local.create_canvases()

        self.page1.refresh_from_db()
        assert kept == []
        assert (self.page1.width, self.page1.height) == (640, 480)
        assert self.page1.ocr_file_path == new_path
        assert not OCR.objects.filter(canvas=self.page1).exists()
        # Position may have been set by hand; a re-ingest doesn't change it.
        assert self.page1.position == 7

    def test_image_only_reingest_keeps_the_pages_ocr(self):
        self.local.create_canvases()

        self.page1.refresh_from_db()
        assert (self.page1.width, self.page1.height) == (640, 480)
        assert self.page1.ocr_file_path == f"/old/{PID}-0001.xml"
        assert OCR.objects.filter(canvas=self.page1).exists()

    def test_page_with_anchored_annotation_is_left_untouched(self):
        self.new_ocr_file(f"{PID}-0001.xml")
        self.new_ocr_file(f"{PID}-0002.xml")
        anchored_word = OCR.objects.get(canvas=self.page1)
        annotation = UserAnnotation.objects.create(
            canvas=self.page1, start_selector=anchored_word
        )

        kept = self.local.create_canvases()

        self.page1.refresh_from_db()
        assert kept == [f"{PID}-0001.tiff"]
        assert (self.page1.width, self.page1.height) == (100, 100)
        assert self.page1.ocr_file_path == f"/old/{PID}-0001.xml"
        assert OCR.objects.filter(pk=anchored_word.pk).exists()
        assert UserAnnotation.objects.filter(pk=annotation.pk).exists()
        # Its new image isn't converted, so the page keeps showing the
        # image its OCR and annotations belong to.
        assert self.converted_images() == [f"{PID}-0002.jpg"]
        # The other page is still updated.
        self.page2.refresh_from_db()
        assert (self.page2.width, self.page2.height) == (800, 600)

    def test_ocr_step_skips_kept_pages_and_reports_them(self):
        new_word = [{"content": "new", "x": 5, "y": 5, "w": 5, "h": 5}]
        with patch.object(ocr_services, "get_ocr", return_value=new_word):
            warnings = ocr_services.add_ocr_to_canvases(
                self.manifest, kept_canvas_pids=[f"{PID}-0001.tiff"]
            )

        assert list(OCR.objects.filter(canvas=self.page1).values_list("content", flat=True)) == ["old"]
        assert OCR.objects.filter(canvas=self.page2, content="new").exists()
        assert len(warnings) == 1
        assert warnings[0].startswith(f"Canvas {PID}-0001.tiff - Kept this page's")

    def test_ocr_is_referenced(self):
        assert ocr_services.ocr_is_referenced(self.page1) is False

        UserAnnotation.objects.create(
            canvas=self.page1, start_selector=OCR.objects.get(canvas=self.page1)
        )

        assert ocr_services.ocr_is_referenced(self.page1) is True

    def test_ocr_file_exact_name_match_wins(self):
        self.new_ocr_file(f"copy-of-{PID}-0001.xml")
        exact = self.new_ocr_file(f"{PID}-0001.xml")
        suffixed = self.new_ocr_file(f"{PID}-0002_ocr.xml")

        assert self.local.ocr_file_for(f"{PID}-0001") == exact
        assert self.local.ocr_file_for(f"{PID}-0002") == suffixed
        assert self.local.ocr_file_for(f"{PID}-0003") is None
