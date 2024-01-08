import os
from django.contrib import admin
from django.shortcuts import redirect
from django_celery_results.models import TaskResult
from .task_utils import IngestTaskWatcher
from .models import Local
from .services import create_manifest
from .tasks import create_canvas_form_local_task, create_canvas_form_local_task

class LocalAdmin(admin.ModelAdmin):
    """Django admin ingest.models.local resource."""
    fields = ('bundle', 'image_server', 'collections')
    show_save_and_add_another = False

    def save_model(self, request, obj, form, change):
        obj.save()
        obj.process()
        obj.creator = request.user
        obj.save()
        obj.refresh_from_db()
        super().save_model(request, obj, form, change)
        if os.environ["DJANGO_ENV"] != 'test': # pragma: no cover
            local_task_id = create_canvas_form_local_task.apply_async(args=[obj.id])
            local_task_result = TaskResult(task_id=local_task_id)
            local_task_result.save()
            file = request.FILES['bundle']
            IngestTaskWatcher.manager.create_watcher(
                task_id=local_task_id,
                task_result=local_task_result,
                task_creator=request.user,
                associated_manifest=obj.manifest,
                filename=file.name
            )
        else:
            create_canvas_form_local_task(obj.id)

    def response_add(self, request, obj, post_url_continue=None):
        obj.refresh_from_db()
        manifest_id = obj.manifest.id
        return redirect('/admin/manifests/manifest/{m}/change/'.format(m=manifest_id))

    class Meta: # pylint: disable=too-few-public-methods, missing-class-docstring
        model = Local
