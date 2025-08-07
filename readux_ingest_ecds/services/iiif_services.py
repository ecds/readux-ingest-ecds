"""Module of service methods for IIIF objects."""

# pylint: disable=import-error
from os import environ, path
import requests
import httpretty
from django.core.serializers import deserialize
from django.conf import settings
from readux_ingest_ecds.helpers import get_iiif_models
from .metadata_services import create_related_links

Manifest = get_iiif_models()["Manifest"]
RelatedLink = get_iiif_models()["RelatedLink"]
Canvas = get_iiif_models()["Canvas"]
OCR = get_iiif_models()["OCR"]
Language = get_iiif_models()["Language"]
Collection = get_iiif_models()["Collection"]


def set_default_language():
    """Create default language."""
    LanguageModel = get_iiif_models()["Language"]
    english, _ = LanguageModel.objects.get_or_create(code="en", name="English")
    return english


def find_language(language):
    """Find Language object

    Args:
        language (str): Language code.
    """
    LanguageModel = get_iiif_models()["Language"]

    languages = []
    for language_code in language.split(";"):
        try:
            languages.append(
                LanguageModel.objects.get(code=language_code.casefold().strip())
            )
        except LanguageModel.DoesNotExist:
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
    ManifestModel = get_iiif_models()["Manifest"]
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
            manifest, _ = ManifestModel.objects.get_or_create(pid=metadata["pid"])
        else:
            manifest = ManifestModel.objects.create()
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
        manifest = ManifestModel()

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
    ManifestModel = get_iiif_models()["Manifest"]
    manifest, _ = ManifestModel.objects.get_or_create(
        pid=pid, image_server=image_server
    )
    manifest.languages.add(set_default_language())
    return manifest


def manifest_from_manifest(link, version="v3"):
    if environ["DJANGO_ENV"] == "test":
        fake_manifest = open(
            path.join(settings.FIXTURE_DIR, f"{version}_manifest.json")
        )
        content = fake_manifest.read()
        httpretty.enable()
        httpretty.register_uri(httpretty.GET, link, body=content)

    response = requests.get(link, timeout=100)
    data = response.json()
    manifest, relations = deserialize(settings.MANIFEST_DESERIALIZER, data)

    if "presentation/3/context" in data["@context"]:
        return (
            manifest,
            find_relations(relations, "v3"),
            [
                deserialize(settings.CANVAS_DESERIALIZER, canvas)
                for canvas in data["items"]
            ],
        )

    return (
        manifest,
        find_relations(relations, "v2"),
        [
            deserialize(settings.CANVAS_DESERIALIZER, canvas)
            for canvas in data["sequences"][0]["canvases"]
        ],
    )


def ocr_from_annotation_page(link, page):
    if environ["DJANGO_ENV"] == "test":
        fake_annos = open(path.join(settings.FIXTURE_DIR, f"ocr_page_{page + 1}.json"))
        content = fake_annos.read()
        httpretty.enable()
        httpretty.register_uri(httpretty.GET, link, body=str(content))

    response = requests.get(link, timeout=100)
    data = response.json()

    deserialized_annos = deserialize(settings.ANNOTATION_LIST_DESERIALIZER, data)
    return [annos for annos, _ in deserialized_annos]


def find_relations(relations, version):
    LanguageModel = get_iiif_models()["Language"]
    CollectionModel = get_iiif_models()["Collection"]
    related_objects = {}
    if "collections" in relations:
        related_objects["collections"] = []
        for collection in relations["collections"]:
            if version == "v3":
                collection_obj, _ = CollectionModel.objects.get_or_create(
                    label=collection
                )
                related_objects["collections"].append(collection_obj)
            else:
                pid = collection.split("/")[-1]
                collection_obj, created = CollectionModel.objects.get_or_create(pid=pid)
                if created:
                    collection_obj.label = pid.title()
                    collection_obj.save(update_fields=["label"])

    if "languages" in relations:
        related_objects["languages"] = []
        for language in relations["languages"]:
            try:
                related_objects["languages"].append(
                    LanguageModel.objects.get(code=language)
                )
            except LanguageModel.DoesNotExist:
                # welp
                pass
    return related_objects


def annotations(canvas):
    if (
        "@context" in canvas.keys()
        and "2/context" in canvas["@context"]
        and "otherContent" in canvas.keys()
        and len(canvas["otherContent"] > 0)
    ):
        return [
            anno["@id"]
            for anno in canvas["otherContent"]
            if "AnnotationPage" in anno["@type"]
        ]

    if "annotations" in canvas.keys() and len(canvas["annotations"]) > 0:
        return [
            anno["id"]
            for anno in canvas["annotations"]
            if anno["type"] == "AnnotationPage"
        ]

    return None
