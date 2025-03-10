import re
from datetime import datetime
from django.core.serializers.json import Serializer as JSONSerializer
from iiif.models import Manifest


class Serializer(JSONSerializer):
    def _init_options(self):
        super()._init_options()


def Deserializer(data):
    """
    Deserialize IIIF v3 Manifest
    """
    manifest = {"pid": data["id"].split("/")[-2]}
    relations = {}
    fields = [f.name for f in Manifest._meta.get_fields()]

    for key, value in data.items():
        if key in fields and key != "id":
            if key == "metadata":
                manifest["metadata"] = []
                if isinstance(data["metadata"], list):
                    for attr in data["metadata"]:
                        if isinstance(attr, dict):
                            key = attr["label"]
                            field = re.sub(r"\([^)]*\)", "", key).strip()
                            field = field.replace(" ", "_")
                            field = field.lower()
                            if field in fields:
                                if field == "published_date":
                                    manifest[field] = __parse_date(attr["value"])
                                elif field == "collections" or field == "languages":
                                    relations[field] = attr["value"]
                                else:
                                    manifest[field] = attr["value"]
                            else:
                                manifest["metadata"].append(attr)
            elif isinstance(value, str):
                manifest[key] = value
            elif isinstance(value, dict) and len(value.keys()) > 0:
                if "en" in value.keys():
                    manifest[key] = value["en"][0]
                elif "none" in value.keys():
                    manifest[key] = value["none"][0]
                else:
                    manifest[key] = value[value.keys()[0]]

    return (manifest, relations)


def __parse_date(date):
    parts = [date, 1, 1]
    if ("/") in date:
        parts = parts.split("/")
    elif ("-") in date:
        parts = parts.split("-")

    return datetime(*[int(part) for part in parts])
