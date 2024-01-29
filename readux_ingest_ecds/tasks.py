# pylint: disable = unused-argument

""" Common tasks for ingest. """
import os
from celery import Celery
from django.apps import apps
from django.conf import settings
from .helpers import get_iiif_models
from .services.ocr_services import get_ocr, add_ocr_annotations

# Use `apps.get_model` to avoid circular import error. Because the parameters used to
# create a background task have to be serializable, we can't just pass in the model object.
Local = apps.get_model('readux_ingest_ecds.local') # pylint: disable = invalid-name

Manifest = get_iiif_models()['Manifest']
Canvas = get_iiif_models()['Canvas']
OCR = get_iiif_models()['OCR']

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
    if os.environ["DJANGO_ENV"] != 'test': # pragma: no cover
        add_ocr_task.delay(local_ingest.manifest.pk)
    else:
        add_ocr_task(local_ingest.manifest.pk)


@app.task(name='adding_ocr_to_canvas', autoretry_for=(Manifest.DoesNotExist,), retry_backoff=5)
def add_ocr_task(manifest_id, *args, **kwargs):
    """Function for parsing and adding OCR."""
    manifest = Manifest.objects.get(pk=manifest_id)
    for canvas in manifest.canvas_set.all():
        ocr = get_ocr(canvas)
        if ocr is not None:
            add_ocr_annotations(canvas, ocr)
            # The add_ocr_annotations method uses bulk_create() which does not call save() on the model.
            # Calling save() is really slow and I don't know why. Calling save() after the annotation
            # has been created, calling save is as fast as expected.
            [ocr.save() for ocr in OCR.objects.filter(canvas=canvas)]
            canvas.save()  # trigger reindex
