from os.path import join
from django_celery_results.models import TaskResult
from factory.django import DjangoModelFactory, FileField
from factory import Faker, SubFactory
from django.conf import settings
from readux_ingest_ecds.models import Local
from iiif.models import ImageServer, Manifest
# from readux_ingest_ecds.task_utils import IngestTaskWatcher

class ImageServerFactory(DjangoModelFactory):
    server_base = 'http://images.ecds.emory.edu'

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

# class TaskResultFactory(DjangoModelFactory):
#     class Meta:
#         model = TaskResult

#     task_id = '1'
#     task_name = 'fake_task'

# class IngestTaskWatcherFactory(DjangoModelFactory):
#     class Meta:
#         model = IngestTaskWatcher

#     task_id = '1'
#     filename = Faker('file_path')
#     task_result = SubFactory(TaskResultFactory)
#     associated_manifest = SubFactory(ManifestFactory)
