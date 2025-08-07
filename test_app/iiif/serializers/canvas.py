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

    annotations = []

    if "@context" in data.keys() and "2/context.json" in data["@context"]:
        if "otherContent" in data.keys():
            annotations = [
                anno_list["@id"]
                for anno_list in data["otherContent"]
                if "AnnotationList" in anno_list["@type"]
            ]
        return (
            {
                "pid": data["@id"].split("/")[-2],
                "width": data["width"],
                "height": data["height"],
            },
            annotations,
        )

    if "annotations" in data.keys():
        annotations = [
            anno_page["id"]
            for anno_page in data["annotations"]
            if "AnnotationPage" in anno_page["type"]
        ]

    return (
        {
            "pid": data["id"].split("/")[-2],
            "width": data["width"],
            "height": data["height"],
        },
        annotations,
    )
