"""
MD5-based dedup cache: re-uploading the exact same file skips the LLM call
entirely and returns the prior stored result. In-process LRU dict — no
external cache service, no extra free-tier dependency to manage.

This is deliberately process-local (not shared across Render instances/
restarts) — acceptable for a single-instance free-tier deployment, and
documented as such. The DB lookup in routes/analyze.py is the durable
fallback: if process memory was cleared (cold start), the analyses table
is checked by file_hash before falling back to the cache miss path.
"""

from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict

_MAX_ENTRIES = 200
_lock = threading.Lock()
_cache: OrderedDict[str, str] = OrderedDict()  # file_hash -> analysis_id


def hash_bytes(raw: bytes) -> str:
    return hashlib.md5(raw).hexdigest()


def get_cached_analysis_id(file_hash: str) -> str | None:
    with _lock:
        analysis_id = _cache.get(file_hash)
        if analysis_id is not None:
            _cache.move_to_end(file_hash)  # LRU touch
        return analysis_id


def set_cached_analysis_id(file_hash: str, analysis_id: str) -> None:
    with _lock:
        _cache[file_hash] = analysis_id
        _cache.move_to_end(file_hash)
        while len(_cache) > _MAX_ENTRIES:
            _cache.popitem(last=False)


def clear_cache() -> None:
    """Used by tests to reset state between cases."""
    with _lock:
        _cache.clear()
