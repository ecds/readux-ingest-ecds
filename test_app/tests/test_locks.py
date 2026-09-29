"""Tests for readux_ingest_ecds.locks -- the distributed lock guarding
against two overlapping runs of the same ingest pipeline (e.g. an admin
resave firing a retry while the original run is still mid-flight)."""

from django.core.cache import cache
from django.test import TestCase

from readux_ingest_ecds.locks import release_ingest_lock, try_acquire_ingest_lock


class IngestLockTest(TestCase):
    def tearDown(self):
        cache.clear()
        super().tearDown()

    def test_first_acquire_succeeds(self):
        assert try_acquire_ingest_lock("local", "ingest-1") is True

    def test_second_acquire_fails_while_held(self):
        assert try_acquire_ingest_lock("local", "ingest-1") is True
        assert try_acquire_ingest_lock("local", "ingest-1") is False

    def test_acquire_succeeds_again_after_release(self):
        try_acquire_ingest_lock("local", "ingest-1")
        release_ingest_lock("local", "ingest-1")
        assert try_acquire_ingest_lock("local", "ingest-1") is True

    def test_different_ingest_ids_are_independent(self):
        assert try_acquire_ingest_lock("local", "ingest-1") is True
        assert try_acquire_ingest_lock("local", "ingest-2") is True

    def test_different_kinds_are_independent(self):
        assert try_acquire_ingest_lock("local", "ingest-1") is True
        assert try_acquire_ingest_lock("remote", "ingest-1") is True

    def test_release_is_safe_when_nothing_is_held(self):
        release_ingest_lock("local", "never-acquired")  # must not raise
