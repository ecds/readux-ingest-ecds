import os
import logging
from zipfile import ZipFile
from django.core.files.storage import FileSystemStorage
from django.db import models
from django.conf import settings
from .services import is_image, is_ocr, is_junk, metadata_from_file, create_manifest, move_image_file, move_ocr_file, canvas_dimensions, upload_trigger_file
from .helpers import get_iiif_models

Manifest = get_iiif_models()['Manifest']
ImageServer = get_iiif_models()['ImageServer']
Collection = get_iiif_models()['Collection']

LOGGER = logging.getLogger(__name__)

tmp_storage = FileSystemStorage(
    location=settings.INGEST_TMP_DIR
)

class IngestAbstractModel(models.Model):
    metadata = models.JSONField(default=dict, blank=True)
    manifest = models.ForeignKey(
        Manifest,
        on_delete=models.DO_NOTHING,
        null=True,
        related_name='ecds_ingest_manifest'
    )
    image_server = models.ForeignKey(
        ImageServer,
        on_delete=models.DO_NOTHING,
        null=True,
        related_name='ecds_ingest_image_server'
    )
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='ecds_ingest_created_locals'
    )
    collections = models.ManyToManyField(
        Collection,
        blank=True,
        help_text="Optional: Collections to attach to the volume ingested in this form.",
        related_name='ecds_ingest_collections'
    )

    class Meta: # pylint: disable=too-few-public-methods, missing-class-docstring
        abstract = True

class Local(IngestAbstractModel):
    bundle = models.FileField(
        null=True,
        blank=True,
        storage=tmp_storage
    )

    class Meta:
        verbose_name_plural = 'Local'

    @property
    def tmp_directory(self):
        return os.path.join(
            settings.INGEST_TMP_DIR,
            self.manifest.pid
        )

    @property
    def ocr_directory(self):
        target_directory = os.path.join(settings.INGEST_OCR_DIR, self.manifest.pid)
        os.makedirs(target_directory, exist_ok=True)
        return target_directory

    @property
    def trigger_file(self):
        return os.path.join(settings.INGEST_TMP_DIR, f'{self.manifest.pid}.txt')

    def process(self):
        """
        Open metadata
        Create manifest
        Unzip bundle
        """
        os.makedirs(settings.INGEST_TMP_DIR, exist_ok=True)
        os.makedirs(settings.INGEST_PROCESSING_DIR, exist_ok=True)
        os.makedirs(settings.INGEST_OCR_DIR, exist_ok=True)
        self.save()
        self.open_metadata()
        self.manifest = create_manifest(self)
        self.save()

    def ingest(self):
        LOGGER.info(f'INGEST: Local ingest - {self.id} - saved for {self.manifest.pid}')
        self.unzip_bundle()
        self.create_canvases()
        LOGGER.info(f'INGEST: Local ingest - {self.id} - finished for {self.manifest.pid}')
        self.delete()

    def unzip_bundle(self):
        open(self.trigger_file, 'a').close()

        with ZipFile(self.bundle, 'r') as zip_ref:
            for member in zip_ref.infolist():
                file_name = member.filename

                if is_junk(os.path.basename(file_name)):
                    continue

                file_path = os.path.join(
                    settings.INGEST_TMP_DIR,
                    file_name
                )

                if is_image(file_name):
                    zip_ref.extract(
                        member=member,
                        path=settings.INGEST_TMP_DIR
                    )

                    file_to_process = move_image_file(self, file_path)
                    with open(self.trigger_file, 'a') as t_file:
                        t_file.write(f'{file_to_process}\n')

                elif is_ocr(file_name):
                    zip_ref.extract(
                        member=member,
                        path=settings.INGEST_TMP_DIR
                    )

                    move_ocr_file(self, file_path)

    def open_metadata(self):
        if bool(self.metadata):
            return

        metadata_file = None

        with ZipFile(self.bundle, 'r') as zip_ref:
            for member in zip_ref.infolist():
                file_name = member.filename

                if is_junk(os.path.basename(file_name)):
                    continue

                if is_image(file_name):
                    continue

                if os.path.splitext(os.path.basename(file_name))[0] == 'metadata':
                    metadata_file = os.path.join(
                        settings.INGEST_TMP_DIR,
                        file_name
                    )
                    zip_ref.extract(
                        member=member,
                        path=settings.INGEST_TMP_DIR
                    )

        if metadata_file is None or os.path.exists(metadata_file) is False:
            return

        self.metadata = metadata_from_file(metadata_file)

    def create_canvases(self):
        Canvas = get_iiif_models()['Canvas']
        images = None
        with open(self.trigger_file, 'r') as t_file:
            images =t_file.read().splitlines()
        images.sort()

        for index, image in enumerate(images):
            position = index + 1
            image_name = os.path.splitext(image)[0]
            canvas_pid = f'{image_name}.tiff'
            width, height = canvas_dimensions(image_name)
            try:
                ocr_file = [ocr for ocr in os.listdir(settings.INGEST_OCR_DIR) if image_name in ocr][0]
                ocr_file_path = os.path.abspath(os.path.join(settings.INGEST_OCR_DIR, ocr_file))
            except IndexError:
                ocr_file_path = None

            Canvas.objects.get_or_create(
                manifest=self.manifest,
                pid=canvas_pid,
                ocr_file_path=ocr_file_path,
                position=position,
                width=width,
                height=height
            )

        upload_trigger_file(self.trigger_file)
