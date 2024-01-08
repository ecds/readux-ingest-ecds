"""Configuration for :class:`apps.ingest`"""
from django.apps import AppConfig


class ReaduxIngestEcdsConfig(AppConfig):
    """Ingest config"""
    name = 'readux_ingest_ecds'
    verbose_name = 'Readux Ingest ECDS'
    label = 'readux_ingest_ecds'
