import json
import enum
from uuid import uuid4
from bs4 import BeautifulSoup
import requests
from django.utils import timezone
from django.utils.functional import Promise
from django.db import models
from django.core.serializers import deserialize as _deserialize, serialize as _serialize
from django.contrib.auth.models import AbstractUser
from .utils import encode_noid


class IiifBase(models.Model):
    class Meta:
        abstract = True

    @property
    def serializer(self):
        raise NotImplementedError("serializer() must be implemented in SubClass.")

    @classmethod
    def serialize(self, version="v3"):
        return json.loads(_serialize(self.serializer, self, version=version))

    @classmethod
    def deserialize(self, url=None):
        if url is None:
            # Raise some error
            pass

        response = requests.get(url)
        data = response.json()
        obj = _deserialize(self.serializer, data)

        for key, value in obj.items():
            setattr(self, key, value)

        self.save(update_fields=obj.keys())


class ChoicesMeta(enum.EnumMeta):
    """A metaclass for creating a enum choices."""

    def __new__(metacls, classname, bases, classdict, **kwds):
        labels = []
        for key in classdict._member_names:
            value = classdict[key]
            if (
                isinstance(value, (list, tuple))
                and len(value) > 1
                and isinstance(value[-1], (Promise, str))
            ):
                *value, label = value
                value = tuple(value)
            else:
                label = key.replace("_", " ").title()
            labels.append(label)
            # Use dict.__setitem__() to suppress defenses against double
            # assignment in enum's classdict.
            dict.__setitem__(classdict, key, value)
        cls = super().__new__(metacls, classname, bases, classdict, **kwds)
        cls._value2label_map_ = dict(zip(cls._value2member_map_, labels))
        # Add a label property to instances of enum which uses the enum member
        # that is passed in as "self" as the value to use when looking up the
        # label in the choices.
        cls.label = property(lambda self: cls._value2label_map_.get(self.value))
        cls.do_not_call_in_templates = True
        return enum.unique(cls)

    def __contains__(cls, member):
        if not isinstance(member, enum.Enum):
            # Allow non-enums to match against member values.
            return any(x.value == member for x in cls)
        return super().__contains__(member)

    @property
    def names(cls):
        empty = ["__empty__"] if hasattr(cls, "__empty__") else []
        return empty + [member.name for member in cls]

    @property
    def choices(cls):
        empty = [(None, cls.__empty__)] if hasattr(cls, "__empty__") else []
        return empty + [(member.value, member.label) for member in cls]

    @property
    def labels(cls):
        return [label for _, label in cls.choices]

    @property
    def values(cls):
        return [value for value, _ in cls.choices]


class Choices(enum.Enum, metaclass=ChoicesMeta):
    """Class for creating enumerated choices."""

    def __str__(self):
        """
        Use value when cast to str, so that Choices set as model instance
        attributes are rendered as expected in templates and similar contexts.
        """
        return str(self.value)


class TextChoices(str, Choices):
    """Class for creating enumerated string choices."""

    def _generate_next_value_(name, start, count, last_values):
        return name


class AnnotationSelector(TextChoices):
    FragmentSelector = "FR"
    CssSelector = "CS"
    XPathSelector = "XP"
    TextQuoteSelector = "TQ"
    TextPositionSelector = "TP"
    DataPositionSelector = "DP"
    SvgSelector = "SV"
    RangeSelector = "RG"


class AnnotationPurpose(TextChoices):
    assessing = "AS"
    bookmarking = "BM"
    classifying = "CL"
    commenting = "CM"
    describing = "DS"
    editing = "ED"
    highlighting = "HL"
    identifying = "ID"
    linking = "LK"
    moderating = "MO"
    painting = "PT"
    questioning = "QT"
    replying = "RE"
    supplementing = "SP"
    tagging = "TG"


class Language(models.Model):
    """Model to store language names and codes for multiple choice fields"""

    code = models.CharField(max_length=16, unique=True)
    name = models.CharField(max_length=255)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        """String representation of the language"""
        return str(self.name)


class Collection(models.Model):
    pid = models.UUIDField(primary_key=True, default=uuid4, editable=True)
    label = models.TextField(null=True, blank=True)


class ImageServer(models.Model):
    server_base = models.CharField(max_length=255)
    storage_service = models.CharField(max_length=25, default="local")


class Manifest(models.Model):
    pid = models.CharField(max_length=255, default=uuid4, editable=True)
    image_server = models.ForeignKey(
        ImageServer, on_delete=models.DO_NOTHING, null=True
    )
    collections = models.ManyToManyField(
        Collection, blank=True, related_name="manifests"
    )
    label = models.TextField(null=True, blank=True)
    author = models.TextField(null=True, blank=True)
    published_city = models.TextField(null=True, blank=True)
    published_date = models.CharField(
        "Published date (display)",
        max_length=255,
        null=True,
        blank=True,
        help_text="Used for display only.",
    )
    publisher = models.TextField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    languages = models.ManyToManyField(
        Language, help_text="Languages present in the manifest.", blank=True
    )
    start_canvas = models.ForeignKey(
        "Canvas",
        on_delete=models.SET_NULL,
        related_name="start_canvas",
        blank=True,
        null=True,
    )

    @property
    def related_links(self):
        """List of links for IIIF v2 'related' field.

        :return: List of links related to Manifest
        :rtype: list
        """
        links = [
            (
                {
                    "@id": link.link,
                    "format": link.format,
                }
                if link.format
                else link.link
            )
            for link in self.relatedlink_set.all()
        ]
        links.append({"@id": f"/volume/{self.pid}/page/all", "format": "text/html"})
        return links

    def get_volume_url(self):
        return "example.org"


class Canvas(models.Model):
    pid = models.CharField(max_length=255, default=uuid4, editable=True)
    # image_server = models.ForeignKey(ImageServer, on_delete=models.DO_NOTHING, null=True)
    position = models.IntegerField()
    width = models.IntegerField(default=0)
    height = models.IntegerField(default=0)
    ocr_file_path = models.CharField(max_length=500, null=True, blank=True)
    manifest = models.ForeignKey(Manifest, on_delete=models.DO_NOTHING)
    preferred_ocr = (("word", "word"), ("line", "line"), ("both", "both"))
    # TODO: move this to the manifest level.
    default_ocr = models.CharField(max_length=30, choices=preferred_ocr, default="word")
    image_server = models.ForeignKey(
        ImageServer, on_delete=models.DO_NOTHING, null=True
    )
    resource = models.TextField(blank=True, null=True)

    def before_save(self):
        return True


class OCR(models.Model):
    OCR = "cnt:ContentAsText"
    TEXT = "dctypes:Text"
    TYPE_CHOICES = ((OCR, "ocr"), (TEXT, "text"))

    canvas = models.ForeignKey(Canvas, on_delete=models.DO_NOTHING)
    x = models.IntegerField(default=0)
    y = models.IntegerField(default=0)
    w = models.IntegerField(default=0)
    h = models.IntegerField(default=0)
    order = models.IntegerField(default=0)
    content = models.TextField(blank=True, null=True, default=" ")
    resource_type = models.CharField(max_length=50, choices=TYPE_CHOICES, default=TEXT)

    def set_span_element(self):
        return True


class RelatedLink(models.Model):
    """Links to related resources"""

    manifest = models.ForeignKey(Manifest, on_delete=models.CASCADE)
    link = models.TextField(blank=True, null=True, default=" ")
    format = models.TextField(blank=True, null=True, default="text/html")
    is_structured_data = models.BooleanField(default=False)


class User(AbstractUser):
    name = models.CharField(blank=True, max_length=255)


class IiifBase(models.Model):
    """Abstract model class for IIIF models"""

    id = models.UUIDField(primary_key=True, default=uuid4, editable=True)
    pid = models.CharField(
        max_length=255,
        default=encode_noid,
        blank=False,
        help_text="Unique ID. Do not use _'s or spaces in the pid.",
    )
    label = models.CharField(max_length=1000, default="")
    created_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    modified_at = models.DateTimeField(auto_now=True, blank=True, null=True)

    dup_pids = None

    @property
    def created_at_iso(self):
        """
        :return: Date object was created formatted like JavaScript's ISO date.
        :rtype: str
        """
        return self.__js_isoformat(self.created_at)

    @property
    def modified_at_iso(self):
        """
        :return: Date object was modified formatted like JavaScript's ISO date.
        :rtype: str
        """
        return self.__js_isoformat(self.modified_at)

    @property
    def v2_baseurl(self):
        """Convenience method to provide the base URL for a manifest."""
        return f"https://test.io/iiif/v2/{self.pid}"

    @property
    def v3_baseurl(self):
        """Convenience method to provide the base URL for a manifest."""
        return f"https://test.io/iiif/v3/{self.pid}"

    def save(self, *args, **kwargs):  # pylint: disable = arguments-differ
        self.clean_pid()

        super().save(*args, **kwargs)

    @staticmethod
    def __js_isoformat(date):
        return (
            date.astimezone(timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )

    def clean_pid(self):
        """Cantaloupe is generally configured substitute a slash (/)
        with an underscore (_) for the file path of the images."""
        self.pid = self.pid.replace("_", "-")

    class Meta:  # pylint: disable=too-few-public-methods, missing-class-docstring
        abstract = True


class AbstractAnnotation(IiifBase):
    """Base class for IIIF annotations."""

    OCR = "cnt:ContentAsText"
    TEXT = "dctypes:Text"
    TYPE_CHOICES = ((OCR, "ocr"), (TEXT, "text"))

    OA_COMMENTING = "oa:commenting"
    SC_PAINTING = "sc:painting"
    MOTIVATION_CHOICES = ((OA_COMMENTING, "commenting"), (SC_PAINTING, "painting"))

    PLAIN = "text/plain"
    HTML = "text/html"
    FORMAT_CHOICES = ((PLAIN, "plain text"), (HTML, "html"))

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    x = models.IntegerField(default=0)
    y = models.IntegerField(default=0)
    w = models.IntegerField(default=0)
    h = models.IntegerField(default=0)
    order = models.IntegerField(default=0)
    content = models.TextField(blank=True, null=True, default=" ")
    raw_content = models.TextField(blank=True, null=True, default=" ")
    resource_type = models.CharField(max_length=50, choices=TYPE_CHOICES, default=TEXT)
    # TODO: replace
    motivation = models.CharField(
        max_length=50, choices=MOTIVATION_CHOICES, default=SC_PAINTING
    )
    purpose = models.CharField(
        max_length=2, choices=AnnotationPurpose.choices, default=AnnotationPurpose("SP")
    )
    primary_selector = models.CharField(
        max_length=2,
        choices=AnnotationSelector.choices,
        default=AnnotationSelector("FR"),
    )
    format = models.CharField(max_length=20, choices=FORMAT_CHOICES, default=PLAIN)
    canvas = models.ForeignKey("Canvas", on_delete=models.CASCADE, null=True)
    language = models.CharField(max_length=10, default="en")
    owner = models.ForeignKey(User, on_delete=models.CASCADE, blank=True, null=True)
    oa_annotation = models.JSONField(default=dict, blank=False)
    # TODO: Should we keep this for annotations from Mirador, or just get rid of it?
    svg = models.TextField(blank=True, null=True)
    style = models.CharField(max_length=1000, blank=True, null=True)
    item = None

    ordering = ["order"]

    @property
    def content_is_html(self):
        """
        Is the content of the annotation HTML?

        :return: True if HTML tags are present in the content.
        :rtype: bool
        """
        return bool(BeautifulSoup(self.content, "html.parser").find())

    @property
    def fragment(self):
        """Web Annotation fragment selector.
        https://www.w3.org/TR/annotation-model/#fragment-selector

        Returns:
            str: FragmentSelector
        """
        return f"xywh=pixel:{self.x},{self.y},{self.w},{self.h}"

    def __str__(self):
        return str(self.pk)

    class Meta:  # pylint: disable=too-few-public-methods, missing-class-docstring
        abstract = True


class Annotation(AbstractAnnotation):
    """Model class for IIIF annotations."""

    def save(self, *args, **kwargs):
        self.set_span_element()
        super().save(*args, **kwargs)

    class Meta:  # pylint: disable=too-few-public-methods, missing-class-docstring
        ordering = ["order"]
        abstract = False

    # @receiver(signals.pre_save, sender=Annotation)
    def set_span_element(self):
        """
        Post save function to wrap the OCR content in a `<span>` to be overlaid in OpenSeadragon.

        :param sender: Class calling function
        :type sender: apps.iiif.annotations.models.Annotation
        :param instance: Annotation object
        :type instance: apps.iiif.annotations.models.Annotation
        """
        # Guard for when an OCR annotation gets re-saved.
        # Without this, it would nest the current span in a new span.
        if self.content.startswith("<span"):
            self.content = BeautifulSoup(self.content, "html.parser").span.string
        if self.resource_type in (self.OCR,):
            # pylint: disable=unsupported-assignment-operation
            self.oa_annotation["annotatedBy"] = {"name": "ocr"}
            # pylint: enable=unsupported-assignment-operation
            self.owner = User.objects.get_or_create(username="ocr", name="OCR")[0]
            character_count = len(self.content)
            # 1.6 is a "magic number" that seems to work pretty well ¯\_(ツ)_/¯
            font_size = self.h / 1.6
            # Assuming a character's width is half the height. This was my first guess.
            # This should give us how long all the characters will be.
            string_width = (font_size / 2) * character_count
            letter_spacing = 0
            relative_letter_spacing = 0
            if self.w > 0:
                # And this is what we're short.
                space_to_fill = self.w - string_width
                # Divide up the space to fill and space the letters.
                letter_spacing = space_to_fill / character_count
                # Percent of letter spacing of overall width.
                # This is used by OpenSeadragon. OSD will update the letter spacing relative to
                # the width of the overlaid element when someone zooms in and out.
                relative_letter_spacing = letter_spacing / self.w
            # pylint: disable=line-too-long
            self.content = f"<span id='{self.pk}' class='anno-{self.pk}' data-letter-spacing='{str(relative_letter_spacing)}'>{self.content}</span>"
            self.style = f".anno-{self.pk}: {{ height: {self.h}px; width: {self.w}px; font-size: {font_size}px; letter-spacing: {letter_spacing}px;}}"
            # pylint: enable=line-too-long


class UserAnnotation(models.Model):
    OCR = "cnt:ContentAsText"
    TEXT = "dctypes:Text"
    TYPE_CHOICES = ((OCR, "ocr"), (TEXT, "text"))

    canvas = models.ForeignKey(Canvas, on_delete=models.DO_NOTHING)
    x = models.IntegerField(default=0)
    y = models.IntegerField(default=0)
    w = models.IntegerField(default=0)
    h = models.IntegerField(default=0)
    order = models.IntegerField(default=0)
    content = models.TextField(blank=True, null=True, default=" ")
    resource_type = models.CharField(max_length=50, choices=TYPE_CHOICES, default=TEXT)

    def set_span_element(self):
        return True
