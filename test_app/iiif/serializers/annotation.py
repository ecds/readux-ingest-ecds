import json
from re import findall
from bs4 import BeautifulSoup
from django.core.serializers.json import Serializer as JSONSerializer
from iiif.models import Canvas, User, AnnotationPurpose, Annotation


class Serializer(JSONSerializer):
    def _init_options(self):
        super()._init_options()


def Deserializer(data):
    """
    Deserialize IIIF Annotations
    """
    if isinstance(data, str):
        data = json.loads(data)

    if "@context" in data.keys() and "2/context.json" in data["@context"]:
        return __v2(data)

    return __v3(data)


def __v2(data):
    annotation = {
        "id": data["@id"],
        "owner": User.objects.get(name=data["annotatedBy"]["name"]),
    }
    tags = []

    if data["motivation"] == "oa:commenting":
        annotation["motivation"] = AnnotationPurpose("CM")

    if data["motivation"] == "oa:painting":
        annotation["motivation"] = AnnotationPurpose("PT")

    source_parts = data["on"]["full"].split("/")
    canvas_pid = source_parts[-1] if source_parts[-1] != "canvas" else source_parts[-2]
    annotation["canvas"] = Canvas.objects.get(pid=canvas_pid)

    resources = (
        data["resource"] if isinstance(data["resource"], list) else [data["resource"]]
    )

    for resource in resources:
        if resource["@type"] == "cnt:ContentAsText":
            annotation["resource_type"] = Annotation.OCR
        if resource["@type"] == "dctypes:Text":
            annotation["resource_type"] = Annotation.TEXT

        if resource["@type"] == "oa:Tag":
            tags.append(resource["chars"])
        else:
            annotation["content"] = resource["chars"]
            soup = BeautifulSoup(resource["chars"], "html.parser")
            annotation["raw_content"] = soup.get_text(separator=" ", strip=True)

    annotation["x"], annotation["y"], annotation["w"], annotation["h"] = [
        float(n) for n in data["on"]["selector"]["value"].split("=")[-1].split(",")
    ]

    if data["on"]["selector"]["item"]["@type"] == "oa:SvgSelector":
        annotation["svg"] = data["on"]["selector"]["item"]["value"]

    if data["on"]["selector"]["item"]["@type"] == "RangeSelector":
        annotation["start_selector"], _ = Annotation.objects.get_or_create(
            id=findall(
                r"([A-Za-z0-9\-]+)",
                data["on"]["selector"]["item"]["startSelector"]["value"],
            )[-1]
        )
        annotation["end_selector"], _ = Annotation.objects.get_or_create(
            id=findall(
                r"([A-Za-z0-9\-]+)",
                data["on"]["selector"]["item"]["endSelector"]["value"],
            )[-1]
        )
        annotation["start_offset"] = data["on"]["selector"]["item"]["startSelector"][
            "refinedBy"
        ]["start"]

        annotation["end_offset"] = data["on"]["selector"]["item"]["endSelector"][
            "refinedBy"
        ]["end"]

    return (
        annotation,
        tags,
    )


def __v3(data):
    content = ""
    if isinstance(data["body"], list):
        for body in data["body"]:
            if body["purpose"] == "TextualBody":
                content = (body["value"],)

    elif isinstance(data["body"], dict):
        if data["body"]["type"] == "TextualBody":
            content = data["body"]["value"]
    soup = BeautifulSoup(content, "html.parser")
    selector = data["target"]["selector"]["value"].split(":")[-1]
    x, y, w, h = [int(n) for n in selector.split(",")]
    return (
        {
            "content": soup.get_text(separator=" ", strip=True),
            "canvas": Canvas.objects.get(pid=data["target"]["source"].split("/")[-1]),
            "w": w,
            "h": h,
            "x": x,
            "y": y,
        },
        [],
    )
