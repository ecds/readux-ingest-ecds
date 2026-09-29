"""Tests for the ingest success/failure email notifications."""

from unittest.mock import patch
from django.core import mail
from django.test import TestCase
from readux_ingest_ecds.mail import send_email_on_failure, send_email_on_success
from .factories import CanvasFactory, ManifestFactory, UserFactory


class MailTest(TestCase):
    def test_failure_email_falls_back_to_manifest_pid_when_bundle_is_none(self):
        """Remote.failure() doesn't pass bundle= (it's not a file-upload
        ingest), which used to crash the subject line
        ("[Readux] Failed: Ingest " + None). Must fall back to the
        manifest's pid instead of raising."""
        creator = UserFactory.create()
        manifest = ManifestFactory.create()

        send_email_on_failure(
            bundle=None, creator=creator, exception="boom", manifest=manifest
        )  # must not raise

        assert len(mail.outbox) == 1
        assert str(manifest.pid) in mail.outbox[0].subject

    def test_failure_email_falls_back_to_unknown_when_nothing_identifies_it(self):
        """Neither bundle nor manifest available -- still must not raise."""
        creator = UserFactory.create()

        send_email_on_failure(
            bundle=None, creator=creator, exception="boom", manifest=None
        )  # must not raise

        assert len(mail.outbox) == 1
        assert "unknown" in mail.outbox[0].subject

    def test_failure_email_skips_without_raising_when_no_creator(self):
        manifest = ManifestFactory.create()

        send_email_on_failure(
            bundle="x.zip", creator=None, exception="boom", manifest=manifest
        )  # must not raise

        assert len(mail.outbox) == 0

    def test_success_email_skips_without_raising_when_no_creator(self):
        manifest = ManifestFactory.create()

        send_email_on_success(creator=None, manifest=manifest)  # must not raise

        assert len(mail.outbox) == 0

    def test_success_email_skips_without_raising_when_no_manifest(self):
        creator = UserFactory.create()

        send_email_on_success(creator=creator, manifest=None)  # must not raise

        assert len(mail.outbox) == 0

    def test_success_email_sends_normally(self):
        creator = UserFactory.create()
        manifest = ManifestFactory.create()

        send_email_on_success(creator=creator, manifest=manifest)

        assert len(mail.outbox) == 1
        assert str(manifest.pid) in mail.outbox[0].subject
        assert mail.outbox[0].to == [creator.email]

    def test_success_email_reports_canvas_counts_and_source(self):
        """The fuller report: total canvases, how many got OCR vs. how many
        have a warning, and which ingest path produced this manifest."""
        creator = UserFactory.create()
        manifest = ManifestFactory.create()
        canvases = CanvasFactory.create_batch(3, manifest=manifest)

        # Two canvases succeeded; one is flagged via the warnings string,
        # matching the "Canvas <pid> - <reason>" format add_ocr_to_canvases
        # actually produces.
        warnings = f"Canvas {canvases[0].pid} - No OCR"

        send_email_on_success(
            creator=creator, manifest=manifest, warnings=warnings, source="S3"
        )

        assert len(mail.outbox) == 1
        body = mail.outbox[0].body
        assert "S3" in body
        assert "3 total" in body
        assert "2 with OCR" in body
        assert "1 with warnings" in body

    def test_local_success_labels_source_by_from_s3(self):
        """Local.success() should tell the difference between an S3-driven
        ingest and a direct file upload, not send an unlabeled report."""
        from .factories import LocalFactory

        creator = UserFactory.create()
        manifest = ManifestFactory.create()

        s3_local = LocalFactory.create(
            manifest=manifest, creator=creator, from_s3=True
        )
        s3_local.success()
        assert "S3" in mail.outbox[-1].body

        upload_local = LocalFactory.create(
            manifest=manifest, creator=creator, from_s3=False
        )
        upload_local.success()
        assert "File Upload" in mail.outbox[-1].body

    def test_failure_send_mail_exception_does_not_propagate(self):
        """A failed SMTP send must not raise out of the notifier -- this
        runs from Celery's on_failure hook, which is also responsible for
        releasing the ingest lock and deleting the Local row; a mail
        server hiccup shouldn't be able to interrupt that."""
        creator = UserFactory.create()
        manifest = ManifestFactory.create()

        with patch(
            "readux_ingest_ecds.mail.send_mail", side_effect=Exception("smtp down")
        ):
            send_email_on_failure(
                bundle="x.zip", creator=creator, exception="boom", manifest=manifest
            )  # must not raise

    def test_success_send_mail_exception_does_not_propagate(self):
        creator = UserFactory.create()
        manifest = ManifestFactory.create()

        with patch(
            "readux_ingest_ecds.mail.send_mail", side_effect=Exception("smtp down")
        ):
            send_email_on_success(creator=creator, manifest=manifest)  # must not raise
