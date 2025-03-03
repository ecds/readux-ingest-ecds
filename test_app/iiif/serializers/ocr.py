from bs4 import BeautifulSoup
from django.core.serializers.json import Serializer as JSONSerializer
from iiif.models import Canvas


class Serializer(JSONSerializer):
    def _init_options(self):
        super()._init_options()


def Deserializer(data):
    """
    Deserialize IIIF v3 Manifest
    """
    content = ""
    if isinstance(data["body"], list):
        for body in data["body"]:
            if body["type"] == "TextualBody":
                content = body["value"]
    elif isinstance(data["body"], dict):
        if data["body"]["type"] == "TextualBody":
            content = data["body"]["value"]
    soup = BeautifulSoup(content, "html.parser")
    selector = data["target"]["selector"]["value"].split(":")[-1]
    x, y, w, h = [int(n) for n in selector.split(",")]
    return {
        "content": soup.get_text(separator=" ", strip=True),
        "canvas": Canvas.objects.get(pid=data["target"]["source"].split("/")[-1]),
        "w": w,
        "h": h,
        "x": x,
        "y": y,
    }
