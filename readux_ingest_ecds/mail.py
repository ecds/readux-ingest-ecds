from traceback import format_tb
from django.urls.base import reverse
from django.template.loader import get_template
from django.conf import settings
from django.core.mail import send_mail

def send_email_on_failure(bundle=None, creator=None, exception=None):
    """Function to send an email on task failure signal from Celery.

    :type task_watcher: app.ingest.models.TaskWatcher
    :param exception: Exception instance raised
    :type exception: Exception
    :param traceback: Stack trace object
    :type traceback: traceback
    """
    context = {}
    if bundle is not None:
        context['filename'] = bundle
    if exception is not None:
        context['exception'] = exception
    html_email = get_template('ingest_ecds_failure_email.html').render(context)
    text_email = get_template('ingest_ecds_failure_email.txt').render(context)
    if creator is not None:
        send_mail(
            '[Readux] Failed: Ingest ' + bundle,
            text_email,
            settings.READUX_EMAIL_SENDER,
            [creator.email],
            fail_silently=False,
            html_message=html_email
        )

def send_email_on_success(creator=None, manifest=None):
    context = {}
    if manifest is not None:
        context['manifest_pid'] = manifest.pid
        context['manifest_url'] = settings.HOSTNAME + reverse(
            'admin:manifests_manifest_change', args=(manifest.pid,)
        )
        context['manifest_pid'] = manifest.pid
        context['volume_url'] = manifest.get_volume_url()
        html_email = get_template('ingest_ecds_success_email.html').render(context)
        text_email = get_template('ingest_ecds_success_email.txt').render(context)
        if creator is not None:
            send_mail(
                '[Readux] Ingest complete: ' + manifest.pid,
                text_email,
                settings.READUX_EMAIL_SENDER,
                [creator.email],
                fail_silently=False,
                html_message=html_email
            )