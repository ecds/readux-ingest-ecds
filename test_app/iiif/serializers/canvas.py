import re
from django.core.serializers.json import Serializer as JSONSerializer


class Serializer(JSONSerializer):
    def _init_options(self):
        super()._init_options()


def Deserializer(data):
    """
    Deserialize IIIF v3 Manifest
    """
    return {
        "pid": data["id"].split("/")[-2],
        "width": data["width"],
        "height": data["height"],
    }
