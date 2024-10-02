from django.core.management.base import BaseCommand, CommandError
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
        parser.add_argument("--volume", type=str, help="PID for volume/manifest.")

        parser.add_argument("--canvas", type=str, help="PID for canvas.")

    def handle(self, *args, **options):
        if options["volume"]:
            try:
                manifest = Manifest.objects.get(pid=options["volume"])
            except Manifest.DoesNotExist:
                raise CommandError(f'Manifest {options["volume"]} does not exist')

            add_ocr_to_canvases(manifest)
            self.stdout.write(self.style.SUCCESS(f"OCR create for {manifest.pid}"))
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
