""" Module of service methods for IIIF objects. """
from readux_ingest_ecds.helpers import get_iiif_models

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
            manifest, created = Manifest.objects.get_or_create(pid=metadata['pid'].replace('_', '-'))
        else:
            manifest = Manifest.objects.create()
        for (key, value) in metadata.items():
            setattr(manifest, key, value)
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
