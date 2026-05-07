# pylint: disable = unused-argument

"""Common tasks for ingest."""

import os
import logging
from celery import Celery, Task
from django.apps import apps
from django.conf import settings
from .helpers import get_iiif_models
from .services.ocr_services import (
    add_ocr_to_canvases,
    add_ocr_to_canvas,
    remove_duplicate_ocr,
)
from .services.file_services import s3_copy

# Use `apps.get_model` to avoid circular import error. Because the parameters used to
# create a background task have to be serializable, we can't just pass in the model object.
Local = apps.get_model("readux_ingest_ecds.local")  # pylint: disable = invalid-name
Bulk = apps.get_model("readux_ingest_ecds.bulk")  # pylint: disable = invalid-name
Remote = apps.get_model("readux_ingest_ecds.remote")  # pylint: disable = invalid-name
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


class FinalRemoteTask(Task):
    def on_success(self, retval, task_id, args, kwargs):
        """Same as FinalTask"""
        ingest = Remote.objects.get(id=args[0])
        ingest.success()

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Same as FinalTask"""
        ingest = Remote.objects.get(id=args[0])
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
        add_ocr_task_local.delay(ingest_id, local_ingest.manifest.pid)
    else:
        add_ocr_task_local(ingest_id, local_ingest.manifest.pid)


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
    name="add_canvases_task",
    autoretry_for=(Exception,),
    retry_backoff=5,
)
def add_canvases_task(ingest_id, manifest_pid, *args, **kwargs):
    """Function to create canvases

    Args:
        ingest_id (string): ID for Local Ingest Object
        manifest_pid (string): PID of Manifest being ingested
    """
    LOGGER.info(f"Adding Canvases for {manifest_pid}")
    local_ingest = Local.objects.get(pk=ingest_id)
    local_ingest.create_canvases()
    LOGGER.info(f"Canvases created for {manifest_pid}")
    local_ingest.manifest.save()

    if os.environ["DJANGO_ENV"] == "test":
        add_ocr_task_local(str(local_ingest.id), manifest_pid)
    else:
        add_ocr_task_local.delay(str(local_ingest.id), manifest_pid)


@app.task(
    name="add_ocr_task_local_ecds",
    base=FinalTask,
    autoretry_for=(Manifest.DoesNotExist,),
    retry_backoff=5,
)
def add_ocr_task_local(ingest_id, manifest_pid, *args, **kwargs):
    """Function for parsing and adding OCR."""
    LOGGER.info(f"ADDING OCR for {manifest_pid}")
    local_ingest = Local.objects.get(pk=ingest_id)
    manifest = Manifest.objects.get(pk=local_ingest.manifest.pk)
    warnings = add_ocr_to_canvases(manifest)
    local_ingest.warnings = " | ".join(warnings)
    local_ingest.save()


@app.task(
    name="nuke_dupe_ocr_task",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=5,
)
def nuke_dupe_ocr_task(manifest_pid, *args, **kwargs):
    """Desperate effort to remove duplicate OCR"""
    manifest = Manifest.objects.get(pid=manifest_pid)
    for canvas in manifest.canvas_set.all():
        remove_duplicate_ocr(canvas)


@app.task(
    name="s3_ingest_task_ecds",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=20,
)
def s3_ingest_task(ingest_id, *args, **kwargs):
    """S3 Ingest Task"""
    LOGGER.info("Starting ingest from S3")
    s3_ingest = S3Ingest.objects.get(pk=ingest_id)
    s3_ingest.ingest()


@app.task(
    name="add_volume_ocr_manage_task",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=20,
)
def add_ocr_manage_task(volume_pid, *args, **kwargs):
    """Add OCR for Volume/Manifest via Manage Command"""
    manifest = Manifest.objects.get(pid=volume_pid)
    add_ocr_to_canvases(manifest)


@app.task(
    name="add_canvas_ocr_manage_task",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=20,
)
def add_ocr_to_canvas_task(canvas_pid, *args, **kwargs):
    """Add OCR for Volume/Manifest via Manage Command"""
    add_ocr_to_canvas(canvas_pid)


@app.task(
    name="retry_local_from_s3_task",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=20,
)
def retry_local_from_s3_task(ingest_id, *args, **kwargs):
    """Add OCR for Volume/Manifest via Manage Command"""
    ingest = Local.objects.get(id=ingest_id)

    # Create or clear the trigger file
    open(ingest.trigger_file, "w", encoding="utf-8").close()

    image_files, _ = s3_copy(
        ingest.source_bucket, ingest.manifest.pid, prefix=ingest.prefix
    )

    for image_file in image_files:
        with open(ingest.trigger_file, "a", encoding="utf-8") as t_file:
            t_file.write(f"{image_file}\n")

    add_canvases_task.delay(str(ingest.id), ingest.manifest.pid)


@app.task(
    name="remote_task",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=20,
)
def remote_task(ingest_id, *args, **kwargs):
    """Task for remote ingest."""
    ingest = Remote.objects.get(id=ingest_id)
    ingest.ingest()


@app.task(
    name="remote_ocr_task",
    base=FinalRemoteTask,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=20,
)
def remote_ocr_task(ingest_id, *args, **kwargs):
    """Task for remote ingest."""
    ingest = Remote.objects.get(id=ingest_id)
    ingest.add_ocr()
    ingest.set_ocr_span_elements()
