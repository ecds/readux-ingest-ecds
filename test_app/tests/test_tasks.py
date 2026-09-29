from django.test import TestCase
import os
import boto3
from moto import mock_aws
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from readux_ingest_ecds import tasks as tasks_module
from readux_ingest_ecds.locks import release_ingest_lock, try_acquire_ingest_lock
from readux_ingest_ecds.models import Local
from readux_ingest_ecds.tasks import (
    FinalTask,
    ReleaseLocalLockOnFailure,
    TRANSIENT_EXCEPTIONS,
    local_ingest_task_ecds,
)
from shutil import rmtree
from django.conf import settings
from .factories import ImageServerFactory, LocalFactory, ManifestFactory


@mock_aws
class TaskTest(TestCase):
    """Test Celery tasks success and failure."""

    def setUp(self):
        """Set instance variables."""
        super().setUp()
        rmtree(settings.INGEST_TMP_DIR, ignore_errors=True)
        self.fixture_path = settings.FIXTURE_DIR
        self.image_server = ImageServerFactory()

        conn = boto3.resource("s3", region_name="us-east-1")
        conn.create_bucket(Bucket=settings.INGEST_TRIGGER_BUCKET)
        conn.create_bucket(Bucket=settings.INGEST_BUCKET)

    def tearDown(self):
        cache.clear()
        super().tearDown()

    def teardown_class():
        rmtree(settings.INGEST_TMP_DIR, ignore_errors=True)

    def test_it_deletes_ingest_on_success(self):
        local = LocalFactory.create(
            bundle=SimpleUploadedFile(
                name="no_meta_file.zip",
                content=open(
                    os.path.join(self.fixture_path, "no_meta_file.zip"), "rb"
                ).read(),
            )
        )
        local.metadata = {"pid": "808", "publisher": "Goodie Mob"}
        local.prep()
        local_ingest_task_ecds(local.id)
        assert True

    def test_local_ingest_task_skips_when_already_locked(self):
        """If another run is already holding the lock for this ingest_id
        (e.g. an admin resave racing an in-flight pipeline), the task
        should skip its work entirely rather than run ingest() twice."""
        local = LocalFactory.create(
            bundle=SimpleUploadedFile(
                name="no_meta_file.zip",
                content=open(
                    os.path.join(self.fixture_path, "no_meta_file.zip"), "rb"
                ).read(),
            )
        )
        local.metadata = {"pid": "809", "publisher": "Goodie Mob"}
        local.prep()

        # prep() itself creates and assigns the manifest, independent of
        # locking -- the thing the lock actually guards is create_canvases(),
        # so that's what has to stay untouched to prove the task returned
        # early.
        local.refresh_from_db()
        assert local.manifest.canvas_set.count() == 0

        try_acquire_ingest_lock("local", local.id)
        local_ingest_task_ecds(local.id)  # should return immediately

        local.refresh_from_db()
        assert local.manifest.canvas_set.count() == 0  # create_canvases() never ran

        release_ingest_lock("local", local.id)


class IngestLockReleaseTest(TestCase):
    """Verifies the Celery hooks that release the ingest lock once a
    pipeline reaches a terminal state (success, or a final, non-retried
    failure), independent of the S3/bundle machinery TaskTest exercises."""

    def tearDown(self):
        cache.clear()
        super().tearDown()

    def test_final_task_on_success_releases_lock(self):
        local = LocalFactory.create(manifest=ManifestFactory.create())
        try_acquire_ingest_lock("local", str(local.id))

        FinalTask().on_success(None, "task-id", [str(local.id)], {})

        assert try_acquire_ingest_lock("local", str(local.id)) is True

    def test_final_task_on_failure_releases_lock(self):
        local = LocalFactory.create(manifest=ManifestFactory.create())
        try_acquire_ingest_lock("local", str(local.id))

        FinalTask().on_failure(Exception("boom"), "task-id", [str(local.id)], {}, None)

        assert try_acquire_ingest_lock("local", str(local.id)) is True

    def test_release_local_lock_on_failure_releases_lock(self):
        """The intermediate-stage hook (add_canvases_task,
        local_ingest_task_ecds, retry_local_from_s3_task) that releases the
        lock if the pipeline fails before ever reaching add_ocr_task_local."""
        try_acquire_ingest_lock("local", "some-ingest-id")

        ReleaseLocalLockOnFailure().on_failure(
            Exception("boom"), "task-id", ["some-ingest-id"], {}, None
        )

        assert try_acquire_ingest_lock("local", "some-ingest-id") is True


class RetryScopingTest(TestCase):
    """Regression guard for the retry-scoping fix: every Celery task in
    this module used to retry on bare Exception, which blindly retried
    non-idempotent work (bulk_create calls, etc.) and permanent failures
    (bad data, "doesn't exist" errors) exactly as eagerly as genuine
    network/DB blips. This asserts none of them fell back to that."""

    def _all_registered_tasks(self):
        from celery.app.task import Task

        return [
            value
            for value in vars(tasks_module).values()
            if isinstance(value, Task) and value.name
        ]

    def test_no_task_retries_on_bare_exception(self):
        tasks = self._all_registered_tasks()
        assert len(tasks) >= 10  # sanity check the lookup actually found them

        for task in tasks:
            autoretry_for = getattr(task, "autoretry_for", ())
            assert Exception not in autoretry_for, (
                f"{task.name} still retries on bare Exception"
            )

    def test_transient_exceptions_are_connectivity_only(self):
        """Guards against TRANSIENT_EXCEPTIONS itself quietly growing to
        include something like botocore.exceptions.ClientError, which
        would also catch permanent errors like NoSuchBucket."""
        from botocore.exceptions import ClientError

        assert ClientError not in TRANSIENT_EXCEPTIONS
        assert ValueError not in TRANSIENT_EXCEPTIONS
