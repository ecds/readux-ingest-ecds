import os
import logging
from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.shortcuts import redirect
from django_celery_results.models import TaskResult
from .models import Local
from .tasks import local_ingest_task

LOGGER = logging.getLogger(__name__)

class LocalAdmin(admin.ModelAdmin):
    """Django admin ingest.models.local resource."""
    fields = ('bundle', 'image_server', 'collections')
    show_save_and_add_another = False

    def save_model(self, request, obj, form, change):
        LOGGER.info(f'INGEST: Local ingest - {obj.id} - started by {request.user.username}')
        obj.creator = request.user
        super().save_model(request, obj, form, change)
        if os.environ["DJANGO_ENV"] != 'test': # pragma: no cover
            local_ingest_task.apply_async(args=[obj.id])
        else:
            local_ingest_task(obj.id)

    def response_add(self, request, obj, post_url_continue=None):
        obj.refresh_from_db()
        manifest_id = obj.manifest.id
        return redirect('/admin/manifests/manifest/{m}/change/'.format(m=manifest_id))

    class Meta: # pylint: disable=too-few-public-methods, missing-class-docstring
        model = Local

admin.site.register(Local, LocalAdmin)
