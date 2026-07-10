"""Small shared helpers for the V3 backend."""

from __future__ import annotations

from datetime import datetime, timezone


def now_iso() -> str:
    """Return the current time as RFC 3339 UTC with millisecond precision.

    Format: ``2026-07-10T14:03:22.481Z`` (the contract's canonical timestamp).
    """
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


__all__ = ["now_iso"]
