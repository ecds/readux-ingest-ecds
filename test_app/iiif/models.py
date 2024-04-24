from django.db import models
from uuid import uuid4
from django.contrib.auth.models import AbstractUser

class Collection(models.Model):
    pid = models.UUIDField(primary_key=True, default=uuid4, editable=True)

class ImageServer(models.Model):
    server_base = models.CharField(max_length=255)
    storage_service = models.CharField(max_length=25, default='local')

class Manifest(models.Model):
    pid = models.CharField(max_length=255, default=uuid4, editable=True)
    image_server = models.ForeignKey(ImageServer, on_delete=models.DO_NOTHING, null=True)
    collections = models.ManyToManyField(Collection, blank=True, related_name='manifests')
    label = models.TextField(null=True, blank=True)
    author = models.TextField(null=True, blank=True)
    published_city = models.TextField(null=True, blank=True)
    publisher = models.TextField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    @property
    def related_links(self):
        """List of links for IIIF v2 'related' field.

        :return: List of links related to Manifest
        :rtype: list
        """
        links = [
            {
                "@id": link.link,
                "format": link.format,
            } if link.format else link.link
            for link in self.relatedlink_set.all()
        ]
        links.append({
            "@id": f'/volume/{self.pid}/page/all',
            "format": "text/html"
        })
        return links


class Canvas(models.Model):
    pid = models.CharField(max_length=255, primary_key=True, default=uuid4, editable=True)
    # image_server = models.ForeignKey(ImageServer, on_delete=models.DO_NOTHING, null=True)
    position = models.IntegerField()
    width = models.IntegerField(default=0)
    height = models.IntegerField(default=0)
    ocr_file_path = models.CharField(max_length=500, null=True, blank=True)
    manifest = models.ForeignKey(Manifest, on_delete=models.DO_NOTHING)
    preferred_ocr = (
        ('word', 'word'),
        ('line', 'line'),
        ('both', 'both')
    )
    # TODO: move this to the manifest level.
    default_ocr = models.CharField(max_length=30, choices=preferred_ocr, default="word")
    image_server = models.ForeignKey(ImageServer, on_delete=models.DO_NOTHING, null=True)

    def before_save(self):
        return True

class OCR(models.Model):
    OCR = 'cnt:ContentAsText'
    TEXT = 'dctypes:Text'
    TYPE_CHOICES = (
        (OCR, 'ocr'),
        (TEXT, 'text')
    )

    canvas = models.ForeignKey(Canvas, on_delete=models.DO_NOTHING)
    x = models.IntegerField(default=0)
    y = models.IntegerField(default=0)
    w = models.IntegerField(default=0)
    h = models.IntegerField(default=0)
    order = models.IntegerField(default=0)
    content = models.TextField(blank=True, null=True, default=' ')
    resource_type = models.CharField(max_length=50, choices=TYPE_CHOICES, default=TEXT)

    def set_span_element(self):
        return True

class RelatedLink(models.Model):
    """ Links to related resources """
    manifest = models.ForeignKey(Manifest, on_delete=models.CASCADE)
    link = models.TextField(blank=True, null=True, default=' ')
    format = models.TextField(blank=True, null=True, default='text/html')
    is_structured_data = models.BooleanField(default=False)

class User(AbstractUser):
    name = models.CharField(blank=True, max_length=255)
