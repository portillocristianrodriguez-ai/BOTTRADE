"""Bound only the passive observation dataset; never touch trading state.

One worker process owns the dataset. The wrapper serializes observation append,
feedback rewrite, and retention. Oversized files keep the latest complete lines.
Recovery needs no second file on the already-full volume: the retained suffix
is disjoint from its destination and stays intact until the copied prefix has
been synced and verified. A failure before truncation can be retried safely.
"""
from __future__ import annotations

import functools
import logging
import os
from pathlib import Path
import stat
import threading

MAX_BYTES = 50 * 1024 * 1024
KEEP_BYTES = 25 * 1024 * 1024
_LOCK = threading.RLock()
log = logging.getLogger(__name__)


def compact(path, max_bytes=MAX_BYTES, keep_bytes=KEEP_BYTES):
    """Retain recent complete JSONL lines using existing allocated file blocks."""
    if not 0 < keep_bytes <= max_bytes // 2:
        raise ValueError('Retention requires 0 < keep_bytes <= max_bytes / 2')
    path = Path(path)
    if path.name != 'pattern_observations.jsonl':
        raise ValueError('Retention is restricted to pattern_observations.jsonl')
    with _LOCK:
        try:
            fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
        except FileNotFoundError:
            return 0
        with os.fdopen(fd, 'r+b', buffering=0) as handle:
            before = os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise ValueError('Dataset must be a regular, unlinked file')
            if before.st_size <= max_bytes:
                return 0
            offset = before.st_size - keep_bytes
            handle.seek(offset - 1)
            previous = handle.read(1)
            tail = handle.read(keep_bytes)
            if previous != b'\n':
                boundary = tail.find(b'\n')
                if boundary < 0:
                    raise ValueError('No complete recent observation; preserving source')
                tail = tail[boundary + 1:]
            # An interrupted append may leave an incomplete final JSON line.
            tail = tail[:tail.rfind(b'\n') + 1]
            if not tail:
                raise ValueError('No complete recent observation; preserving source')
            current = os.fstat(handle.fileno())
            if (current.st_size, current.st_mtime_ns) != (before.st_size, before.st_mtime_ns):
                raise RuntimeError('Dataset changed during retention')
            # With keep <= max/2 the source suffix cannot overlap this prefix.
            handle.seek(0)
            view = memoryview(tail)
            while view:
                written = handle.write(view)
                if not written:
                    raise OSError('Short retention write')
                view = view[written:]
            os.fsync(handle.fileno())
            handle.seek(0)
            if handle.read(len(tail)) != tail:
                raise OSError('Retention verification failed; source suffix preserved')
            handle.truncate(len(tail))
            os.fsync(handle.fileno())
            removed = before.st_size - len(tail)
            log.warning('[storage] Observations compacted: %d -> %d bytes; newest complete lines retained', before.st_size, len(tail))
            return removed


def install(main_module):
    original = main_module.registrar_observacion_pattern
    if getattr(original, '_bounded_pattern_storage', False):
        return

    @functools.wraps(original)
    def bounded(*args, **kwargs):
        with _LOCK:
            path = main_module.config.PATTERN_DATA_FILE
            compact(path)
            try:
                return original(*args, **kwargs)
            finally:
                compact(path)

    bounded._bounded_pattern_storage = True
    main_module.registrar_observacion_pattern = bounded
    log.info('[storage] Observation limit: 50 MiB; retain latest 25 MiB on compaction')
