from django.core.management.base import BaseCommand, CommandError
from readux_ingest_ecds.helpers import get_iiif_models
from readux_ingest_ecds.services.ocr_services import add_ocr_to_canvases

Manifest = get_iiif_models()["Manifest"]


class Command(BaseCommand):
    help = "(Re)Build OCR for a volume"

    def add_arguments(self, parser):
        parser.add_argument(
            "volume", type=str, help="PID for volume/manifest to be generated."
        )

    def handle(self, *args, **options):
        try:
            manifest = Manifest.objects.get(pid=options["volume"])
        except Manifest.DoesNotExist:
            raise CommandError('Manifest "%s" does not exist' % options["volume"])

        add_ocr_to_canvases(manifest)

        self.stdout.write(
            self.style.SUCCESS('Successfully closed poll "%s"' % manifest.pid)
        )
