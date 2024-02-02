""" Module of service methods for IIIF objects. """
from readux_ingest_ecds.helpers import get_iiif_models
from .metadata_services import create_related_links

Manifest = get_iiif_models()['Manifest']
RelatedLink = get_iiif_models()['RelatedLink']
OCR = get_iiif_models()['OCR']

def create_manifest(ingest):
    """
    Create or update a Manifest from supplied metadata and images.
    :return: New or updated Manifest with supplied `pid`
    :rtype: iiif.manifest.models.Manifest
    """
    Manifest = get_iiif_models()['Manifest']
    manifest = None
    # Make a copy of the metadata so we don't extract it over and over.
    try:
        if not bool(ingest.manifest) or ingest.manifest is None:
            ingest.open_metadata()

        metadata = dict(ingest.metadata)
    except TypeError:
        metadata = None
    if metadata:
        if 'pid' in metadata:
            manifest, _ = Manifest.objects.get_or_create(pid=metadata['pid'])
        else:
            manifest = Manifest.objects.create()
        for (key, value) in metadata.items():
            if key == 'related':
                 # add RelatedLinks from metadata spreadsheet key "related"
                create_related_links(manifest, value)
            else:
                # all other keys should exist as fields on Manifest (for now)
                setattr(manifest, key, value)
    # If the key doesn't exist on Manifest model, add it to Manifest.metadata
    else:
        manifest = Manifest()

    manifest.image_server = ingest.image_server

    # Ensure that manifest has an ID before updating the M2M relationship
    manifest.save()
    manifest.refresh_from_db()
    manifest.collections.set(ingest.collections.all())
    # Save again once relationship is set
    manifest.save()

    return manifest
