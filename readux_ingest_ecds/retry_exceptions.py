"""Shared definition of which exceptions count as transient (worth an
automatic retry) versus permanent (retrying just repeats a guaranteed
failure). Lives in its own module, rather than in tasks.py, so both
tasks.py and services/ocr_services.py can import it without a circular
import (tasks.py already imports from ocr_services.py).
"""

from botocore.exceptions import ConnectionError as BotoConnectionError
from django.db.utils import OperationalError
from requests.exceptions import ConnectionError as RequestsConnectionError, Timeout

# Genuine connectivity/infrastructure blips (network drops, DB connection
# hiccups) that are likely to succeed on a later attempt. Deliberately NOT
# botocore.exceptions.ClientError or BotoCoreError -- ClientError also
# covers things like NoSuchBucket, which mean "this genuinely doesn't
# exist," not "try again later"; retrying those just repeats a guaranteed
# failure (and, for non-idempotent work like bulk_create, can turn a
# permanent failure into duplicated data).
TRANSIENT_EXCEPTIONS = (
    BotoConnectionError,  # covers EndpointConnectionError too (subclass)
    RequestsConnectionError,
    Timeout,
    OperationalError,
)
