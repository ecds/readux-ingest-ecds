from django.db import models
from django_celery_results.models import TaskResult
from django.conf import settings
from .helpers import get_iiif_models

Manifest = get_iiif_models()['Manifest']

class IngestTaskWatcherManager(models.Manager):
    """ Manager class for associating user and ingest data with a task result """
    def create_watcher(self, filename, task_id, task_result, task_creator, associated_manifest=None):
        """
        Creates an instance of IngestTaskWatcher with provided params
        """
        watcher = self.create(
            filename=filename,
            task_id=task_id,
            task_result=task_result,
            task_creator=task_creator,
            associated_manifest=associated_manifest
        )
        return watcher


class IngestTaskWatcher(models.Model):
    """ Model class for associating user and ingest data with a task result """
    filename = models.CharField(max_length=255, null=True)
    task_id = models.CharField(max_length=255, null=True)
    task_result = models.ForeignKey(TaskResult, on_delete=models.CASCADE, null=True)
    task_creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        related_name='created_tasks'
    )
    associated_manifest = models.ForeignKey(Manifest, on_delete=models.SET_NULL, null=True)
    manager = IngestTaskWatcherManager()

    class Meta:
        verbose_name_plural = 'Ingest Statuses'

