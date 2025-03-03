import os
import boto3
import tempfile
from shutil import rmtree
from faker import Faker
from faker_file.providers.jpeg_file import JpegFileProvider
from faker_file.storages.filesystem import FileSystemStorage
from moto import mock_aws
from django.test import TestCase
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from .factories import ImageServerFactory, S3IngestFactory
from iiif.models import Manifest
from readux_ingest_ecds.tasks import s3_ingest_task


@mock_aws
class S3Test(TestCase):
    def setUp(self):
        """Set instance variables."""
        super().setUp()
        rmtree(settings.INGEST_TMP_DIR, ignore_errors=True)
        os.makedirs(os.path.join(settings.INGEST_TMP_DIR))
        os.makedirs(
            os.path.join(settings.INGEST_TMP_DIR, settings.INGEST_STAGING_PREFIX)
        )
        os.makedirs(
            os.path.join(settings.INGEST_TMP_DIR, settings.INGEST_OCR_PREFIX),
            exist_ok=True,
        )
        os.makedirs(os.path.join(settings.INGEST_PROCESSING_DIR), exist_ok=True)
        self.image_server = ImageServerFactory()
        self.ingest_files = []
        self.fake = Faker()
        self.fake.add_provider(JpegFileProvider)
        self.s3 = boto3.resource("s3")
        self.fixture_path = settings.INGEST_TMP_DIR
        # os.mkdir(settings.INGEST_TMP_DIR)

        conn = boto3.resource("s3", region_name="us-east-1")
        conn.create_bucket(Bucket=settings.INGEST_TRIGGER_BUCKET)
        conn.create_bucket(Bucket=settings.INGEST_BUCKET)
        conn.create_bucket(Bucket="source")

    def teardown_class():
        rmtree(settings.INGEST_TMP_DIR, ignore_errors=True)
        for item in os.listdir("./"):
            if item.endswith(".csv") or item.endswith(".zip"):
                os.remove(os.path.join("./", item))

    def create_source_images(
        self, pid=None, count=1, include_pid_in_file=True, prefix="tmp"
    ):
        if pid is None:
            raise Exception("You must supply a pid kwarg")

        sub_dir = f"{prefix}/{pid}" if include_pid_in_file else pid
        self.fs_storage = FileSystemStorage(
            root_path=tempfile.gettempdir(),
            rel_path=sub_dir,
        )

        os.makedirs(
            os.path.join(self.fs_storage.root_path, self.fs_storage.rel_path, "images"),
            exist_ok=True,
        )

        os.makedirs(
            os.path.join(self.fs_storage.root_path, self.fs_storage.rel_path, "ocr"),
            exist_ok=True,
        )

        for _ in range(count):
            fake_image = self.fake.jpeg_file(storage=self.fs_storage)
            # include the pid in the filename if not included in the path
            image_key = (
                os.path.join(sub_dir, f"{pid}_{os.path.basename(fake_image)}")
                if include_pid_in_file
                else os.path.join(
                    self.fs_storage.rel_path, os.path.basename(fake_image)
                )
            )
            ocr_key = image_key.replace("jpg", "txt")
            open(
                os.path.join(self.fs_storage.root_path, ocr_key),
                "a",
                encoding="utf-8",
            ).close()

            self.s3.Bucket("source").upload_file(
                os.path.join(self.fs_storage.root_path, str(fake_image)),
                f"images/{image_key}",
            )
            self.s3.Bucket("source").upload_file(
                os.path.join(self.fs_storage.root_path, ocr_key), f"ocr/{ocr_key}"
            )

    def create_pids(
        self,
        pid_count=1,
        image_count=1,
        include_pid_in_file=True,
        specific_pid=None,
        prefix=None,
    ):
        # We don't want to create multiple with same pid.
        if pid_count > 1 and specific_pid is not None:
            assert False

        pids = []
        pid_file = os.path.join(self.fixture_path, self.fake.file_name(extension="csv"))
        with open(pid_file, "w", encoding="utf-8") as t_file:
            t_file.write("PID,Label\n")

        for _ in range(pid_count):
            pid = self.fake.isbn10() if specific_pid is None else specific_pid
            if prefix is not None:
                pid = f"{prefix}_{pid}"
            with open(pid_file, "a", encoding="utf-8") as t_file:
                t_file.write(f"{pid},{self.fake.name()}\n")
            pids.append(pid)
            self.create_source_images(
                pid=pid, count=image_count, include_pid_in_file=include_pid_in_file
            )

        return (pids, pid_file)

    def test_s3_ingest_pid_not_in_filename(self):
        pids, pid_file = self.create_pids(
            pid_count=3, image_count=4, include_pid_in_file=False
        )

        upload_file = SimpleUploadedFile(
            name=os.path.basename(pid_file),
            content=open(pid_file, "rb").read(),
        )

        ingest = S3IngestFactory(metadata_spreadsheet=upload_file)
        s3_ingest_task(ingest.id)
        # ingest.ingest()

        destination_bucket = self.s3.Bucket(settings.INGEST_BUCKET)
        for pid in pids:
            ingested_images = [
                str(obj.key)
                for obj in destination_bucket.objects.all()
                if str(obj.key).startswith(f"{settings.INGEST_STAGING_PREFIX}/{pid}_")
            ]
            ingested_ocr = [
                str(obj.key)
                for obj in destination_bucket.objects.all()
                if str(obj.key).startswith(f"{settings.INGEST_OCR_PREFIX}/{pid}/")
            ]
            assert Manifest.objects.filter(pid=pid).exists()
            assert Manifest.objects.get(pid=pid).canvas_set.count() == 4
            assert Manifest.objects.get(pid=pid).label is not None
            assert len(ingested_images) == 4
            assert len(ingested_ocr) == 4

    def test_s3_ingest_pid_in_filename(self):
        pids, pid_file = self.create_pids(pid_count=2, image_count=3)

        upload_file = SimpleUploadedFile(
            name=os.path.basename(pid_file),
            content=open(pid_file, "rb").read(),
        )

        ingest = S3IngestFactory(metadata_spreadsheet=upload_file)
        # ingest.ingest()
        s3_ingest_task(ingest.id)

        destination_bucket = self.s3.Bucket(settings.INGEST_BUCKET)
        for pid in pids:
            ingested_images = [
                str(obj.key)
                for obj in destination_bucket.objects.all()
                if str(obj.key).startswith(f"{settings.INGEST_STAGING_PREFIX}/{pid}_")
            ]
            ingested_ocr = [
                str(obj.key)
                for obj in destination_bucket.objects.all()
                if str(obj.key).startswith(f"{settings.INGEST_OCR_PREFIX}/{pid}/{pid}_")
            ]
            assert Manifest.objects.filter(pid=pid).exists()
            assert Manifest.objects.get(pid=pid).canvas_set.count() == 3
            assert len(ingested_images) == 3
            assert len(ingested_ocr) == 3

    def test_s3_ingest_with_prefix(self):
        # Make files without prefix
        pids, pid_file = self.create_pids(pid_count=3, image_count=2)

        # Make files with prefix.
        for pid in pids:
            self.create_source_images(pid=pid, count=2, prefix="emory")

        upload_file = SimpleUploadedFile(
            name=os.path.basename(pid_file),
            content=open(pid_file, "rb").read(),
        )

        ingest = S3IngestFactory(metadata_spreadsheet=upload_file, prefix="emory")
        # ingest.ingest()
        s3_ingest_task(ingest.id)

        destination_bucket = self.s3.Bucket(settings.INGEST_BUCKET)

        source_files = [str(obj.key) for obj in self.s3.Bucket("source").objects.all()]

        for pid in pids:
            ingested_images = [
                os.path.basename(str(obj.key))
                for obj in destination_bucket.objects.all()
                if str(obj.key).startswith(f"{settings.INGEST_STAGING_PREFIX}/{pid}_")
            ]

            ingested_ocr = [
                os.path.basename(str(obj.key))
                for obj in destination_bucket.objects.all()
                if str(obj.key).startswith(f"{settings.INGEST_OCR_PREFIX}/{pid}/{pid}_")
            ]

            canvases = [
                canvas.pid.replace(".tiff", ".jpg")
                for canvas in Manifest.objects.get(pid=pid).canvas_set.all()
            ]

            for source_file in source_files:
                if pid in source_file and source_file.endswith("jpg"):
                    if "emory" in source_file:
                        assert os.path.basename(source_file) in canvases
                    if "emory" not in source_file:
                        assert os.path.basename(source_file) not in canvases

            assert Manifest.objects.filter(pid=pid).exists()
            # Assert it only included files with prefix.
            assert Manifest.objects.get(pid=pid).canvas_set.count() == 2
            assert len(ingested_images) == 2
            assert len(ingested_ocr) == 2

    def test_s3_ingest_with_partial_pid(self):
        """
        This is to ensure a pid like "oxford" doesn't also collect files with pids like "oxford2"
        """
        pids, pid_file = self.create_pids(specific_pid="oxford")
        other_pids, other_pid_file = self.create_pids(
            pid_count=3, image_count=2, prefix="oxford"
        )

        for pid in pids:
            assert pid == "oxford"

        upload_file = SimpleUploadedFile(
            name=os.path.basename(pid_file),
            content=open(pid_file, "rb").read(),
        )

        for pid in other_pids:
            assert "oxford" != pid
            assert "oxford" in pid

        other_upload_file = SimpleUploadedFile(
            name=os.path.basename(pid_file),
            content=open(pid_file, "rb").read(),
        )

        ingest = S3IngestFactory(metadata_spreadsheet=upload_file)
        other_ingest = S3IngestFactory(metadata_spreadsheet=other_upload_file)
        s3_ingest_task(ingest.id)
        # s3_ingest_task(other_ingest.id)

        destination_bucket = self.s3.Bucket(settings.INGEST_BUCKET)

        source_files = [str(obj.key) for obj in self.s3.Bucket("source").objects.all()]

        assert len(source_files) == 14
        # Note: this assumes that the pid is in the 3rd position in the path.
        assert len([f for f in source_files if "oxford" in f]) == 14
        assert (
            len([f for f in source_files if f.split("/")[2].startswith("oxford")]) == 14
        )
        assert len([f for f in source_files if f.split("/")[2] == "oxford"]) == 2

        for pid in pids:
            ingested_images = [
                str(obj.key)
                for obj in destination_bucket.objects.all()
                if str(obj.key).startswith(f"{settings.INGEST_STAGING_PREFIX}/{pid}_")
            ]
            ingested_ocr = [
                str(obj.key)
                for obj in destination_bucket.objects.all()
                if str(obj.key).startswith(f"{settings.INGEST_OCR_PREFIX}/{pid}/{pid}_")
            ]
            assert Manifest.objects.filter(pid=pid).exists()
            assert Manifest.objects.get(pid=pid).canvas_set.count() == 1
            assert len(ingested_images) == 1
            assert len(ingested_ocr) == 1
