import os
import json
from datetime import datetime
from django.test import TestCase
from django.conf import settings
from readux_ingest_ecds.services import iiif_services
from readux_ingest_ecds.services.metadata_services import metadata_from_file
from .factories import LocalFactory, LanguageFactory, CanvasFactory


class IIIFServicesTest(TestCase):
    def setUp(self):
        """Set instance variables."""
        super().setUp()
        self.fixture_path = settings.FIXTURE_DIR

    def test_creating_manifest(self):
        """It should create a manifest with the ingest's metadata."""
        extra_metadata = metadata_from_file(
            os.path.join(self.fixture_path, "extra_metadata.csv")
        )[0]
        local = LocalFactory.create(metadata=extra_metadata)
        manifest = iiif_services.create_manifest(local)
        assert extra_metadata["pid"] == manifest.pid
        assert "ssdl:spatialCoverageFastUri" in [d["label"] for d in manifest.metadata]

    def test_creating_manifest_without_language(self):
        """It should create a manifest with the default language."""

        metadata = metadata_from_file(
            os.path.join(self.fixture_path, "extra_metadata.csv")
        )[0]
        language = LanguageFactory.create(name="English", code="en")
        local = LocalFactory.create(metadata=metadata)
        manifest = iiif_services.create_manifest(local)
        assert language in manifest.languages.all()

    def test_creating_manifest_with_language(self):
        """It should create a manifest with the ingest's metadata."""

        metadata = metadata_from_file(
            os.path.join(self.fixture_path, "metadata_with_language.csv")
        )[0]
        language = LanguageFactory.create(name="Creek", code="mus")
        default_language = LanguageFactory.create(name="English", code="en")
        local = LocalFactory.create(metadata=metadata)
        manifest = iiif_services.create_manifest(local)
        assert language in manifest.languages.all()
        assert default_language not in manifest.languages.all()

    def test_creating_manifest_with_multiple_languages(self):
        """It should create a manifest with each language in the ingest's metadata."""

        metadata = metadata_from_file(
            os.path.join(self.fixture_path, "metadata_with_languages.csv")
        )[0]
        language1 = LanguageFactory.create(name="Creek", code="mus")
        language2 = LanguageFactory.create(name="German", code="de")
        local = LocalFactory.create(metadata=metadata)
        manifest = iiif_services.create_manifest(local)
        assert language1 in manifest.languages.all()
        assert language2 in manifest.languages.all()

    def test_creating_manifest_with_language_not_in_db(self):
        """It should create a manifest with the default language if the supplied langues is not in the database."""

        metadata = metadata_from_file(
            os.path.join(self.fixture_path, "metadata_with_language.csv")
        )[0]
        language = LanguageFactory.create(name="English", code="en")
        local = LocalFactory.create(metadata=metadata)
        manifest = iiif_services.create_manifest(local)
        assert language in manifest.languages.all()

    def test_creating_manifest_when_one_language_is_in_db_other_is_not(self):
        """It should create a manifest with the with only existing language listed."""

        metadata = metadata_from_file(
            os.path.join(self.fixture_path, "metadata_with_languages.csv")
        )[0]
        language = LanguageFactory.create(name="Creek", code="mus")
        default_language = LanguageFactory.create(name="English", code="en")
        local = LocalFactory.create(metadata=metadata)
        manifest = iiif_services.create_manifest(local)
        assert language in manifest.languages.all()
        assert default_language not in manifest.languages.all()
        assert manifest.languages.count() == 1

    def test_creating_manifest_from_manifest_v2(self):
        """It should crete a manifest/volume from a remote IIIF manifest."""
        manifest, _, _ = iiif_services.manifest_from_manifest(
            "https://example.org", "v2"
        )
        with open(os.path.join(self.fixture_path, "v2_manifest.json")) as f:
            content = json.load(f)
            assert manifest["label"] == content["label"]
            assert manifest["published_date"] == "1971"
            assert "Export Date" in [d["label"] for d in manifest["metadata"]]

    def test_creating_manifest_from_manifest_v3(self):
        """It should crete a manifest/volume from a remote IIIF manifest."""
        manifest, _, _ = iiif_services.manifest_from_manifest("https://example.org")
        with open(os.path.join(self.fixture_path, "v3_manifest.json")) as f:
            content = json.load(f)
            assert manifest["label"] == content["label"]
            assert manifest["published_date"] == datetime(1878, 1, 1)
            assert "Full Title" in [d["label"] for d in manifest["metadata"]]

    def test_creating_canvas_from_manifest(self):
        """It should create a canvas from a canvas item from a IIIF manifest."""
        with open(os.path.join(self.fixture_path, "v3_manifest.json")) as f:
            content = json.load(f)
            item = content["items"][0]
            assert item["type"] == "Canvas"
            canvas = iiif_services.canvas_from_manifest(item)
            assert canvas["width"] == item["width"]
            assert canvas["pid"] == "1878-Helpin-EMU-0001.tiff"

    def test_creating_ocr_from_annotation_page(self):
        """It should create an OCR annotation from a IIIF annotation page."""
        CanvasFactory.create(pid="1878-Helpin-EMU-0001.tiff")
        with open(os.path.join(self.fixture_path, "ocr_page_1.json")) as f:
            content = json.load(f)
            item = content["items"][0]
            ocr_annos = iiif_services.ocr_from_annotation_page("https://example.org", 0)
            assert "By" in ocr_annos[0]["content"]
            assert ocr_annos[0]["x"] == 741
            assert len(ocr_annos) == 4
