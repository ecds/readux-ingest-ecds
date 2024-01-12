# pylint: disable = unused-argument

""" Common tasks for ingest. """
from celery import Celery
from django.apps import apps
from django.conf import settings
from .helpers import get_iiif_models

# Use `apps.get_model` to avoid circular import error. Because the parameters used to
# create a background task have to be serializable, we can't just pass in the model object.
Local = apps.get_model('readux_ingest_ecds.local') # pylint: disable = invalid-name
# Remote = apps.get_model('ingest.remote')
# S3Ingest = apps.get_model('ingest.S3Ingest')
Manifest = get_iiif_models()['Manifest']

Canvas = get_iiif_models()['Canvas']

app = Celery('readux_ingest_ecds', result_extended=True)
app.config_from_object('django.conf:settings')
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)

@app.task(name='local_ingest_task_ecds', autoretry_for=(Exception,), retry_backoff=True, max_retries=20)
def local_ingest_task_ecds(ingest_id):
    """Background task to start ingest process.

    :param ingest_id: Primary key for .models.Local object
    :type ingest_id: UUID

    """
    local_ingest = Local.objects.get(pk=ingest_id)
    local_ingest.ingest()
