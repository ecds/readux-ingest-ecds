from django.conf import settings
from django.apps import apps
from django.core.exceptions import AppRegistryNotReady

def get_iiif_models():
   try:
      return {
         'Manifest': apps.get_model(settings.IIIF_MANIFEST_MODEL),
         'ImageServer': apps.get_model(settings.IIIF_IMAGE_SERVER_MODEL),
         'RelatedLink': apps.get_model(settings.IIIF_RELATED_LINK_MODEL),
         'Canvas': apps.get_model(settings.IIIF_CANVAS_MODEL),
         'Collection': apps.get_model(settings.IIIF_COLLECTION_MODEL),
      }
   except AppRegistryNotReady:
      return {
         'Manifest': settings.IIIF_MANIFEST_MODEL,
         'ImageServer': settings.IIIF_IMAGE_SERVER_MODEL,
         'RelatedLink': settings.IIIF_RELATED_LINK_MODEL,
         'Canvas': settings.IIIF_CANVAS_MODEL,
         'Collection': settings.IIIF_COLLECTION_MODEL,
      }
