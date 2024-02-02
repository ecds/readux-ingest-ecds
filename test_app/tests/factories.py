from os.path import join
from django_celery_results.models import TaskResult
from factory.django import DjangoModelFactory, FileField, ImageField
from factory import Faker, SubFactory
from django.conf import settings
from readux_ingest_ecds.models import Local, Bulk, VolumeFile
from iiif.models import ImageServer, Manifest, User, Collection

class ImageServerFactory(DjangoModelFactory):
    server_base = 'http://iiif.ecds.emory.edu'

    class Meta: # pylint: disable=too-few-public-methods, missing-class-docstring
        model = ImageServer

class ManifestFactory(DjangoModelFactory):
    """Creates a Manifest object for testing."""
    class Meta: # pylint: disable=too-few-public-methods, missing-class-docstring
        model = Manifest

class LocalFactory(DjangoModelFactory):
    class Meta:
        model = Local

    bundle = FileField(filename='bundle.zip', filepath=join(settings.FIXTURE_DIR, 'bundle.zip'))
    image_server = SubFactory(ImageServerFactory)
    manifest = None

class UserFactory(DjangoModelFactory):
    """ Factory for fake user """
    username = Faker("user_name")
    email = Faker("email")
    name = Faker("name")

    class Meta:
        model = User

class VolumeBundleFileFactory(DjangoModelFactory):
    file = FileField(filename='volume2.zip', filepath=join(settings.FIXTURE_DIR, 'bulk', 'volume2.zip'))

    class Meta:
        model = VolumeFile

class VolumeMetadataFileFactory(DjangoModelFactory):
    file = FileField(filename='metadata.csv', filepath=join(settings.FIXTURE_DIR, 'bulk', 'metadata.csv'))

    class Meta:
        model = VolumeFile

class BulkFactory(DjangoModelFactory):
    class Meta:
        model = Bulk

    image_server = SubFactory(ImageServerFactory)
class CollectionFactory(DjangoModelFactory):
    """
    Factory for mocking :class:`apps.iiif.kollections.models.Collection` objects.
    """
    class Meta:
        model = Collection
