""" Module of service methods for ingest files. """

from readux_ingest_ecds.helpers import get_iiif_models
from mimetypes import guess_type
from tablib.core import Dataset

Manifest = get_iiif_models()["Manifest"]
RelatedLink = get_iiif_models()["RelatedLink"]


def clean_metadata(metadata):
    """Remove keys that do not align with Manifest fields.

    :param metadata:
    :type metadata: tablib.Dataset
    :return: Dictionary with keys matching Manifest fields
    :rtype: dict
    """
    fields = [
        *(f.name for f in get_iiif_models()["Manifest"]._meta.get_fields()),
        "related",
    ]

    metadata = {
        (
            key.casefold().replace(" ", "_")
            if key.casefold().replace(" ", "_") in fields
            else key
        ): value
        for key, value in metadata.items()
    }

    if "metadata" not in metadata.keys():
        metadata["metadata"] = []

    extra_keys = []

    # for key in metadata.keys():
    #     if key != 'metadata' and key not in fields:
    #         metadata['metadata'][key] = metadata[key]

    # for key in metadata['metadata']:
    #     try:
    #         metadata.pop(key)
    #     except KeyError:
    #         # Just making sure.
    #         pass

    for key in metadata.keys():
        if key != "metadata" and isinstance(metadata[key], list):
            if isinstance(metadata[key][0], dict):
                for meta_key in metadata[key][0].keys():
                    if "value" in meta_key:
                        metadata[key] = metadata[key][0][meta_key]
            else:
                metadata[key] = ", ".join(metadata[key])
        if key not in fields:
            extra_keys.append(key)

    for key in extra_keys:
        metadata["metadata"].append({"label": key, "value": metadata[key]})
        metadata.pop(key)

    return metadata


def create_related_links(manifest, related_str):
    """
    Create RelatedLink objects from supplied related links string and associate each with supplied
    Manifest. String should consist of semicolon-separated URLs.
    :param manifest:
    :type related_str: iiif.manifest.models.Manifest
    :param related_str:
    :type related_str: str
    :rtype: None
    """
    for link in related_str.split(";"):
        (format, _) = guess_type(link)
        get_iiif_models()["RelatedLink"].objects.create(
            manifest=manifest,
            link=link,
            format=format
            or "text/html",  # assume web page if MIME type cannot be determined
            is_structured_data=False,  # assume this is not meant for seeAlso
        )


def get_metadata_from(files):
    """
    Find metadata file in uploaded files.
    :return: If metadata file exists, returns the values. If no file, returns None.
    :rtype: list or None
    """
    metadata = None
    for file in files:
        if metadata is not None:
            continue
        if "zip" in guess_type(file.name)[0]:
            continue
        if "metadata" in file.name.casefold():
            stream = file.read()
            if (
                "csv" in guess_type(file.name)[0]
                or "tab-separated" in guess_type(file.name)[0]
            ):
                metadata = Dataset().load(stream.decode("utf-8-sig"), format="csv").dict
            else:
                metadata = Dataset().load(stream).dict
    return metadata


def metadata_from_file(metadata_file):
    format = metadata_file_format(metadata_file)
    if format is None:
        return

    metadata = []
    metadata_set = None

    if format == "excel":
        with open(metadata_file, "rb") as fh:
            metadata_set = Dataset().load(
                fh.read(), format=metadata_file.split(".")[-1]
            )
    else:
        with open(metadata_file, "r", encoding="utf-8-sig") as fh:
            metadata_set = Dataset().load(fh.read(), format=format)

    if metadata_set is not None:
        metadata_set.headers = [
            header.casefold() if header.casefold() == "filename" else header
            for header in metadata_set.headers
        ]
        for row in metadata_set.dict:
            metadata.append(clean_metadata(row))

    return metadata


def metadata_file_format(file_path):
    """Get format used to read the metadata file

    :param file_path: Name of metadata file
    :type file_path: str
    :return: Format of metadata file, csv, tsv, excel, or None
    :rtype: str, None
    """
    if file_path is None:
        return None

    file_type = guess_type(file_path)[0]

    if "csv" in file_type:
        return "csv"
    elif "tab-separated" in file_type:
        return "tsv"
    elif "officedocument" in file_type:
        return "excel"

    return None
