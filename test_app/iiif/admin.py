from django.contrib import admin
from .models import Manifest


class ManifestAdmin(admin.ModelAdmin):
    pass


admin.site.register(Manifest, ManifestAdmin)
