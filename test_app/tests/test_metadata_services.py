from django.test import TestCase
from readux_ingest_ecds.services.metadata_services import clean_metadata

class MetadataServiceTest(TestCase):
    def test_cleaning_metadata(self):
        """ It should normalize keys that match a Manifest field. """
        fake_metadata = {
            'pid': 'blm',
            'Special': 'coffee',
            'summary': 'idk',
            'PUBLISHER': 'ecds',
            'Published City': 'atlanta'
        }

        cleaned_metadata = clean_metadata(fake_metadata)

        assert 'Published City' not in cleaned_metadata.keys()
        assert 'PUBLISHER' not in cleaned_metadata.keys()
        assert cleaned_metadata['published_city'] == fake_metadata['Published City']
        assert cleaned_metadata['publisher'] == fake_metadata['PUBLISHER']
        print(cleaned_metadata)
        assert 'Special' in [m['label'] for m in cleaned_metadata['metadata']]
