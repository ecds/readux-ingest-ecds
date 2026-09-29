"""Email notifications for Celery ingest task success/failure signals."""

import logging
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import get_template
from django.urls.base import reverse

LOGGER = logging.getLogger(__name__)


def _send(subject, text_email, html_email, creator):
    """Shared send step.

    Logs and skips (rather than crashing) when there's no creator to
    notify -- creator is nullable on every ingest model, so this is a
    real, reachable case, not just defensive padding. Logs (rather than
    propagating) if the actual SMTP send fails, since this runs from
    Celery's on_success/on_failure hooks, which are also responsible for
    releasing the ingest lock and updating/deleting the Local row -- a
    failed notification shouldn't be able to interrupt that.
    """
    if creator is None:
        LOGGER.warning(
            f"INGEST: no creator to notify for '{subject}' -- skipping email"
        )
        return
    try:
        send_mail(
            subject,
            text_email,
            settings.READUX_EMAIL_SENDER,
            [creator.email],
            fail_silently=False,
            html_message=html_email,
        )
    except Exception:  # pylint: disable=broad-except
        LOGGER.exception(f"INGEST: failed to send '{subject}' to {creator.email}")


def send_email_on_failure(bundle=None, creator=None, exception=None, manifest=None):
    """Function to send an email on task failure signal from Celery.

    :param exception: Exception instance raised
    :type exception: Exception
    """
    # Always set these keys, even when the value is None -- the templates
    # chain {{ filename|default:manifest_pid|default:"unknown" }}, and
    # Django's `default` filter only handles a variable being falsy, not
    # being entirely absent from the context (that raises
    # VariableDoesNotExist while resolving the filter argument).
    context = {"filename": bundle, "exception": exception, "manifest_pid": None}
    if manifest is not None:
        context["manifest_pid"] = manifest.pid
        context["total_canvases"] = manifest.canvas_set.count()

    html_email = get_template("ingest_ecds_failure_email.html").render(context)
    text_email = get_template("ingest_ecds_failure_email.txt").render(context)

    # bundle is None for ingest paths that were never file uploads (e.g.
    # Remote) -- fall back to the manifest pid, then a plain label, rather
    # than concatenating None into the subject line.
    label = bundle or (manifest.pid if manifest is not None else "unknown")
    _send(f"[Readux] Failed: Ingest {label}", text_email, html_email, creator)


def send_email_on_success(creator=None, manifest=None, warnings=None, source=None):
    """
    :param source: Short label for which ingest path produced this
        manifest (e.g. "S3", "File Upload", "Remote URL"), if known.
    :type source: str
    """
    if manifest is None:
        LOGGER.warning(
            "INGEST: send_email_on_success called with no manifest -- skipping email"
        )
        return

    ingest_warnings = (
        warnings if warnings is not None and len(warnings) > 10 else None
    )
    warning_list = ingest_warnings.split(" | ") if ingest_warnings is not None else []

    total_canvases = manifest.canvas_set.count()
    canvases_with_warnings = len(warning_list)
    canvases_succeeded = max(total_canvases - canvases_with_warnings, 0)

    context = {"manifest_pid": manifest.pid}
    context["manifest_url"] = settings.HOSTNAME + reverse(
        f"admin:{settings.IIIF_MANIFEST_MODEL.lower().replace('.', '_')}_change",
        args=(manifest.pid,),
    )
    context["volume_url"] = manifest.get_volume_url()
    context["source"] = source
    context["total_canvases"] = total_canvases
    context["canvases_succeeded"] = canvases_succeeded
    context["canvases_with_warnings"] = canvases_with_warnings

    context["warnings"] = ""
    context["html_warnings"] = []
    if warning_list:
        context["warnings"] = [
            f'{w} -- https://iip.readux.io/iiif/3/{w.split(" ")[1]}/full/250,/0/default.jpg'
            for w in warning_list
        ]
        context["html_warnings"] = [
            [
                w,
                f'<img src="https://iip.readux.io/iiif/3/{w.split(" ")[1]}/full/250,/0/default.jpg" />',
            ]
            for w in warning_list
        ]

    html_email = get_template("ingest_ecds_success_email.html").render(context)
    text_email = get_template("ingest_ecds_success_email.txt").render(context)

    _send(f"[Readux] Ingest complete: {manifest.pid}", text_email, html_email, creator)
