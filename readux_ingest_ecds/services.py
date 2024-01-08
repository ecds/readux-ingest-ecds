""" Module of service classes and methods for ingest. """
import itertools
import os
from shutil import move
from PIL import Image
from boto3 import resource
from tablib.core import Dataset
from mimetypes import guess_type
from urllib.parse import unquote, urlparse

from django.conf import settings

from .helpers import get_iiif_models

Manifest = get_iiif_models()['Manifest']
RelatedLink = get_iiif_models()['RelatedLink']

def clean_metadata(metadata):
    """Remove keys that do not align with Manifest fields.

    :param metadata:
    :type metadata: tablib.Dataset
    :return: Dictionary with keys matching Manifest fields
    :rtype: dict
    """
    metadata = {key.casefold().replace(' ', '_'): value for key, value in metadata.items()}
    fields = [f.name for f in get_iiif_models()['Manifest']._meta.get_fields()]
    invalid_keys = []

    for key in metadata.keys():
        if key != 'metadata' and isinstance(metadata[key], list):
            if isinstance(metadata[key][0], dict):
                for meta_key in metadata[key][0].keys():
                    if 'value' in meta_key:
                        metadata[key] = metadata[key][0][meta_key]
            else:
                metadata[key] = ', '.join(metadata[key])
        if key not in fields:
            invalid_keys.append(key)

    for invalid_key in invalid_keys:
        metadata.pop(invalid_key)

    return metadata

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

    # This was giving me a 'django.core.exceptions.AppRegistryNotReady: Models aren't loaded yet' error.
    # Remote = apps.get_model('ingest.remote')

    # Ensure that manifest has an ID before updating the M2M relationship
    manifest.save()
    # if not isinstance(ingest, Remote):
    manifest.refresh_from_db()
    manifest.collections.set(ingest.collections.all())
    # Save again once relationship is set
    manifest.save()

    # if type(ingest, .models.Remote):
    # if isinstance(ingest, Remote):
    #     RelatedLink(
    #         manifest=manifest,
    #         link=ingest.remote_url,
    #         format='application/ld+json'
    #     ).save()

    return manifest

def extract_image_server(canvas):
    """Determines the IIIF image server URL for a given IIIF Canvas

    :param canvas: IIIF Canvas
    :type canvas: dict
    :return: IIIF image server URL
    :rtype: str
    """
    url = urlparse(canvas['images'][0]['resource']['service']['@id'])
    parts = url.path.split('/')
    parts.pop()
    base_path = '/'.join(parts)
    host = url.hostname
    if url.port is not None:
        host = '{h}:{p}'.format(h=url.hostname, p=url.port)
    return '{s}://{h}{p}'.format(s=url.scheme, h=host, p=base_path)

def parse_iiif_v2_manifest(data):
    """Parse IIIF Manifest based on v2.1.1 or the presentation API.
    https://iiif.io/api/presentation/2.1

    :param data: IIIF Presentation v2.1.1 manifest
    :type data: dict
    :return: Extracted metadata
    :rtype: dict
    """
    properties = {}
    manifest_data = []

    if 'metadata' in data:
        manifest_data.append({ 'metadata': data['metadata'] })

        for iiif_metadata in [{prop['label']: prop['value']} for prop in data['metadata']]:
            properties.update(iiif_metadata)

    # Sometimes, the label appears as a list.
    if 'label' in data.keys() and isinstance(data['label'], list):
        data['label'] = ' '.join(data['label'])

    manifest_data.extend([{prop: data[prop]} for prop in data if isinstance(data[prop], str)])

    for datum in manifest_data:
        properties.update(datum)

    uri = urlparse(data['@id'])

    if not uri.query:
        properties['pid'] = uri.path.split('/')[-2]
    else:
        properties['pid'] = uri.query

    if 'description' in data.keys():
        if isinstance(data['description'], list):
            if isinstance(data['description'][0], dict):
                en = [lang['@value'] for lang in data['description'] if lang['@language'] == 'en']
                properties['summary'] = data['description'][0]['@value'] if not en else en[0]
            else:
                properties['summary'] = data['description'][0]
        else:
            properties['summary'] = data['description']

    if 'logo' in properties:
        properties['logo_url'] = properties['logo']
        properties.pop('logo')

    manifest_metadata = clean_metadata(properties)

    return manifest_metadata

def parse_iiif_v2_canvas(canvas):
    """ """
    canvas_id = canvas['@id'].split('/')
    pid = canvas_id[-1] if canvas_id[-1] != 'canvas' else canvas_id[-2]

    service = urlparse(canvas['images'][0]['resource']['service']['@id'])
    resource = unquote(service.path.split('/').pop())

    summary = canvas['description'] if 'description' in canvas.keys() else ''
    label = canvas['label'] if 'label' in canvas.keys() else ''
    return {
        'pid': pid,
        'height': canvas['height'],
        'width': canvas['width'],
        'summary': summary,
        'label': label,
        'resource': resource
    }

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
        if 'zip' in guess_type(file.name)[0]:
            continue
        if 'metadata' in file.name.casefold():
            stream = file.read()
            if 'csv' in guess_type(file.name)[0] or 'tab-separated' in guess_type(file.name)[0]:
                metadata = Dataset().load(stream.decode('utf-8-sig'), format='csv').dict
            else:
                metadata = Dataset().load(stream).dict
    return metadata

def metadata_from_file(metadata_file):
    format = metadata_file_format(metadata_file)
    if format is None:
        return

    metadata = None

    if format == 'excel':
        with open(metadata_file, 'rb') as fh:
            metadata = Dataset().load(fh.read(), format=metadata_file.split('.')[-1])
    else:
        with open(metadata_file, 'r', encoding="utf-8-sig") as fh:
            metadata = Dataset().load(fh.read(), format=format)

    if metadata is not None:
        metadata = clean_metadata(metadata.dict[0])

    return metadata

def get_associated_meta(all_metadata, file):
    """
    Associate metadata with filename.
    :return: If a matching filename is found, returns the row as dict,
        with generated pid. Otherwise, returns {}.
    :rtype: dict
    """
    file_meta = {}
    extless_filename = file.name[0:file.name.rindex('.')]
    for meta_dict in all_metadata:
        for key, val in meta_dict.items():
            if key.casefold() == 'filename':
                metadata_found_filename = val
        # Match filename column, case-sensitive, against filename
        if metadata_found_filename and metadata_found_filename in (extless_filename, file.name):
            file_meta = meta_dict
    return file_meta

def lowercase_first_line(iterator):
    """Lowercase the first line of a text file (such as the header row of a CSV)"""
    return itertools.chain(
        # ignore unicode characters, set lowercase, and strip whitespace
        [next(iterator).encode('ascii', 'ignore').decode().casefold().strip()], iterator
    )

def is_image(file_path):
    """Check if file is expected type for image files

    :param file_path: Name of file to check
    :type file_path: str
    :return: Bool if file type is an image.
    :rtype: bool
    """
    return file_path is not None and 'images' in file_path and 'image' in guess_type(file_path)[0]

def is_ocr(file_path):
    """Check if file is expected type for OCR files

    :param file_path: Name of file to check
    :type file_path: str
    :return: Bool if file type matches OCR file types.
    :rtype: bool
    """
    ocr_file_types = ['text', 'xml','json','html', 'hocr', 'tsv']
    return file_path is not None and 'ocr' in file_path and any(file_path.endswith(ocr_type) for ocr_type in ocr_file_types)

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

    if 'csv' in file_type:
        return 'csv'
    elif 'tab-separated' in file_type:
        return 'tsv'
    elif 'officedocument' in file_type:
        return 'excel'

    return None

def is_junk(file_path):
    """Check if a file should be considered junk

    :param file_path: File name to check
    :type file_path: str
    :return: True if file name starts with special char
    :rtype: bol
    """
    return file_path.startswith('.') or file_path.startswith('~') or file_path.startswith('__') or file_path.endswith('/') or file_path == ''

def move_image_file(ingest, file_path):
    """ Move files to directory where they processed.
    Add the Manifest pid to the file name if not already there.

    :param ingest: Ingest object
    :type ingest: _type_
    :param file_path: Absolute path of tmp file
    :type file_path: str
    :return: File name file to be processed
    :rtype: str
    """
    base_name = os.path.basename(file_path)
    if ingest.manifest.pid not in base_name:
        base_name = f'{ingest.manifest.pid}_{base_name}'
    move(file_path, os.path.join(settings.INGEST_PROCESSING_DIR, base_name))
    return base_name

def move_ocr_file(ingest, file_path):
    """ Move OCR file to where it belongs.

    :param ingest: Ingest object
    :type ingest: _type_
    :param file_path: Absolute path of tmp file
    :type file_path: str
    """
    base_name = os.path.basename(file_path)
    if ingest.manifest.pid not in base_name:
        base_name = f'{ingest.manifest.pid}_{base_name}'
    move(file_path, os.path.join(ingest.ocr_directory, base_name))

def upload_trigger_file(trigger_file):
    """
    Upload trigger file to S3. The file contains a list of images being ingested.
    The file will be picked up by an AWS lambda function and the images will be
    converted to ptiffs.

    :param trigger_file: Absolute path to trigger file.
    :type trigger_file: str
    """
    s3 = resource('s3')
    s3.Bucket(settings.INGEST_TRIGGER_BUCKET).upload_file(trigger_file, os.path.basename(trigger_file))

def canvas_dimensions(image_name):
    """Get canvas dimensions

    :param image_name: File name without extension of image file.
    :type image_name: str
    :return: 2-tuple containing width and height (in pixels)
    :rtype: tuple
    """
    original_image = [img for img in os.listdir(settings.INGEST_PROCESSING_DIR) if img.startswith(image_name)]
    if len(original_image) > 0:
        return Image.open(os.path.join(settings.INGEST_PROCESSING_DIR, original_image[0])).size
    return (0,0)
