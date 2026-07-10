"""Identifier helpers for the V3 backend.

The contract mandates:

* ``session_id``/``card_id``/``plan_id``/``intent_id``/``action_id``/``event_id``
  — **ULID** (26 chars, Crockford base32, lexicographically sortable).
* ``project_id`` — ``sha256_hex(canonical_project_path)`` (lowercase 64-hex).
* ``request_id`` — a client-generated ULID (we also mint them server-side when a
  caller omits one).

The ``ulid`` package is intentionally not a dependency; this module implements a
small, monotonic ULID generator (48-bit ms timestamp + 80-bit randomness) that
never emits a value ≤ a previously emitted one within the same process, so ids
sort in creation order (REQ-BE-010 relies on stable, sortable ids).
"""

from __future__ import annotations

import hashlib
import os
import secrets
import threading
import time
from pathlib import Path

#: Crockford base32 alphabet (excludes I, L, O, U).
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

_lock = threading.Lock()
_last_time_ms = 0
_last_randomness = 0

_TIME_MAX = (1 << 48) - 1
_RAND_MAX = (1 << 80) - 1


def _encode(value: int, length: int) -> str:
    """Encode ``value`` as a fixed-``length`` Crockford base32 string."""
    chars = ["0"] * length
    for i in range(length - 1, -1, -1):
        chars[i] = _CROCKFORD[value & 0x1F]
        value >>= 5
    return "".join(chars)


def new_ulid(now_ms: int | None = None) -> str:
    """Return a fresh, monotonically increasing ULID (26 Crockford chars).

    Monotonicity holds within a single process: two calls in the same
    millisecond increment the random component rather than reusing it, and a
    backwards clock step is clamped to the last emitted timestamp.
    """
    global _last_time_ms, _last_randomness

    t = int(time.time() * 1000) if now_ms is None else int(now_ms)
    with _lock:
        if t <= _last_time_ms:
            # Same (or an earlier, clock-skewed) millisecond → bump randomness so
            # the id strictly increases. On randomness overflow, advance the
            # timestamp by one ms (the classic ULID monotonic overflow rule).
            t = _last_time_ms
            rand = _last_randomness + 1
            if rand > _RAND_MAX:
                t += 1
                rand = secrets.randbits(80)
        else:
            rand = secrets.randbits(80)
        _last_time_ms = t
        _last_randomness = rand

    return _encode(t & _TIME_MAX, 10) + _encode(rand & _RAND_MAX, 16)


def new_request_id() -> str:
    """Mint a server-side ``request_id`` (used when the client omits one)."""
    return new_ulid()


def is_ulid(value: str) -> bool:
    """Return True if ``value`` is a syntactically valid ULID."""
    if not isinstance(value, str) or len(value) != 26:
        return False
    return all(c in _CROCKFORD for c in value.upper())


def canonical_project_path(path: str | Path) -> str:
    """Return the absolute, symlink-resolved canonical path (both sides agree).

    The client and server MUST compute ``project_id`` identically from this.
    """
    return os.path.realpath(os.path.abspath(str(path)))


def project_id_for(path: str | Path) -> str:
    """Compute ``project_id`` = ``sha256_hex(canonical_project_path)``."""
    canonical = canonical_project_path(path)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
