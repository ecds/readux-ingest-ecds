import os
import logging
from mimetypes import guess_type
from django.core.files.base import ContentFile
from django.contrib import admin
from django.db import transaction
from django.shortcuts import redirect
from .models import Local, Bulk, S3Ingest, Remote
from .tasks import (
    local_ingest_task_ecds,
    bulk_ingest_task_ecds,
    s3_ingest_task,
    retry_local_from_s3_task,
    remote_task,
)
from .forms import BulkVolumeUploadForm

LOGGER = logging.getLogger(__name__)


class LocalAdmin(admin.ModelAdmin):
    """Django admin ingest.models.local resource."""

    list_display = ["manifest"]
    fields = (
        "bundle",
        "image_server",
        "collections",
        "manifest",
        "warnings",
        "prefix",
        "source_bucket",
    )
    readonly_fields = ("manifest", "warnings")
    show_save_and_add_another = False
    search_fields = ("manifest__pid", "manifest__label")

    def save_model(self, request, obj, form, change):
        is_adding = obj._state.adding
        LOGGER.info(f"INGEST: Local ingest started by {request.user.username}")
        obj.creator = request.user
        if is_adding or obj.from_s3 is False:
            obj.prep()
        super().save_model(request, obj, form, change)
        if os.environ["DJANGO_ENV"] != "test":  # pragma: no cover
            # Defer dispatch until the admin view's transaction actually
            # commits -- Django wraps the whole changeform view (including
            # this save_model call) in transaction.atomic(), so a worker
            # picking up the task immediately can otherwise query for this
            # row (or the manifest obj.prep() just created) before it's
            # visible outside this transaction.
            if is_adding or obj.from_s3 is False:
                transaction.on_commit(lambda: local_ingest_task_ecds.apply_async(args=[obj.id]))
            else:
                transaction.on_commit(lambda: retry_local_from_s3_task.apply_async(args=[obj.id]))
        else:
            local_ingest_task_ecds(obj.id)

    def response_add(self, request, obj, post_url_continue=None):
        obj.refresh_from_db()
        LOGGER.info(
            f"INGEST: Local ingest - {obj.id} - added for {str(obj.manifest.pid)}"
        )
        return redirect(f"/admin/manifests/manifest/{str(obj.manifest.pk)}/change/")

    class Meta:  # pylint: disable=missing-class-docstring
        model = Local


class BulkAdmin(admin.ModelAdmin):
    """Django admin ingest.models.bulk resource."""

    form = BulkVolumeUploadForm

    def save_model(self, request, obj, form, change):
        LOGGER.info(f"INGEST: Bulk ingest started by {request.user.username}")

        if form.is_valid():
            form.save(commit=False)
            form.save_m2m()
        obj.save()

        ingest_files = request.FILES.getlist("volume_files")[0]

        for ingest_file in ingest_files:
            if (
                "metadata" in ingest_file.name.casefold()
                and "zip" not in guess_type(ingest_file.name)[0]
            ):
                with ContentFile(ingest_file.read()) as file_content:
                    obj.metadata_file.save(ingest_file.name, file_content)
            else:
                local_ingest = Local.objects.create(
                    bulk=obj, image_server=obj.image_server, creator=request.user
                )

                local_ingest.collections.set(obj.collections.all())
                with ContentFile(ingest_file.read()) as file_content:
                    local_ingest.bundle.save(ingest_file.name, file_content)
                local_ingest.save()

        obj.creator = request.user
        super().save_model(request, obj, form, change)
        if os.environ["DJANGO_ENV"] != "test":  # pragma: no cover
            transaction.on_commit(lambda: bulk_ingest_task_ecds.apply_async(args=[obj.id]))
        else:
            bulk_ingest_task_ecds(obj.id)

    class Meta:
        model = Bulk


class S3IngestAdmin(admin.ModelAdmin):
    def save_model(self, request, obj, form, change):
        LOGGER.info(f"INGEST: S3 ingest started by {request.user.username}")
        obj.creator = request.user

        super().save_model(request, obj, form, change)
        if os.environ["DJANGO_ENV"] != "test":  # pragma: no cover
            transaction.on_commit(lambda: s3_ingest_task.apply_async(args=[obj.id]))
        else:
            s3_ingest_task(obj.id)

    class Meta:
        model = S3Ingest


class RemoteAdmin(admin.ModelAdmin):
    """Django admin ingest.models.remote resource."""

    list_display = ["manifest"]
    fields = (
        "link",
        "image_server",
        "manifest",
    )
    readonly_fields = ("manifest",)

    def save_model(self, request, obj, form, change):
        LOGGER.info(f"INGEST: Remote ingest started")
        obj.creator = request.user

        super().save_model(request, obj, form, change)
        if os.environ["DJANGO_ENV"] != "test":  # pragma: no cover
            transaction.on_commit(lambda: remote_task.apply_async(args=[obj.id]))
        else:
            remote_task(obj.id)

    class Meta:
        model = Remote


admin.site.register(Local, LocalAdmin)
admin.site.register(Bulk, BulkAdmin)
admin.site.register(S3Ingest, S3IngestAdmin)
admin.site.register(Remote, RemoteAdmin)
