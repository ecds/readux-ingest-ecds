import json
from re import findall
from bs4 import BeautifulSoup
from django.core.serializers.json import Serializer as JSONSerializer
from django.core.serializers import deserialize


class Serializer(JSONSerializer):
    def _init_options(self):
        super()._init_options()


def Deserializer(data):
    """Deserialize IIIF V2 Annotation List"""
    if isinstance(data, str):
        data = json.loads(data)

    if "@context" in data.keys() and "2/context.json" in data["@context"]:
        return [deserialize("ocr", annotation) for annotation in data["resources"]]

    return [deserialize("ocr", annotation) for annotation in data["items"]]
