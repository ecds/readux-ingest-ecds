import os
from django.core.files.storage import FileSystemStorage
from django.conf import settings

class TmpStorage(FileSystemStorage):
    location = settings.INGEST_TMP_DIR

    def get_available_name(self, name: str, max_length: int | None = ...) -> str:
        if self.exists(name):
            os.remove(os.path.join(settings.INGEST_TMP_DIR, name))
        return name
