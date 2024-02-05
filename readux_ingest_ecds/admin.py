import os
import logging
from django.contrib import admin
from django.shortcuts import redirect
from .models import Local, Bulk
from .tasks import local_ingest_task_ecds, bulk_ingest_task_ecds
from .forms import BulkVolumeUploadForm

LOGGER = logging.getLogger(__name__)

class LocalAdmin(admin.ModelAdmin):
    """Django admin ingest.models.local resource."""
    fields = ('bundle', 'image_server', 'collections')
    show_save_and_add_another = False

    def save_model(self, request, obj, form, change):
        LOGGER.info(f'INGEST: Local ingest started by {request.user.username}')
        obj.creator = request.user
        obj.prep()
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

class BulkAdmin(admin.ModelAdmin):
    form = BulkVolumeUploadForm

    def save_model(self, request, obj, form, change):
        LOGGER.info(f'INGEST: Bulk ingest started by {request.user.username}')
        obj.upload_files(request.FILES.getlist('volume_files')[0])
        obj.creator = request.user
        super().save_model(request, obj, form, change)
        if os.environ["DJANGO_ENV"] != 'test': # pragma: no cover
            bulk_ingest_task_ecds.apply_async(args=[obj.id])
        else:
            bulk_ingest_task_ecds(obj.id)

    class Meta:
        model = Bulk

admin.site.register(Local, LocalAdmin)
admin.site.register(Bulk, BulkAdmin)