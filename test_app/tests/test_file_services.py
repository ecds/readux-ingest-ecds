import os
import boto3
from faker import Faker
from moto import mock_aws
from django.test import TestCase
from django.conf import settings
from readux_ingest_ecds.services import file_services


@mock_aws
class FileServicesTest(TestCase):
    def setUp(self):
        """Set instance variables."""
        super().setUp()
        self.fake = Faker()
        self.fixture_path = settings.FIXTURE_DIR
        self.s3 = boto3.resource("s3", region_name="us-east-1")
        self.s3.create_bucket(Bucket=settings.INGEST_TRIGGER_BUCKET)
        self.s3.create_bucket(Bucket=settings.INGEST_BUCKET)
        self.s3.create_bucket(Bucket="source")
        os.makedirs(settings.INGEST_OCR_DIR, exist_ok=True)

    def test_s3_copy(self):
        fixture_dir = os.path.join(self.fixture_path, "s3_copy")
        files = os.listdir(fixture_dir)
        for mock_file in files:
            with open(os.path.join(fixture_dir, mock_file), "rb") as f:
                if mock_file.endswith("jpg"):
                    self.s3.Bucket("source").upload_fileobj(
                        f, f"pid/images/{mock_file}"
                    )
                else:
                    self.s3.Bucket("source").upload_fileobj(f, f"pid/ocr/{mock_file}")

        images, ocr_files = file_services.s3_copy("source", "pid")

        for image in images:
            self.s3.Object(
                settings.INGEST_BUCKET,
                f"{settings.INGEST_STAGING_PREFIX}/{image}",
            ).load()

        # OCR is downloaded locally rather than copied to the ingest bucket.
        for ocr in ocr_files:
            assert os.path.dirname(ocr) == os.path.join(settings.INGEST_OCR_DIR, "pid")
            assert os.path.isfile(ocr)
        assert len(images) == 10
        assert len(ocr_files) == 10

    def test_s3_copy_with_prefix_only_matches_that_prefix(self):
        """s3_copy() now passes Prefix= to the S3 list call itself instead
        of listing the whole bucket and filtering in Python -- this checks
        that narrowing didn't break correctness: files under a *different*
        prefix (even matching the same pid) must not be picked up, and
        files under the requested prefix still are."""
        self.s3.Bucket("source").put_object(
            Key="myprefix/pid/images/page1.jpg", Body=b"fake-image"
        )
        self.s3.Bucket("source").put_object(
            Key="myprefix/pid/ocr/page1.xml", Body=b"fake-ocr"
        )
        # Same pid, but under a different prefix -- must be excluded.
        self.s3.Bucket("source").put_object(
            Key="otherprefix/pid/images/page1.jpg", Body=b"fake-image"
        )

        images, ocr_files = file_services.s3_copy("source", "pid", prefix="myprefix")

        assert len(images) == 1
        assert len(ocr_files) == 1

    def test_s3_copy_lists_fewer_objects_with_a_prefix(self):
        """Confirms the narrowing is genuinely happening server-side (via
        Prefix=), not just that results are still correct -- a bucket-wide
        listing would still return the right *files* even without this
        fix, since the pid/images/ocr filtering in Python was already
        correct; what changed is how much the S3 API call itself has to
        return in the first place."""
        for i in range(20):
            self.s3.Bucket("source").put_object(
                Key=f"unrelated-{i}/other/images/page.jpg", Body=b"noise"
            )
        self.s3.Bucket("source").put_object(
            Key="myprefix/pid/images/page1.jpg", Body=b"fake-image"
        )

        bucket = self.s3.Bucket("source")
        full_scan_count = len(list(bucket.objects.all()))
        prefixed_count = len(list(bucket.objects.filter(Prefix="myprefix/")))

        assert full_scan_count == 21
        assert prefixed_count == 1

        images, ocr_files = file_services.s3_copy("source", "pid", prefix="myprefix")
        assert len(images) == 1
