import os
import logging
import uuid
from zipfile import ZipFile
from mimetypes import guess_type
from django.db import models
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.validators import FileExtensionValidator
from django.core.serializers import deserialize
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
from .services.iiif_services import (
    create_manifest,
    create_manifest_from_pid,
    find_language,
    manifest_from_manifest,
    canvas_from_manifest,
    ocr_from_annotation_page,
)
from .services.metadata_services import metadata_from_file, clean_metadata
from .helpers import get_iiif_models
from .storages import TmpStorage
from .mail import send_email_on_success, send_email_on_failure

Manifest = get_iiif_models()["Manifest"]
ImageServer = get_iiif_models()["ImageServer"]
Collection = get_iiif_models()["Collection"]
Canvas = get_iiif_models()["Canvas"]
OCR = get_iiif_models()["OCR"]

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
    warnings = models.CharField(blank=True, max_length=10000)
    prefix = models.CharField(
        null=True,
        blank=True,
        max_length=255,
        help_text="""Only from used when creating from S3Ingest.""",
    )
    from_s3 = models.BooleanField(
        default=False,
        help_text="""Only from used when creating from S3Ingest.""",
    )
    source_bucket = models.CharField(
        null=True,
        blank=True,
        max_length=255,
        help_text="""Only from used when creating from S3Ingest.""",
    )

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
            LOGGER.info(f"Creating canvas {image}")
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

            try:
                Canvas.objects.get(pid=canvas_pid)
            except Canvas.DoesNotExist:
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
        self.check_canvases()

        upload_trigger_file(self.trigger_file)

    def check_canvases(self):
        Canvas = get_iiif_models()["Canvas"]
        unique_canvas_pids = set()
        for canvas in self.manifest.canvas_set.all():
            unique_canvas_pids.add(canvas.pid)
        dupes = []
        for canvas_pid in list(unique_canvas_pids):
            canvases = list(Canvas.objects.filter(pid=canvas_pid))
            canvases.pop()
            dupes += canvases

        for dupe_canvas in dupes:
            dupe_canvas.delete()

        self.manifest.refresh_from_db()
        self.manifest.start_canvas = self.manifest.canvas_set.all()[0]
        self.manifest.save()
        return True

    def success(self):
        LOGGER.info(f"SUCCESS!!! {self.manifest.pid}")
        send_email_on_success(
            creator=self.creator, manifest=self.manifest, warnings=self.warnings
        )
        self.manifest.save()
        if os.environ["DJANGO_ENV"] != "test":
            from apps.iiif.manifests.documents import ManifestDocument

            index = ManifestDocument()
            index.update(self.manifest, True, "index")

    def failure(self, exc):
        LOGGER.info(f"FAIL!!! {self.manifest.pid}")
        send_email_on_failure(
            bundle=self.bundle.name,
            creator=self.creator,
            exception=str(exc),
            manifest=self.manifest,
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
    prefix = models.CharField(
        null=True,
        blank=True,
        max_length=255,
        help_text="""Optional: The name of a subdirectory in the bucket. This will limit where the ingest will look for files.""",
    )

    class Meta:
        verbose_name_plural = "S3 Ingests"

    def ingest(self):
        rows = metadata_from_file(self.metadata_spreadsheet.path)

        for row in rows:
            pid = row["pid"]
            if pid is None:
                continue
            LOGGER.info(f"Creating manifest {pid}")
            manifest = create_manifest_from_pid(pid, self.image_server)
            metadata = dict(row)
            for key, value in metadata.items():
                if key == "language":
                    manifest.languages.set(find_language(value))
                else:
                    setattr(manifest, key, value)

            manifest.collections.set(self.collections.all())
            manifest.save()
            local_ingest, created = Local.objects.get_or_create(
                manifest=manifest,
                image_server=self.image_server,
                creator=self.creator,
                from_s3=True,
                prefix=self.prefix,
                source_bucket=self.s3_bucket,
            )

            if created:
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

                image_files, _ = s3_copy(self.s3_bucket, pid, prefix=self.prefix)

                for image_file in image_files:
                    with open(trigger_file, "a", encoding="utf-8") as t_file:
                        t_file.write(f"{image_file}\n")

                from .tasks import add_canvases_task

                if os.environ["DJANGO_ENV"] == "test":
                    add_canvases_task(str(local_ingest.id), manifest.pid)
                else:
                    add_canvases_task.delay(str(local_ingest.id), manifest.pid)

            else:
                LOGGER.warning(f"Ingest for {manifest.pid} already exists.")

        self.delete()


class Remote(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    link = models.CharField(
        null=False,
        blank=False,
        max_length=500,
        help_text="""URL for remote IIIF manifest.""",
    )
    image_server = models.ForeignKey(
        ImageServer,
        on_delete=models.DO_NOTHING,
        null=True,
        related_name="ecds_remote_ingest_image_server",
    )

    def ingest(self):
        """
        Ingest from remote manifest.
        """
        Manifest = get_iiif_models()["Manifest"]
        Canvas = get_iiif_models()["Canvas"]
        OCR = get_iiif_models()["OCR"]
        new_canvases = []
        manifest_attrs, items = manifest_from_manifest(self.link)
        manifest = Manifest(**manifest_attrs)
        manifest.image_server = self.image_server
        manifest.save()
        for index, item in enumerate(items):
            canvas = None
            if item["type"] == "Canvas":
                canvas_attrs = canvas_from_manifest(item)
                canvas = Canvas(**canvas_attrs)
                canvas.position = index + 1
                canvas.manifest = manifest
                canvas.image_server = self.image_server
                new_canvases.append(canvas)
            if (
                canvas is not None
                and "annotations" in item.keys()
                and len(item["annotations"]) > 0
            ):
                for annos in item["annotations"]:
                    if annos["type"] == "AnnotationPage" and annos["id"].endswith(
                        "ocr"
                    ):
                        RemoteAnnotationPage.objects.create(
                            page=annos["id"], ingest=self
                        )

        if len(new_canvases) > 0:
            Canvas.objects.bulk_create(new_canvases)

        if self.remoteannotationpage_set.count() > 0:
            self.save()
            from .tasks import remote_ocr_task

            self.refresh_from_db()
            if os.environ["DJANGO_ENV"] == "test":
                remote_ocr_task(str(self.id))
            else:
                remote_ocr_task.delay(str(self.id))

    def add_ocr(self):
        OCR = get_iiif_models()["OCR"]
        new_ocr_annos = []
        for index, anno_page in enumerate(self.remoteannotationpage_set.all()):
            ocr_attrs = ocr_from_annotation_page(anno_page.page, index)
            for ocr_anno in ocr_attrs:
                ocr = OCR(**ocr_anno)
                new_ocr_annos.append(ocr)

        OCR.objects.bulk_create(new_ocr_annos)


class RemoteAnnotationPage(models.Model):
    page = models.CharField(
        null=False,
        blank=False,
        max_length=500,
        help_text="""URL for remote IIIF annotation page.""",
    )
    ingest = models.ForeignKey(Remote, on_delete=models.CASCADE)
