import re
from datetime import datetime
from django.core.serializers.json import Serializer as JSONSerializer
from iiif.models import Manifest


def parse_fields(attribute):
    """Get attributes from V2 Manifest

    Args:
        attribute (tuple): _description_
    """
    key, value = attribute
    fields = [field.name for field in Manifest._meta.get_fields()]
    field = re.sub(r"\([^)]*\)", "", key).strip()
    field = field.replace(" ", "_")
    field = field.lower()
    if field == "publication_date":
        return {"published_date": value}
    if field == "place_of_publication":
        return {"published_city": value}
    if field in fields:
        return {field: value}
    return None


class Serializer(JSONSerializer):
    def _init_options(self):
        super()._init_options()


def Deserializer(data):
    """
    Deserialize IIIF Manifest
    """
    fields = [f.name for f in Manifest._meta.get_fields()]

    if "@context" in data and "2/context.json" in data["@context"]:
        relations = {
            "collections": data["within"],
            "canvases": [
                canvas["@id"].split("/")[-1]
                for canvas in data["sequences"][0]["canvases"]
            ],
        }

        if "seeAlso" in data.keys():
            relations["related_links"] = data["seeAlso"]

        manifest = {
            "pid": data["@id"].split("/")[-2],
            "summary": data["description"],
            "metadata": [],
        }

        try:
            metadata = data.pop("metadata")
            for metadatum in metadata:
                attribute = parse_fields((metadatum["label"], metadatum["value"]))
                if attribute is not None:
                    manifest = {**manifest, **attribute}
                else:
                    manifest["metadata"].append(metadatum)
        except KeyError:
            # Maybe no metadata
            pass

        for key, value in data.items():
            attribute = parse_fields((key, value))
            if attribute is not None:
                manifest = {**manifest, **attribute}

        return (manifest, relations)

    manifest = {"pid": data["id"].split("/")[-2]}
    relations = {}

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
