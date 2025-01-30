from django.core.management.base import BaseCommand, CommandError
from readux_ingest_ecds.helpers import get_iiif_models
from readux_ingest_ecds.services.ocr_services import remove_duplicate_ocr

Manifest = get_iiif_models()["Manifest"]
Canvas = get_iiif_models()["Canvas"]
OCR = get_iiif_models()["OCR"]


class Command(BaseCommand):
    help = "Remove duplicate OCR for a volume or canvas."

    def add_arguments(self, parser):
        parser.add_argument(
            "--volume", type=str, help="PID for volume. Same as --manifest."
        )
        parser.add_argument(
            "--manifest", type=str, help="PID for manifest. Same as --volume."
        )
        parser.add_argument("--canvas", type=str, help="PID for canvas.")
        return super().add_arguments(parser)

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

            for canvas in manifest.canvas_set.all():
                remove_duplicate_ocr(canvas)
