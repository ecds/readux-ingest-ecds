""" Module of service methods for IIIF objects. """

import requests
import httpretty
from os import environ, path
from django.core.serializers import deserialize
from django.conf import settings
from readux_ingest_ecds.helpers import get_iiif_models
from .metadata_services import create_related_links

Manifest = get_iiif_models()["Manifest"]
RelatedLink = get_iiif_models()["RelatedLink"]
Canvas = get_iiif_models()["Canvas"]
OCR = get_iiif_models()["OCR"]


def set_default_language():
    """Create default language."""
    Language = get_iiif_models()["Language"]
    english, _ = Language.objects.get_or_create(code="en", name="English")
    return english


def find_language(language):
    """Find Language object

    Args:
        language (str): Language code.
    """
    Language = get_iiif_models()["Language"]

    languages = []
    for language_code in language.split(";"):
        try:
            languages.append(
                Language.objects.get(code=language_code.casefold().strip())
            )
        except Language.DoesNotExist:
            pass
    if len(languages) == 0:
        languages.append(set_default_language())

    return languages


def create_manifest(ingest):
    """
    Create or update a Manifest from supplied metadata and images.
    :return: New or updated Manifest with supplied `pid`
    :rtype: iiif.manifest.models.Manifest
    """
    Manifest = get_iiif_models()["Manifest"]
    manifest = None
    # Make a copy of the metadata so we don't extract it over and over.
    try:
        if not bool(ingest.manifest) or ingest.manifest is None:
            ingest.open_metadata()

        metadata = dict(ingest.metadata)
    except TypeError:
        metadata = None
    if metadata:
        if "pid" in metadata:
            manifest, _ = Manifest.objects.get_or_create(pid=metadata["pid"])
        else:
            manifest = Manifest.objects.create()
        for key, value in metadata.items():
            if key == "related":
                # add RelatedLinks from metadata spreadsheet key "related"
                create_related_links(manifest, value)
            elif key == "language":
                manifest.languages.set(find_language(value))
            else:
                # all other keys should exist as fields on Manifest (for now)
                setattr(manifest, key, value)
    # If the key doesn't exist on Manifest model, add it to Manifest.metadata
    else:
        manifest = Manifest()

    manifest.image_server = ingest.image_server

    # Ensure that manifest has an ID before updating the M2M relationship
    manifest.save()
    if not manifest.languages.exists():
        manifest.languages.add(set_default_language())
    manifest.refresh_from_db()
    manifest.collections.set(ingest.collections.all())
    # Save again once relationship is set
    manifest.save()

    return manifest


def create_manifest_from_pid(pid, image_server):
    """Create Manifest and Canvases

    Args:
        pid (str): PID for new Manifest
        images (list[str]): List of image file names
        collections (list[IIIF.Collection])
    """
    Manifest = get_iiif_models()["Manifest"]
    manifest, _ = Manifest.objects.get_or_create(pid=pid, image_server=image_server)
    manifest.languages.add(set_default_language())
    return manifest


def manifest_from_manifest(link):
    if environ["DJANGO_ENV"] == "test":
        fake_manifest = open(path.join(settings.FIXTURE_DIR, "v3_manifest.json"))
        content = fake_manifest.read()
        httpretty.enable()
        httpretty.register_uri(httpretty.GET, link, body=content)

    response = requests.get(link)
    data = response.json()
    return (deserialize(settings.MANIFEST_DESERIALIZER, data), data["items"])


def canvas_from_manifest(data):
    return deserialize(settings.CANVAS_DESERIALIZER, data)


def ocr_from_annotation_page(link, page):
    if environ["DJANGO_ENV"] == "test":
        fake_annos = open(path.join(settings.FIXTURE_DIR, f"ocr_page_{page + 1}.json"))
        content = fake_annos.read()
        httpretty.enable()
        httpretty.register_uri(httpretty.GET, link, body=str(content))

    annos = []
    response = requests.get(link)
    data = response.json()

    for item in data["items"]:
        annos.append(deserialize(settings.ANNOTATION_DESERIALIZER, item)[0])

    return annos
