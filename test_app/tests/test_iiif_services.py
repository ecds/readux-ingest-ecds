import os
from django.test import TestCase
from django.conf import settings
from readux_ingest_ecds.services import iiif_services
from readux_ingest_ecds.services.metadata_services import metadata_from_file
from .factories import LocalFactory

class IIIFServicesTest(TestCase):
    def setUp(self):
        """ Set instance variables. """
        super().setUp()
        self.fixture_path = settings.FIXTURE_DIR

    def test_creating_manifest(self):
        """ It should create a manifest with the ingest's metadata. """
        extra_metadata = metadata_from_file(os.path.join(self.fixture_path, 'extra_metadata.csv'))[0]
        local = LocalFactory.create(metadata=extra_metadata)
        manifest = iiif_services.create_manifest(local)
        assert extra_metadata['pid'] == manifest.pid
        assert 'ssdl:spatialCoverageFastUri' in [d['label'] for d in manifest.metadata]
