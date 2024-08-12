import os
import logging
import uuid
from zipfile import ZipFile
from mimetypes import guess_type
from django.db import models
from django.conf import settings
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.core.files.storage import FileSystemStorage
from django.core.files.base import ContentFile
from django.core.validators import FileExtensionValidator
from .services.file_services import (
    is_image,
    is_ocr,
    is_junk,
    move_image_file,
    move_ocr_file,
    canvas_dimensions,
    upload_trigger_file,
    s3_copy,
)
from .services.iiif_services import create_manifest, create_manifest_from_pid
from .services.metadata_services import metadata_from_file, clean_metadata
from .helpers import get_iiif_models
from .storages import TmpStorage
from .mail import send_email_on_success, send_email_on_failure

Manifest = get_iiif_models()["Manifest"]
ImageServer = get_iiif_models()["ImageServer"]
Collection = get_iiif_models()["Collection"]

LOGGER = logging.getLogger(__name__)


def bulk_path(instance, filename):
    """
    Make directories and path for Bulk upload
    :param instance: Bulk instance
    :type instance: Bulk
    :param filename: File being uploaded
    :type filename: str
    :return: Destination path for file upload
    :rtype: str
    """
    os.makedirs(os.path.join(settings.INGEST_TMP_DIR, str(instance.id)), exist_ok=True)
    return os.path.join(str(instance.id), filename)


def local_tmp(instance, filename):
    """
    Make directories and path for Local upload
    :param instance: Local instance
    :type instance: Local
    :param filename: File being uploaded
    :type filename: str
    :return: Destination path for file upload
    :rtype: str
    """
    os.makedirs(os.path.join(settings.INGEST_TMP_DIR, str(instance.id)), exist_ok=True)
    return os.path.join(str(instance.id), filename)


class IngestAbstractModel(models.Model):
    """Base model class for ingest"""

    metadata = models.JSONField(default=dict, blank=True)
    manifest = models.ForeignKey(
        Manifest,
        on_delete=models.DO_NOTHING,
        null=True,
        related_name="ecds_ingest_manifest",
    )
    image_server = models.ForeignKey(
        ImageServer,
        on_delete=models.DO_NOTHING,
        null=True,
        related_name="ecds_ingest_image_server",
    )
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="ecds_ingest_created_locals",
    )
    collections = models.ManyToManyField(
        Collection,
        blank=True,
        help_text="Optional: Collections to attach to the volume ingested in this form.",
        related_name="ecds_ingest_collections",
    )
    bulk = models.ForeignKey("Bulk", on_delete=models.CASCADE, null=True)

    class Meta:  # pylint: disable=too-few-public-methods, missing-class-docstring
        abstract = True


class Local(IngestAbstractModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bundle = models.FileField(
        null=True, blank=True, storage=TmpStorage, upload_to=local_tmp
    )

    bundle_path = models.CharField(blank=True, max_length=1000)

    class Meta:
        verbose_name_plural = "Local"

    @property
    def tmp_directory(self):
        return os.path.join(
            settings.INGEST_TMP_DIR,
            str(self.id),
        )

    @property
    def ocr_directory(self):
        target_directory = os.path.join(settings.INGEST_OCR_DIR, self.manifest.pid)
        os.makedirs(target_directory, exist_ok=True)
        return target_directory

    @property
    def trigger_file(self):
        return os.path.join(
            settings.INGEST_TMP_DIR, str(self.id), f"{self.manifest.pid}.txt"
        )

    def prep(self):
        """
        Open metadata
        Create manifest
        Unzip bundle
        """
        LOGGER.info(f"INGEST: Local ingest - preparing new local ingest!!!!")
        os.makedirs(os.path.join(settings.INGEST_TMP_DIR, str(self.id)), exist_ok=True)
        os.makedirs(settings.INGEST_PROCESSING_DIR, exist_ok=True)
        os.makedirs(settings.INGEST_OCR_DIR, exist_ok=True)
        self.save()
        self.open_metadata()
        self.manifest = create_manifest(self)
        self.save()

    def ingest(self):
        LOGGER.info(f"INGEST: Local ingest - {self.id} - saved for {self.manifest.pid}")
        self.unzip_bundle()
        self.create_canvases()
        LOGGER.info(
            f"INGEST: Local ingest - {self.id} - finished for {self.manifest.pid}"
        )

    def unzip_bundle(self):
        open(self.trigger_file, "a", encoding="utf-8").close()

        bundle_to_unzip = self.bundle_path if self.bundle_path else self.bundle

        with ZipFile(bundle_to_unzip, "r") as zip_ref:
            for member in zip_ref.infolist():
                file_name = member.filename

                if is_junk(os.path.basename(file_name)):
                    continue

                file_path = os.path.join(self.tmp_directory, file_name)

                if is_image(file_name):
                    zip_ref.extract(
                        member=member, path=os.path.join(self.tmp_directory)
                    )

                    file_to_process = move_image_file(self, file_path)
                    with open(self.trigger_file, "a", encoding="utf-8") as t_file:
                        t_file.write(f"{file_to_process}\n")

                elif is_ocr(file_name):
                    zip_ref.extract(member=member, path=self.tmp_directory)

                    move_ocr_file(self, file_path)

    def open_metadata(self):
        if bool(self.metadata):
            self.metadata = clean_metadata(self.metadata)
            return

        metadata_file = None

        with ZipFile(self.bundle, "r") as zip_ref:
            for member in zip_ref.infolist():
                file_name = member.filename

                if is_junk(os.path.basename(file_name)):
                    continue

                if is_image(file_name):
                    continue

                if os.path.splitext(os.path.basename(file_name))[0] == "metadata":
                    metadata_file = os.path.join(self.tmp_directory, file_name)
                    zip_ref.extract(member=member, path=self.tmp_directory)

        if metadata_file is None or os.path.exists(metadata_file) is False:
            return

        self.metadata = metadata_from_file(metadata_file)[0]

    def create_canvases(self):
        Canvas = get_iiif_models()["Canvas"]
        new_canvases = []
        images = None
        with open(self.trigger_file, "r") as t_file:
            images = t_file.read().splitlines()
        images.sort()

        for index, image in enumerate(images):
            position = index + 1
            image_name = os.path.splitext(image)[0]
            canvas_pid = f"{image_name}.tiff"
            width, height = canvas_dimensions(image_name)
            ocr_directory = os.path.join(settings.INGEST_OCR_DIR, self.manifest.pid)
            try:
                ocr_file = [
                    ocr for ocr in os.listdir(ocr_directory) if image_name in ocr
                ][0]
                ocr_file_path = os.path.abspath(os.path.join(ocr_directory, ocr_file))
            except IndexError:
                ocr_file_path = None

            new_canvas = Canvas(
                manifest=self.manifest,
                image_server=self.image_server,
                pid=canvas_pid,
                ocr_file_path=ocr_file_path,
                position=position,
                width=width,
                height=height,
                resource=canvas_pid,
            )

            new_canvas.before_save()

            new_canvases.append(new_canvas)

        Canvas.objects.bulk_create(new_canvases)

        upload_trigger_file(self.trigger_file)

    def success(self):
        LOGGER.info(f"SUCCESS!!! {self.manifest.pid}")
        send_email_on_success(creator=self.creator, manifest=self.manifest)
        self.manifest.save()
        if os.environ["DJANGO_ENV"] != "test":
            from apps.iiif.manifests.documents import ManifestDocument

            index = ManifestDocument()
            index.update(self.manifest, True, "index")
        self.delete()

    def failure(self, exc):
        LOGGER.info(f"FAIL!!! {self.manifest.pid}")
        send_email_on_failure(
            bundle=self.bundle.name, creator=self.creator, exception=str(exc)
        )
        self.delete()


class Bulk(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    collections = models.ManyToManyField(
        Collection,
        blank=True,
        help_text="Optional: Collections to attach to the volume ingested in this form.",
        related_name="ecds_bulk_ingest_collections",
    )
    image_server = models.ForeignKey(
        ImageServer,
        on_delete=models.DO_NOTHING,
        null=True,
        related_name="ecds_bulk_ingest_image_server",
    )
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="ecds_bulk_ingest_created_locals",
    )
    volume_files = models.FileField(
        blank=False, null=True, upload_to=bulk_path, storage=TmpStorage
    )
    metadata_file = models.FileField(
        blank=False, null=True, upload_to=bulk_path, storage=TmpStorage
    )

    def upload_files(self, files, creator):
        """_summary_

        :param files: _description_
        :type files: _type_
        """
        # if isinstance(files, InMemoryUploadedFile):
        #     FileSystemStorage(
        #         location=os.path.join(settings.INGEST_TMP_DIR, str(self.id))
        #     ).save(files.name, files)
        # else:
        #     for uploaded_file in files:
        #         with open(
        #             os.path.join(
        #                 settings.INGEST_TMP_DIR, bulk_path(self, uploaded_file.name)
        #             ),
        #             "wb",
        #         ) as out_file:
        #             out_file.write(uploaded_file.read())
        for uploaded_file in files:
            if (
                "metadata" in uploaded_file.name.casefold()
                and "zip" not in guess_type(uploaded_file.name)[0]
            ):
                with ContentFile(uploaded_file.read()) as file_content:
                    self.metadata_file.save(uploaded_file.name, file_content)
            else:
                local_ingest = Local.objects.create(
                    bulk=self, image_server=self.image_server, creator=creator
                )

                local_ingest.collections.set(self.collections.all())
                with ContentFile(uploaded_file.read()) as file_content:
                    local_ingest.bundle.save(uploaded_file.name, file_content)
                local_ingest.save()

    class Meta:
        """Model Meta"""

        verbose_name_plural = "Bulk"

    def ingest(self):
        """Doc"""
        LOGGER.info("Ingesting Bulk")
        metadata = metadata_from_file(
            os.path.join(
                settings.INGEST_TMP_DIR,
                self.metadata_file.name,
            )
        )

        for index, volume in enumerate(metadata):
            for local_ingest in self.local_set.all():
                if volume["filename"] in str(local_ingest.bundle):
                    local_ingest.metadata = metadata[index]
                    local_ingest.save()
                    local_ingest.prep()
                    local_ingest.ingest()

        # ingest_directory = os.path.join(settings.INGEST_TMP_DIR, str(self.id))
        # ingest_files = os.listdir(ingest_directory)
        # for uploaded_file in ingest_files:
        #     if os.path.splitext(os.path.basename(uploaded_file))[0] == "metadata":
        #         metadata = metadata_from_file(
        #             os.path.join(ingest_directory, uploaded_file)
        #         )
        # for volume in metadata:
        #     bundle_filename = [
        #         d["value"]
        #         for d in volume["metadata"]
        #         if d["label"].casefold() == "filename"
        #     ][0]
        #     bundle = os.path.join(
        #         settings.INGEST_TMP_DIR, str(self.id), bundle_filename
        #     )
        #     if os.path.exists(bundle) and bundle.endswith(".zip"):
        #         local = Local.objects.create(
        #             metadata=volume,
        #             bundle_path=bundle,
        #             image_server=self.image_server,
        #             creator=self.creator,
        #         )
        #         local.prep()
        #         local.ingest()
        # self.delete()


class S3Ingest(models.Model):
    """Model class for bulk ingesting volumes from an Amazon AWS S3 bucket."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    s3_bucket = models.CharField(
        null=False,
        blank=False,
        max_length=255,
        help_text="""The name of a publicly-accessible S3 bucket containing volumes to
        ingest, either at the bucket root or within subfolder(s). Each volume should have its own
        subfolder, with the volume's PID as its name.
        <br />
        <strong>Example:</strong> if the bucket's URL is
        https://my-bucket.s3.us-east-1.amazonaws.com/, its name is <strong>my-bucket</strong>.""",
    )
    metadata_spreadsheet = models.FileField(
        null=False,
        blank=False,
        help_text="""A spreadsheet file with a row for each volume, including the
        volume PID (column name <strong>pid</strong>).""",
        validators=[FileExtensionValidator(allowed_extensions=["csv", "xlsx"])],
    )
    image_server = models.ForeignKey(
        ImageServer,
        on_delete=models.DO_NOTHING,
        null=True,
        related_name="ecds_s3_ingest_image_server",
    )
    collections = models.ManyToManyField(
        Collection,
        blank=True,
        help_text="Optional: Collections to attach to ALL volumes ingested in this form.",
    )
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="ecds_ingest_created_s3",
    )

    class Meta:
        verbose_name_plural = "Amazon S3 Ingests"

    def ingest(self):
        rows = metadata_from_file(self.metadata_spreadsheet.path)

        for row in rows:
            pid = row["pid"]
            manifest = create_manifest_from_pid(pid, self.image_server)
            metadata = dict(row)
            for key, value in metadata.items():
                setattr(manifest, key, value)

            manifest.collections.set(self.collections.all())
            manifest.save()
            local_ingest = Local.objects.create(
                manifest=manifest, image_server=self.image_server, creator=self.creator
            )

            trigger_file = os.path.join(
                settings.INGEST_TMP_DIR, str(local_ingest.id), f"{pid}.txt"
            )

            os.makedirs(
                os.path.join(settings.INGEST_TMP_DIR, str(local_ingest.id)),
                exist_ok=True,
            )

            os.makedirs(
                os.path.join(settings.INGEST_OCR_DIR, str(pid)),
                exist_ok=True,
            )

            open(trigger_file, "a", encoding="utf-8").close()

            image_files, _ = s3_copy(self.s3_bucket, pid)

            for image_file in image_files:
                with open(trigger_file, "a", encoding="utf-8") as t_file:
                    t_file.write(f"{image_file}\n")

            local_ingest.create_canvases()
            manifest.save()
            from .tasks import add_ocr_task_local

            if os.environ["DJANGO_ENV"] == "test":
                add_ocr_task_local(str(local_ingest.id))
            else:
                add_ocr_task_local.delay(str(local_ingest.id))

        self.delete()
