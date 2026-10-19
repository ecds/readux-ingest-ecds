"""Tests for the S3 volume copy step and the image list it hands to
create_canvases()."""

import os
from io import BytesIO
from shutil import rmtree
from types import SimpleNamespace
from unittest.mock import patch
import boto3
import pytest
from moto import mock_aws
from PIL import Image
from django.conf import settings
from django.test import TestCase
from readux_ingest_ecds.services import file_services
from readux_ingest_ecds.services.file_services import volume_keys
from .factories import LocalFactory, ManifestFactory


class FakeBucket:
    """Records each Prefix listed so tests can see how much was listed."""

    def __init__(self, keys):
        self.keys = keys
        self.listed = []

    @property
    def objects(self):
        return self

    def filter(self, Prefix):  # pylint: disable=invalid-name
        self.listed.append(Prefix)
        return [SimpleNamespace(key=k) for k in self.keys if k.startswith(Prefix)]


class VolumeKeysTest(TestCase):
    def test_lists_only_the_volume_folder_for_the_standard_layout(self):
        bucket = FakeBucket(
            [
                "textract_output/vol1/images/vol1-0001.jpg",
                "textract_output/vol1/ocr/vol1-0001.txt",
                "textract_output/vol2/images/vol2-0001.jpg",
            ]
        )

        keys = volume_keys(bucket, "vol1", "textract_output")

        assert keys == [
            "textract_output/vol1/images/vol1-0001.jpg",
            "textract_output/vol1/ocr/vol1-0001.txt",
        ]
        # One narrow listing; never the whole prefix with every volume in it.
        assert bucket.listed == ["textract_output/vol1/"]

    def test_falls_back_to_the_prefix_for_other_layouts(self):
        bucket = FakeBucket(
            ["emory/images/vol1/a.jpg", "emory/images/vol10/b.jpg", "emory/ocr/vol1/a.txt"]
        )

        keys = volume_keys(bucket, "vol1", "emory")

        assert keys == ["emory/images/vol1/a.jpg", "emory/ocr/vol1/a.txt"]
        assert bucket.listed == ["emory/vol1/", "emory/"]

    def test_blank_prefix_means_no_prefix(self):
        bucket = FakeBucket(["vol1/images/a.jpg"])

        assert volume_keys(bucket, "vol1", "") == ["vol1/images/a.jpg"]
        assert volume_keys(bucket, "vol1", "/") == ["vol1/images/a.jpg"]


@pytest.mark.django_db
class LocalImageListTest(TestCase):
    def setUp(self):
        super().setUp()
        rmtree(settings.INGEST_TMP_DIR, ignore_errors=True)
        self.local = LocalFactory.create(
            manifest=ManifestFactory.create(),
            from_s3=True,
            source_bucket="source",
            prefix="textract_output",
        )

    def test_copy_writes_the_complete_image_list(self):
        with patch(
            "readux_ingest_ecds.models.s3_copy", return_value=(["b.jpg", "a.jpg"], [])
        ):
            self.local.copy_from_s3()

        with open(self.local.trigger_file, encoding="utf-8") as t_file:
            assert t_file.read() == "b.jpg\na.jpg\n"
        assert not os.path.exists(f"{self.local.trigger_file}.tmp")

    def test_interrupted_copy_leaves_no_image_list(self):
        with patch(
            "readux_ingest_ecds.models.s3_copy", side_effect=ConnectionError("dropped")
        ):
            with self.assertRaises(ConnectionError):
                self.local.copy_from_s3()

        assert not os.path.exists(self.local.trigger_file)

    def test_copy_with_no_images_raises_and_leaves_no_image_list(self):
        with patch("readux_ingest_ecds.models.s3_copy", return_value=([], [])):
            with self.assertRaisesRegex(ValueError, "No images found"):
                self.local.copy_from_s3()

        assert not os.path.exists(self.local.trigger_file)

    def test_create_canvases_without_image_list_explains_how_to_retry(self):
        with self.assertRaisesRegex(ValueError, "No image list.*re-save"):
            self.local.create_canvases()

    def test_create_canvases_with_empty_image_list_explains_how_to_retry(self):
        os.makedirs(os.path.dirname(self.local.trigger_file), exist_ok=True)
        open(self.local.trigger_file, "w", encoding="utf-8").close()

        with self.assertRaisesRegex(ValueError, "is empty.*re-save"):
            self.local.create_canvases()


@mock_aws
class CanvasDimensionsTest(TestCase):
    """Dimensions are read from the staged file itself, never from an IIIF
    server, whose cached info.json can describe an earlier file."""

    def setUp(self):
        super().setUp()
        self.bucket = boto3.resource("s3", region_name="us-east-1").create_bucket(
            Bucket=settings.INGEST_BUCKET
        )

    def stage(self, name, size, fmt="JPEG"):
        image = BytesIO()
        Image.new("RGB", size).save(image, fmt)
        self.bucket.put_object(
            Key=f"{settings.INGEST_STAGING_PREFIX}/{name}", Body=image.getvalue()
        )

    def test_reads_size_from_the_staged_file(self):
        self.stage("page-0001.jpg", (640, 480))

        assert file_services.canvas_dimensions("page-0001") == (640, 480)

    def test_rescanned_file_with_same_name_gets_its_new_size(self):
        self.stage("page-0001.jpg", (640, 480))
        assert file_services.canvas_dimensions("page-0001") == (640, 480)

        self.stage("page-0001.jpg", (1280, 2029))

        assert file_services.canvas_dimensions("page-0001") == (1280, 2029)

    def test_reads_whole_file_when_header_has_no_size(self):
        self.stage("page-0001.tif", (300, 200), fmt="TIFF")

        with patch.object(file_services, "IMAGE_HEADER_BYTES", 16):
            assert file_services.canvas_dimensions("page-0001") == (300, 200)

    def test_matches_the_whole_file_name(self):
        self.stage("page-0010.jpg", (640, 480))

        assert file_services.canvas_dimensions("page-001") == (0, 0)

    def test_missing_file_has_no_size(self):
        assert file_services.canvas_dimensions("page-0001") == (0, 0)
