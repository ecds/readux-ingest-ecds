import os
from uuid import uuid4
from unittest.mock import patch
from django.core import mail
from django.conf import settings
from django.db.utils import OperationalError
from django.test import TestCase
from readux_ingest_ecds.services import ocr_services
from readux_ingest_ecds.tasks import add_ocr_task_local
from .factories import CanvasFactory, LocalFactory, ManifestFactory, UserFactory
from iiif.models import OCR


class OCRTest(TestCase):
    def setUp(self):
        """Set instance variables."""
        super().setUp()
        self.fixture_path = settings.FIXTURE_DIR

    def test_alto4_xml_file(self):
        """It should normalize keys that match a Manifest field."""
        canvas = CanvasFactory.create(
            ocr_file_path=os.path.join(self.fixture_path, "alto4.xml")
        )
        result = ocr_services.fetch_positional_ocr(canvas)
        ocr = ocr_services.parse_alto_ocr(result)
        assert ocr[1] == {"content": "No.", "h": 52, "w": 85, "x": 176, "y": 438}

    def test_empty_xml(self):
        """It should add a warning to the ingest."""
        manifest = ManifestFactory.create()
        canvas = CanvasFactory.create(
            ocr_file_path=os.path.join(self.fixture_path, "empty.xml"),
            manifest=manifest,
        )
        CanvasFactory.create(
            ocr_file_path=os.path.join(self.fixture_path, "empty.xml"),
            manifest=manifest,
        )
        local = LocalFactory.create(manifest=manifest, creator=UserFactory.create())
        add_ocr_task_local(local.id, manifest.pid)
        local.refresh_from_db()
        local.success()
        assert local.warnings.startswith(
            f"Canvas {canvas.pid} - XMLSyntaxError: Document is empty, line 1, column 1 (<string>, line 1) | "
        )
        assert "XMLSyntaxError" in mail.outbox[0].body
        assert "iip" in mail.outbox[0].body

    def test_prevent_double_ocr(self):
        """"""
        canvas = CanvasFactory.create(
            ocr_file_path=os.path.join(self.fixture_path, "alto4.xml"),
            manifest=ManifestFactory.create(),
        )

        ocr = ocr_services.get_ocr(canvas)
        annos = ocr_services.add_ocr_annotations(canvas, ocr)
        OCR.objects.bulk_create(annos)
        assert len(annos) == 178
        assert OCR.objects.count() == 178
        dupe_annos = ocr_services.add_ocr_annotations(canvas, ocr)
        assert len(dupe_annos) == 0

    def test_add_ocr_annotations_dedupes_within_a_single_batch(self):
        """If the OCR source lists the same word position twice within one
        get_ocr() call (a malformed/repeated line), add_ocr_annotations()
        must not create two rows for it. The DB existence check alone
        can't catch this -- neither duplicate is committed yet when the
        second one is checked -- so this has to be caught in-memory."""
        canvas = CanvasFactory.create(manifest=ManifestFactory.create())
        word = {"content": "duplicate", "w": 10, "h": 10, "x": 5, "y": 5}

        annos = ocr_services.add_ocr_annotations(canvas, [dict(word), dict(word)])

        assert len(annos) == 1

    def test_add_ocr_annotations_skips_gracefully_on_pre_existing_duplicates(self):
        """If a canvas already has more than one existing OCR row at the
        same geometry (leftover duplication from before this session's
        fixes), add_ocr_annotations() must not crash with
        MultipleObjectsReturned -- it should just skip creating another
        copy and leave the existing rows alone."""
        canvas = CanvasFactory.create(manifest=ManifestFactory.create())
        for _ in range(2):
            OCR.objects.create(
                canvas=canvas,
                w=10,
                h=10,
                x=5,
                y=5,
                content="existing",
                order=1,
                resource_type=OCR.OCR,
            )

        word = {"content": "existing", "w": 10, "h": 10, "x": 5, "y": 5}

        annos = ocr_services.add_ocr_annotations(canvas, [word])  # must not raise

        assert annos == []
        assert OCR.objects.filter(canvas=canvas).count() == 2

    def test_add_ocr_to_canvases_isolates_a_single_canvas_failure(self):
        """A non-transient exception from one canvas (e.g. malformed hOCR)
        must not abort the whole task -- OCR should still get added for
        every other canvas, and the failure recorded as a warning instead
        of propagating. Letting it propagate would reach
        add_ocr_task_local's on_failure -> Local.failure(), which deletes
        the whole ingest's tracking record even though every other canvas
        already succeeded."""
        manifest = ManifestFactory.create()
        good_canvas = CanvasFactory.create(
            ocr_file_path=os.path.join(self.fixture_path, "alto4.xml"),
            manifest=manifest,
        )
        bad_canvas = CanvasFactory.create(
            ocr_file_path=os.path.join(self.fixture_path, "alto4.xml"),
            manifest=manifest,
        )

        real_get_ocr = ocr_services.get_ocr

        def flaky_get_ocr(canvas):
            if canvas.pk == bad_canvas.pk:
                raise ValueError("simulated malformed OCR source")
            return real_get_ocr(canvas)

        with patch(
            "readux_ingest_ecds.services.ocr_services.get_ocr",
            side_effect=flaky_get_ocr,
        ):
            warnings = ocr_services.add_ocr_to_canvases(manifest)

        assert OCR.objects.filter(canvas=good_canvas).count() == 178
        assert OCR.objects.filter(canvas=bad_canvas).count() == 0
        assert any(
            "ValueError" in w and str(bad_canvas.pid) in w for w in warnings
        )

    def test_add_ocr_to_canvases_reraises_transient_exceptions(self):
        """A transient/connectivity exception must propagate rather than
        get swallowed as a per-canvas warning, so Celery's autoretry_for
        on add_ocr_task_local actually retries the whole task instead of
        silently recording "this canvas failed" for something that might
        succeed on the next attempt."""
        manifest = ManifestFactory.create()
        CanvasFactory.create(
            ocr_file_path=os.path.join(self.fixture_path, "alto4.xml"),
            manifest=manifest,
        )

        with patch(
            "readux_ingest_ecds.services.ocr_services.get_ocr",
            side_effect=OperationalError("connection lost"),
        ):
            with self.assertRaises(OperationalError):
                ocr_services.add_ocr_to_canvases(manifest)

    def test_add_ocr_to_canvases_handles_multiple_canvases(self):
        """add_ocr_to_canvases() now flushes each canvas's OCR to the DB
        individually instead of accumulating a whole batch of canvases in
        memory first (a fix for workers getting OOM-killed on large
        manifests) -- this confirms that change still adds OCR correctly
        across more than one canvas, not just a single one."""
        manifest = ManifestFactory.create()
        canvas_one = CanvasFactory.create(
            ocr_file_path=os.path.join(self.fixture_path, "alto4.xml"),
            manifest=manifest,
        )
        canvas_two = CanvasFactory.create(
            ocr_file_path=os.path.join(self.fixture_path, "alto4.xml"),
            manifest=manifest,
        )

        warnings = ocr_services.add_ocr_to_canvases(manifest)

        assert warnings == []
        assert OCR.objects.filter(canvas=canvas_one).count() == 178
        assert OCR.objects.filter(canvas=canvas_two).count() == 178


ALTO4_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<alto xmlns="http://www.loc.gov/standards/alto/ns-v4#">
  <Layout><Page ID="P1" PHYSICAL_IMG_NR="1" WIDTH="1279" HEIGHT="2029"><PrintSpace>
    <TextBlock ID="TB1"><TextLine ID="TL1" HPOS="624" VPOS="214" WIDTH="216" HEIGHT="30">
      {strings}
    </TextLine></TextBlock>
  </PrintSpace></Page></Layout>
</alto>"""


class ALTOParsingTest(TestCase):
    """parse_alto_ocr() only reads String text and position, so it accepts
    files the strict ALTO schema would reject over other attributes."""

    def parse(self, strings):
        return ocr_services.parse_alto_ocr(
            ALTO4_TEMPLATE.format(strings=strings).encode("utf-8")
        )

    def test_word_confidence_out_of_schema_range_is_accepted(self):
        """Seen in converted Textract output: WC as 0-100, where ALTO
        requires 0-1. The schema used to reject every page over it."""
        ocr = self.parse(
            '<String ID="S1" HPOS="624" VPOS="214" WIDTH="204" HEIGHT="30" '
            'CONTENT="ᏗᎧᏃᎩᏍᏗ" WC="93"/>'
        )

        assert ocr == [{"content": "ᏗᎧᏃᎩᏍᏗ", "h": 30, "w": 204, "x": 624, "y": 214}]

    def test_decimal_positions_are_rounded(self):
        ocr = self.parse(
            '<String ID="S1" HPOS="10.6" VPOS="20.4" WIDTH="30.5" HEIGHT="40" '
            'CONTENT="word"/>'
        )

        assert ocr == [{"content": "word", "h": 40, "w": 30, "x": 11, "y": 20}]

    def test_missing_position_is_a_clear_error(self):
        with self.assertRaisesRegex(ValueError, "ALTO String S1 needs CONTENT"):
            self.parse('<String ID="S1" VPOS="20" WIDTH="30" HEIGHT="40" CONTENT="w"/>')


class WarningsReportTest(TestCase):
    def test_long_error_detail_is_capped(self):
        canvas = CanvasFactory.create()

        warning = ocr_services.canvas_warning(canvas, ValueError("x" * 5000))

        assert warning.startswith(f"Canvas {canvas.pid} - ValueError: ")
        assert len(warning) < ocr_services.MAX_WARNING_DETAIL + len(str(canvas.pid)) + 20

    def test_separator_in_error_detail_is_replaced(self):
        """The report splits warnings on " | ", so one inside an error
        message would be counted as an extra canvas."""
        canvas = CanvasFactory.create()

        warning = ocr_services.canvas_warning(canvas, ValueError("a | b"))

        assert " | " not in warning

    def test_warnings_column_has_no_length_limit(self):
        """Every page of a volume failing used to overflow the old
        10,000-character column and crash the end of the OCR step. Checked
        on the field because SQLite, used for these tests, doesn't enforce
        column lengths, so the overflow itself can't be reproduced here."""
        from readux_ingest_ecds.models import Local

        assert Local._meta.get_field("warnings").max_length is None
