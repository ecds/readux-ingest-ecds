from os.path import join
from django_celery_results.models import TaskResult
from factory.django import DjangoModelFactory, FileField, ImageField
from factory import Faker, SubFactory
from django.conf import settings
from readux_ingest_ecds.models import Local, Bulk
from iiif.models import ImageServer, Manifest, User, Collection, Canvas

class ImageServerFactory(DjangoModelFactory):
    server_base = 'http://iiif.ecds.emory.edu'

    class Meta: # pylint: disable=too-few-public-methods, missing-class-docstring
        model = ImageServer

class ManifestFactory(DjangoModelFactory):
    """Creates a Manifest object for testing."""
    image_server = SubFactory(ImageServerFactory)
    class Meta: # pylint: disable=too-few-public-methods, missing-class-docstring
        model = Manifest

class CanvasFactory(DjangoModelFactory):
    """Creates a Canvas object for testing."""
    manifest = SubFactory(ManifestFactory)
    position = 1
    class Meta:
        model = Canvas

class LocalFactory(DjangoModelFactory):
    class Meta:
        model = Local

    bundle = FileField(filename='bundle.zip', filepath=join(settings.FIXTURE_DIR, 'bundle.zip'))
    manifest = None
    image_server = SubFactory(ImageServerFactory)

class UserFactory(DjangoModelFactory):
    """ Factory for fake user """
    username = Faker("user_name")
    email = Faker("email")
    name = Faker("name")

    class Meta:
        model = User

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
