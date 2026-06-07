"""Top-level session registry for Archon orchestrator runs (F1, F14).

A *session* is one orchestrator process owning a single namespaced directory
``<base>/.orchestra/runs/<session_id>/``. This module maintains a top-level
``<base>/.orchestra/sessions.json`` registry (NOT namespaced) that lists every
session known to the system so the dashboard — a separate OS process — can
discover, select, and steer runs by reading files only.

The registry is a JSON array of entries shaped like::

    {
        "session_id": str,
        "goal": str,
        "project_path": str | None,
        "pid": int | None,
        "status": "starting"|"running"|"paused"|"completed"|"failed"|"stopped",
        "started_at": iso8601,
        "updated_at": iso8601,
        "orchestra_dir": str,
    }

Because N orchestrator processes (plus the dashboard) may write the registry
concurrently, every mutation takes an exclusive ``fcntl`` lock on a sidecar
lock file and persists via atomic write-rename. Every public function is
robust to a missing or corrupt registry file: reads return ``[]`` / ``None``
and writes recreate the file rather than raising to the caller.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import fcntl  # POSIX only; absent on Windows.

    _HAVE_FCNTL = True
except ImportError:  # pragma: no cover - non-POSIX fallback
    fcntl = None  # type: ignore[assignment]
    _HAVE_FCNTL = False


__all__ = [
    "VALID_STATUSES",
    "make_session_id",
    "register_session",
    "update_session_status",
    "list_sessions",
    "read_session",
    "session_dir",
]


#: Allowed values for a session ``status`` field.
VALID_STATUSES: tuple[str, ...] = (
    "starting",
    "running",
    "paused",
    "completed",
    "failed",
    "stopped",
)

#: Maximum number of goal words folded into a session-id slug.
_SLUG_MAX_WORDS = 4
#: Hard cap on slug length to keep ids filesystem-friendly.
_SLUG_MAX_LEN = 40


def _now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string.

    Returns:
        ISO 8601 timestamp (UTC, with offset), e.g. ``2026-06-06T14:30:22+00:00``.
    """
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017


def _slugify(goal: str) -> str:
    """Build a short, kebab-case ASCII slug from the first words of a goal.

    Args:
        goal: Free-form goal text. May be empty or contain unicode.

    Returns:
        A lowercase, ASCII, kebab-case slug of up to ``_SLUG_MAX_WORDS`` words,
        capped at ``_SLUG_MAX_LEN`` characters. Falls back to ``"session"`` when
        no usable characters remain.
    """
    text = (goal or "").strip().lower()
    # Drop anything that is not an ASCII letter, digit, or whitespace.
    text = re.sub(r"[^a-z0-9\s]+", " ", text)
    words = [w for w in text.split() if w]
    slug = "-".join(words[:_SLUG_MAX_WORDS])
    slug = slug[:_SLUG_MAX_LEN].strip("-")
    return slug or "session"


def make_session_id(goal: str) -> str:
    """Mint a session id of the form ``YYYYMMDD-HHMMSS-<slug>``.

    The timestamp is local time (so ids sort chronologically in a human's
    timezone) and the slug is derived from the first few words of ``goal``.

    Args:
        goal: The run's goal text; used to derive the human-readable slug.

    Returns:
        A new session id, e.g. ``20260606-143022-habit-tracker``.
    """
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{_slugify(goal)}"


def _registry_path(base_dir: Path) -> Path:
    """Resolve the registry file path for a base directory.

    Args:
        base_dir: Either a project base dir (the ``.orchestra/sessions.json``
            child is used) or a direct path to a ``sessions.json`` file.

    Returns:
        Absolute path to the ``sessions.json`` registry file.
    """
    base = Path(base_dir)
    if base.suffix == ".json":
        return base
    return base / ".orchestra" / "sessions.json"


def _lock_path(registry: Path) -> Path:
    """Return the sidecar lock-file path for a registry file.

    Args:
        registry: Path to the registry JSON file.

    Returns:
        Path to the ``.lock`` sidecar used for advisory cross-process locking.
    """
    return registry.with_name(registry.name + ".lock")


def session_dir(base_dir: Path, session_id: str) -> Path:
    """Return the per-session directory for a session id.

    Args:
        base_dir: Project base dir, or a path to ``sessions.json`` (its parent
            ``.orchestra`` root is reused).
        session_id: The session id to resolve.

    Returns:
        ``<base>/.orchestra/runs/<session_id>`` as an absolute path.
    """
    registry = _registry_path(base_dir)
    # registry is <orchestra>/sessions.json → runs live next to it.
    orchestra_root = registry.parent
    return orchestra_root / "runs" / session_id


def _read_entries(registry: Path) -> list[dict[str, Any]]:
    """Load registry entries, tolerating a missing or corrupt file.

    Args:
        registry: Path to the registry JSON file.

    Returns:
        The list of entry dicts, or ``[]`` if the file is absent, unreadable,
        or does not contain a JSON array of objects.
    """
    try:
        raw = registry.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return []
    if not raw.strip():
        return []
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [entry for entry in data if isinstance(entry, dict)]


def _atomic_write(registry: Path, entries: list[dict[str, Any]]) -> None:
    """Persist registry entries via atomic write-rename.

    Writes to a temp file in the same directory and ``os.replace``-s it over the
    target so concurrent readers never observe a partial file.

    Args:
        registry: Destination registry path.
        entries: Entries to serialize as a JSON array.

    Raises:
        OSError: Propagated only on a hard filesystem failure; callers wrap
            this so it never reaches the public API surface.
    """
    registry.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(entries, indent=2, default=str)
    fd, tmp_name = tempfile.mkstemp(
        prefix=registry.name + ".",
        suffix=".tmp",
        dir=str(registry.parent),
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, registry)
    except BaseException:
        # Best-effort cleanup of the stray temp file on any failure.
        with contextlib.suppress(OSError):
            tmp_path.unlink()
        raise


def _mutate(registry: Path, mutator) -> None:
    """Run ``mutator`` over the registry entries under an exclusive lock.

    Acquires an advisory ``fcntl`` lock on the sidecar lock file (when
    available), reads the current entries, applies ``mutator`` to obtain the new
    list, and writes it atomically. Never raises to the caller.

    Args:
        registry: Path to the registry JSON file.
        mutator: Callable taking the current entries list and returning the new
            entries list to persist.
    """
    try:
        registry.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return

    lock_path = _lock_path(registry)
    try:
        with contextlib.ExitStack() as stack:
            if _HAVE_FCNTL:
                # Hold an advisory exclusive lock across the read-modify-write.
                # If locking fails we still proceed — the write is atomic.
                with contextlib.suppress(OSError):
                    lock_handle = stack.enter_context(open(lock_path, "w"))
                    fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            entries = _read_entries(registry)
            try:
                new_entries = mutator(entries)
            except Exception:
                return
            if new_entries is None:
                return
            _atomic_write(registry, new_entries)
    except (OSError, ValueError, TypeError):
        # Never propagate I/O or serialization failures to callers.
        return


def _sort_key(entry: dict[str, Any]) -> str:
    """Sort key for newest-first ordering.

    Args:
        entry: A registry entry.

    Returns:
        The most recent of ``updated_at`` / ``started_at`` (empty string when
        neither is present), used as a descending sort key.
    """
    updated = entry.get("updated_at") or ""
    started = entry.get("started_at") or ""
    return updated if updated >= started else started


def register_session(base_dir: Path, entry: dict[str, Any]) -> None:
    """Add or replace a session entry in the registry, keyed by ``session_id``.

    Missing fields are filled with sensible defaults: ``started_at`` and
    ``updated_at`` default to now, ``status`` to ``"starting"``, and
    ``orchestra_dir`` to the canonical per-session directory. An existing entry
    with the same ``session_id`` is replaced (its original ``started_at`` is
    preserved if the new entry omits one). Never raises to the caller.

    Args:
        base_dir: Project base dir, or a path to ``sessions.json``.
        entry: The session entry. Must include a non-empty ``session_id``;
            otherwise the call is a no-op.
    """
    if not isinstance(entry, dict):
        return
    session_id = entry.get("session_id")
    if not session_id or not isinstance(session_id, str):
        return

    registry = _registry_path(base_dir)
    now = _now_iso()
    normalized = dict(entry)
    normalized["session_id"] = session_id
    normalized.setdefault("goal", "")
    normalized.setdefault("project_path", None)
    normalized.setdefault("pid", None)
    normalized.setdefault("status", "starting")
    normalized.setdefault("started_at", now)
    normalized["updated_at"] = now
    normalized.setdefault("orchestra_dir", str(session_dir(base_dir, session_id)))

    def _apply(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        kept: list[dict[str, Any]] = []
        for existing in entries:
            if existing.get("session_id") == session_id:
                # Preserve original start time unless the caller supplied one.
                if "started_at" not in entry and existing.get("started_at"):
                    normalized["started_at"] = existing["started_at"]
                continue
            kept.append(existing)
        kept.append(normalized)
        return kept

    _mutate(registry, _apply)


def update_session_status(
    base_dir: Path,
    session_id: str,
    status: str | None = None,
    **fields: Any,
) -> None:
    """Update an existing session's status and/or arbitrary fields.

    Bumps ``updated_at`` to now. If the session is not yet registered, a new
    entry is created so updates are never lost. ``session_id`` cannot be
    overridden via ``fields``. Never raises to the caller.

    Args:
        base_dir: Project base dir, or a path to ``sessions.json``.
        session_id: The session id to update; a falsy id is a no-op.
        status: New status value. Ignored if ``None``; if provided but not in
            :data:`VALID_STATUSES` it is still stored (the registry does not
            police values beyond best effort).
        **fields: Additional entry fields to set (e.g. ``pid``, ``goal``,
            ``project_path``). ``session_id`` is protected and dropped.
    """
    if not session_id or not isinstance(session_id, str):
        return

    registry = _registry_path(base_dir)
    now = _now_iso()
    updates = {k: v for k, v in fields.items() if k != "session_id"}
    if status is not None:
        updates["status"] = status

    def _apply(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        found = False
        result: list[dict[str, Any]] = []
        for existing in entries:
            if existing.get("session_id") == session_id:
                merged = dict(existing)
                merged.update(updates)
                merged["session_id"] = session_id
                merged["updated_at"] = now
                merged.setdefault("started_at", now)
                merged.setdefault("orchestra_dir", str(session_dir(base_dir, session_id)))
                result.append(merged)
                found = True
            else:
                result.append(existing)
        if not found:
            new_entry: dict[str, Any] = {
                "session_id": session_id,
                "goal": "",
                "project_path": None,
                "pid": None,
                "status": "starting",
                "started_at": now,
                "updated_at": now,
                "orchestra_dir": str(session_dir(base_dir, session_id)),
            }
            new_entry.update(updates)
            new_entry["session_id"] = session_id
            new_entry["updated_at"] = now
            result.append(new_entry)
        return result

    _mutate(registry, _apply)


def list_sessions(base_dir: Path) -> list[dict[str, Any]]:
    """Return all registered sessions, newest first.

    Ordering is descending by the more recent of ``updated_at`` / ``started_at``.
    Never raises: a missing or corrupt registry yields an empty list.

    Args:
        base_dir: Project base dir, or a path to ``sessions.json``.

    Returns:
        A list of session entry dicts, newest first.
    """
    registry = _registry_path(base_dir)
    entries = _read_entries(registry)
    try:
        return sorted(entries, key=_sort_key, reverse=True)
    except (TypeError, ValueError):
        return entries


def read_session(base_dir: Path, session_id: str) -> dict[str, Any] | None:
    """Return a single session entry by id, or ``None`` if not found.

    Never raises: a missing or corrupt registry yields ``None``.

    Args:
        base_dir: Project base dir, or a path to ``sessions.json``.
        session_id: The session id to look up.

    Returns:
        The matching entry dict, or ``None`` when absent.
    """
    if not session_id:
        return None
    registry = _registry_path(base_dir)
    for entry in _read_entries(registry):
        if entry.get("session_id") == session_id:
            return entry
    return None
