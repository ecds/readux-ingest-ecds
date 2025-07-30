import json
from django.core.serializers.json import Serializer as JSONSerializer


class Serializer(JSONSerializer):
    def _init_options(self):
        super()._init_options()


def Deserializer(data):
    """
    Deserialize IIIF v3 Manifest
    """
    if isinstance(data, str):
        data = json.loads(data)

    if "@context" in data.keys() and "2/context.json" in data["@context"]:
        return {
            "pid": data["@id"].split("/")[-2],
            "width": data["width"],
            "height": data["height"],
        }

    return {
        "pid": data["id"].split("/")[-2],
        "width": data["width"],
        "height": data["height"],
    }
