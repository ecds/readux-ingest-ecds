from django.db import models
from uuid import uuid4
from django.contrib.auth.models import AbstractUser

class Collection(models.Model):
    pid = models.UUIDField(primary_key=True, default=uuid4, editable=True)

class ImageServer(models.Model):
    server_base = models.CharField(max_length=255)

class Manifest(models.Model):
    pid = models.CharField(max_length=255, primary_key=True, default=uuid4, editable=True)
    image_server = models.ForeignKey(ImageServer, on_delete=models.DO_NOTHING, null=True)
    collections = models.ManyToManyField(Collection, blank=True, related_name='manifests')

class Canvas(models.Model):
    pid = models.CharField(max_length=255, primary_key=True, default=uuid4, editable=True)
    image_server = models.ForeignKey(ImageServer, on_delete=models.DO_NOTHING, null=True)
    position = models.IntegerField()
    width = models.IntegerField(default=0)
    height = models.IntegerField(default=0)
    ocr_file_path = models.CharField(max_length=500, null=True, blank=True)
    manifest = models.ForeignKey(Manifest, on_delete=models.DO_NOTHING)

class RelatedLink(models.Model):
    """ Links to related resources """
    manifest = models.ForeignKey(Manifest, on_delete=models.CASCADE)

class User(AbstractUser):
    name = models.CharField(blank=True, max_length=255)
