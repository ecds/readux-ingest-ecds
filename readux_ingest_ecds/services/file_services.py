""" Module of service methods for ingest files. """

import os
from moto import mock_aws
from shutil import move
from mimetypes import guess_type
from PIL import Image
from boto3 import resource

from django.conf import settings

from readux_ingest_ecds.helpers import get_iiif_models

Manifest = get_iiif_models()["Manifest"]
RelatedLink = get_iiif_models()["RelatedLink"]


def is_image(file_path):
    """Check if file is expected type for image files

    :param file_path: Name of file to check
    :type file_path: str
    :return: Bool if file type is an image.
    :rtype: bool
    """
    return (
        file_path is not None
        and "images" in file_path
        and "image" in guess_type(file_path)[0]
    )


def is_ocr(file_path):
    """Check if file is expected type for OCR files

    :param file_path: Name of file to check
    :type file_path: str
    :return: Bool if file type matches OCR file types.
    :rtype: bool
    """
    ocr_file_types = ["txt", "xml", "json", "html", "hocr", "tsv"]
    return (
        file_path is not None
        and "ocr" in file_path
        and any(file_path.endswith(ocr_type) for ocr_type in ocr_file_types)
    )


def is_junk(file_path):
    """Check if a file should be considered junk

    :param file_path: File name to check
    :type file_path: str
    :return: True if file name starts with special char
    :rtype: bol
    """
    return (
        file_path.startswith(".")
        or file_path.startswith("~")
        or file_path.startswith("__")
        or file_path.endswith("/")
        or file_path == ""
    )


def move_image_file(ingest, file_path):
    """Move files to directory where they processed.
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
        base_name = f"{ingest.manifest.pid}_{base_name}"
    move(file_path, os.path.join(settings.INGEST_PROCESSING_DIR, base_name))
    return base_name


def move_ocr_file(ingest, file_path):
    """Move OCR file to where it belongs.

    :param ingest: Ingest object
    :type ingest: _type_
    :param file_path: Absolute path of tmp file
    :type file_path: str
    """
    base_name = os.path.basename(file_path)
    if ingest.manifest.pid not in base_name:
        base_name = f"{ingest.manifest.pid}_{base_name}"
    move(file_path, os.path.join(ingest.ocr_directory, base_name))


def divide_chunks(item_list, chunk_size=10):
    """
    Divide list of files into smaller chunks for processing.
    :param file_list: List of images to ingest.
    :param chunk_size: Number of items in each chunk. Defaults to 10.
    :type file_list: list
    """
    for item in range(0, len(item_list), chunk_size):
        yield item_list[item : item + chunk_size]


def upload_trigger_file(trigger_file):
    """
    Upload trigger file to S3. The file contains a list of images being ingested.
    The file will be picked up by an AWS lambda function and the images will be
    converted to ptiffs.

    :param trigger_file: Absolute path to trigger file.
    :type trigger_file: str
    """
    s3 = resource("s3")
    with open(trigger_file, "r", encoding="utf-8") as t_file:
        images = t_file.read().splitlines()
    chunked_images = list(divide_chunks(images))
    for idx, chunk in enumerate(chunked_images):
        chunked_trigger_file = trigger_file.replace(".txt", f"-{idx}.txt")
        for image in chunk:
            with open(chunked_trigger_file, "a", encoding="utf-8") as t_file:
                t_file.write(f"{image}\n")
        s3.Bucket(settings.INGEST_TRIGGER_BUCKET).upload_file(
            chunked_trigger_file, os.path.basename(chunked_trigger_file)
        )


def canvas_dimensions(image_name):
    """Get canvas dimensions

    :param image_name: File name without extension of image file.
    :type image_name: str
    :return: 2-tuple containing width and height (in pixels)
    :rtype: tuple
    """
    original_image = [
        img
        for img in os.listdir(settings.INGEST_PROCESSING_DIR)
        if img.startswith(image_name)
    ]
    if len(original_image) > 0:
        return Image.open(
            os.path.join(settings.INGEST_PROCESSING_DIR, original_image[0])
        ).size
    return (0, 0)


def s3_copy(source, pid):
    """Copy S3 objects to ingest

    Args:
        source (str): Source bucket name
        pid (str): PID for volume being ingested

    Returns:
        list[str]: List of copied image files for volume
    """
    s3 = resource("s3")
    destination_bucket = s3.Bucket(settings.INGEST_BUCKET)
    source_bucket = s3.Bucket(source)

    keys_to_copy = [
        str(obj.key)
        for obj in source_bucket.objects.all()
        if pid in obj.key and not str(obj.key).endswith("/")
    ]

    images = []
    ocr = []
    for key in keys_to_copy:
        copy_source = {"Bucket": source, "Key": key}
        filename = os.path.basename(key)
        if pid not in filename:
            filename = f"{pid}_{filename}"
        if "image" in guess_type(key)[0] and "images" in key.casefold():
            images.append(filename)
            destination_bucket.copy(
                copy_source, f"{settings.INGEST_STAGING_PREFIX}/{filename}"
            )
        elif "ocr" in key.casefold() and is_ocr(f"ocr_{key}"):
            ocr_path = f"{settings.INGEST_OCR_PREFIX}/{pid}/{filename}"
            ocr.append(ocr_path)
            destination_bucket.copy(copy_source, ocr_path)

    images.sort()
    return (images, ocr)
