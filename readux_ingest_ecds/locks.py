"""Distributed locking for ingest pipelines.

Prevents two overlapping runs of the same ingest -- e.g. an admin resave
firing a retry while the original pipeline is still mid-flight -- from
racing on shared, non-atomic operations like Canvas creation
(readux_ingest_ecds.models.Local.create_canvases).

Backed by the Django cache, which must be a shared backend (Redis) for
this to work across separate Celery worker processes -- a per-process
cache (e.g. LocMemCache) would make acquire/release invisible between
workers and silently defeat the lock.

The lock spans a whole task *chain* (e.g. add_canvases_task -> add_ocr_task_local),
not a single task, so it's acquired at pipeline start and released from the
chain's final success/failure handler rather than via a context manager.
"""

import logging

from django.core.cache import cache

LOGGER = logging.getLogger(__name__)

# Long enough to cover the slowest realistic ingest pipeline; if a worker
# dies without releasing the lock, this is also the maximum time a stuck
# ingest can block a legitimate retry.
LOCK_TIMEOUT = 60 * 60 * 4


def _lock_key(kind, ingest_id):
    return f"ingest-lock:{kind}:{ingest_id}"


def try_acquire_ingest_lock(kind, ingest_id):
    """Attempt to acquire the lock for this ingest pipeline.

    Returns True if acquired (caller should proceed), False if another run
    already holds it (caller should skip this invocation, not retry it --
    the pipeline that holds the lock is already doing the work).
    """
    acquired = cache.add(_lock_key(kind, ingest_id), "1", timeout=LOCK_TIMEOUT)
    if not acquired:
        LOGGER.warning(
            f"INGEST: {kind} ingest {ingest_id} is already running -- skipping this run."
        )
    return acquired


def release_ingest_lock(kind, ingest_id):
    cache.delete(_lock_key(kind, ingest_id))
