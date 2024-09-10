# pylint: disable = unused-argument

""" Common tasks for ingest. """
import os
import logging
from celery import Celery, Task
from django.apps import apps
from django.conf import settings
from .helpers import get_iiif_models
from .services.ocr_services import add_ocr_to_canvases
from .mail import send_email_on_success, send_email_on_failure

# Use `apps.get_model` to avoid circular import error. Because the parameters used to
# create a background task have to be serializable, we can't just pass in the model object.
Local = apps.get_model("readux_ingest_ecds.local")  # pylint: disable = invalid-name
Bulk = apps.get_model("readux_ingest_ecds.bulk")  # pylint: disable = invalid-name
S3Ingest = apps.get_model(
    "readux_ingest_ecds.s3ingest"
)  # pylint: disable = invalid-name

Manifest = get_iiif_models()["Manifest"]
Canvas = get_iiif_models()["Canvas"]
OCR = get_iiif_models()["OCR"]

LOGGER = logging.getLogger(__name__)


class FinalTask(Task):
    def on_success(self, retval, task_id, args, kwargs):
        """Success handler.

        Run by the worker if the task executes successfully.

        Arguments:
            retval (Any): The return value of the task.
            task_id (str): Unique id of the executed task.
            args (Tuple): Original arguments for the executed task.
            kwargs (Dict): Original keyword arguments for the executed task.

        Returns:
            None: The return value of this handler is ignored.
        """
        ingest = Local.objects.get(id=args[0])
        ingest.success()

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Error handler.

        This is run by the worker when the task fails.

        Arguments:
            exc (Exception): The exception raised by the task.
            task_id (str): Unique id of the failed task.
            args (Tuple): Original arguments for the task that failed.
            kwargs (Dict): Original keyword arguments for the task that failed.
            einfo (~billiard.einfo.ExceptionInfo): Exception information.

        Returns:
            None: The return value of this handler is ignored.
        """
        ingest = Local.objects.get(id=args[0])
        ingest.failure(exc)


app = Celery("readux_ingest_ecds", result_extended=True)
app.config_from_object("django.conf:settings")
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)


@app.task(
    name="local_ingest_task_ecds",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=20,
)
def local_ingest_task_ecds(ingest_id):
    """Background task to start ingest process.

    :param ingest_id: Primary key for .models.Local object
    :type ingest_id: UUID

    """
    local_ingest = Local.objects.get(pk=ingest_id)
    local_ingest.ingest()
    if os.environ["DJANGO_ENV"] != "test":  # pragma: no cover
        add_ocr_task_local.delay(ingest_id)
    else:
        add_ocr_task_local(ingest_id)


@app.task(
    name="bulk_ingest_task_ecds",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=20,
)
def bulk_ingest_task_ecds(ingest_id):
    """Background task to start ingest process.

    :param ingest_id: Primary key for .models.Local object
    :type ingest_id: UUID

    """
    bulk_ingest = Bulk.objects.get(pk=ingest_id)
    bulk_ingest.ingest()


@app.task(
    name="add_ocr_task_local_ecds",
    base=FinalTask,
    autoretry_for=(Manifest.DoesNotExist,),
    retry_backoff=5,
)
def add_ocr_task_local(ingest_id, *args, **kwargs):
    """Function for parsing and adding OCR."""
    LOGGER.info("ADDING OCR")
    local_ingest = Local.objects.get(pk=ingest_id)
    manifest = Manifest.objects.get(pk=local_ingest.manifest.pk)
    warnings = add_ocr_to_canvases(manifest)
    local_ingest.warnings = "\n".join(warnings)
    local_ingest.save()


@app.task(
    name="s3_ingest_task_ecds",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=20,
)
def s3_ingest_task(ingest_id, *args, **kwargs):
    """S3 Ingest Task"""
    LOGGER.info("Starting ingest from S3")
    print(ingest_id)
    s3_ingest = S3Ingest.objects.get(pk=ingest_id)
    s3_ingest.ingest()
