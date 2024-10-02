from django.core.management.base import BaseCommand, CommandError
from readux_ingest_ecds.tasks import add_ocr_manage_task
from readux_ingest_ecds.helpers import get_iiif_models
from readux_ingest_ecds.services.ocr_services import (
    add_ocr_to_canvases,
    get_ocr,
    add_ocr_annotations,
)

Manifest = get_iiif_models()["Manifest"]
Canvas = get_iiif_models()["Canvas"]
OCR = get_iiif_models()["OCR"]


class Command(BaseCommand):
    help = "(Re)Build OCR for a volume or canvas."

    def add_arguments(self, parser):
        parser.add_argument(
            "--volume", type=str, help="PID for volume. Same as --manifest."
        )
        parser.add_argument(
            "--manifest", type=str, help="PID for manifest. Same as --volume."
        )
        parser.add_argument("--canvas", type=str, help="PID for canvas.")

    def handle(self, *args, **options):
        if options["volume"] or options["manifest"]:
            pid = (
                options["volume"]
                if options["volume"] is not None
                else options["manifest"]
            )
            try:
                manifest = Manifest.objects.get(pid=pid)
            except Manifest.DoesNotExist:
                raise CommandError(f"Manifest {pid} does not exist")

            add_ocr_manage_task.delay(manifest.pid)
            self.stdout.write(
                self.style.SUCCESS(
                    f"A background task has started to add OCR to {manifest.pid}. This could take a while depending on volume length. NOTE: The OCR is not necessarily created according to page order."
                )
            )
        elif options["canvas"]:
            try:
                canvas = Canvas.objects.get(pid=options["canvas"])
            except Canvas.DoesNotExist:
                raise CommandError(f"Canvas {options['canvas']} does not exist.")

            new_ocr_annotations = []
            ocr = get_ocr(canvas)
            if ocr is not None:
                new_ocr_annotations += add_ocr_annotations(canvas, ocr)

            OCR.objects.bulk_create(new_ocr_annotations)

            self.stdout.write(self.style.SUCCESS(f"OCR create for {canvas.pid}"))
        else:
            self.stdout.write(
                self.style.ERROR(
                    "You must provide a canvas of volume pid using the --volume or --canvas option."
                )
            )
