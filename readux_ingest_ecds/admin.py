import os
import logging
from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.shortcuts import redirect
from django_celery_results.models import TaskResult
from .models import Local
from .tasks import local_ingest_task_ecds

LOGGER = logging.getLogger(__name__)

class LocalAdmin(admin.ModelAdmin):
    """Django admin ingest.models.local resource."""
    fields = ('bundle', 'image_server', 'collections')
    show_save_and_add_another = False

    def save_model(self, request, obj, form, change):
        LOGGER.info(f'INGEST: Local ingest started by {request.user.username}')
        obj.creator = request.user
        obj.process()
        super().save_model(request, obj, form, change)
        if os.environ["DJANGO_ENV"] != 'test': # pragma: no cover
            local_ingest_task_ecds.apply_async(args=[obj.id])
        else:
            local_ingest_task_ecds(obj.id)

    def response_add(self, request, obj, post_url_continue=None):
        obj.refresh_from_db()
        LOGGER.info(f'INGEST: Local ingest - {obj.id} - added for {obj.manifest.pid}')
        return redirect('/admin/manifests/manifest/{m}/change/'.format(m=obj.manifest.pk))

    class Meta: # pylint: disable=too-few-public-methods, missing-class-docstring
        model = Local

admin.site.register(Local, LocalAdmin)
