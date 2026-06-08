"""Append-only firehose session log for Archon (F16).

Each orchestrator process owns exactly one :class:`SessionLog`, which writes a
total, untruncated record of everything that happens during a run to a single
``session.jsonl`` file inside the per-session ``.orchestra`` directory.

Design contract (see ``.archon-build/CONTRACT.md`` §4):

* The log is **append-only**. It is NEVER truncated and NEVER cleared on init,
  and there is NO maximum-line cap (unlike :class:`logger.EventLogger`, which
  keeps only the last 100 events for the dashboard).
* Every record is one JSON object per line: ``{"ts": iso8601, "kind": kind, ...}``.
* Serialization is tolerant: non-serializable values fall back to ``str`` via
  ``json.dumps(default=str)`` so a single odd value never drops a record.
* Writes use ``O_APPEND`` so each line is a single atomic ``write`` syscall;
  one process owning one log means appends do not interleave.
* The file is created with owner-only permissions (``0o600``): it persists full
  prompts and worker output in cleartext (potentially secrets), so it must not
  be world-readable.
* All I/O is best-effort: a failure to write a line must never crash the caller.

Safety valve: the "never truncate" contract holds for any realistic run, but to
bound pathological growth there is a single high-ceiling rotation. Before each
append, if ``session.jsonl`` exceeds a large hard cap (default 1 GiB, overridable
via the ``ARCHON_SESSION_LOG_MAX_BYTES`` env var), it is rotated once to
``session.jsonl.1`` (overwriting any previous ``.1``) and a fresh ``session.jsonl``
is started. The active file keeps its name so the dashboard tail keeps working.
Rotation is best-effort and never raises.
"""

from __future__ import annotations

import contextlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

__all__ = ["SessionLog"]

# High-ceiling safety valve. The firehose contract is "never truncate", so this
# default (1 GiB) is far above any realistic run; it only guards against
# pathological unbounded growth. Overridable via ``ARCHON_SESSION_LOG_MAX_BYTES``.
_DEFAULT_MAX_BYTES = 1 << 30


def _max_bytes() -> int:
    """Resolve the rotation hard cap in bytes.

    Reads the ``ARCHON_SESSION_LOG_MAX_BYTES`` env var (an int) on each call so
    the cap can be tuned without restarting. Falls back to ``_DEFAULT_MAX_BYTES``
    when the var is unset, empty, or not a valid integer.

    Returns:
        The maximum log size in bytes before a one-shot rotation is triggered.
    """
    raw = os.environ.get("ARCHON_SESSION_LOG_MAX_BYTES")
    if raw is None:
        return _DEFAULT_MAX_BYTES
    try:
        return int(raw)
    except ValueError:
        return _DEFAULT_MAX_BYTES


class SessionLog:
    """Append-only firehose writer for a single orchestrator session.

    One process owns one ``SessionLog`` instance. It appends newline-delimited
    JSON records to ``<session_dir>/session.jsonl``. The file is opened per write
    in ``O_APPEND`` mode so each record is a single atomic write and the log can
    be tailed concurrently by the dashboard.

    Attributes:
        session_dir: The per-session ``.orchestra`` directory that owns the log.
        log_file: Path to the append-only ``session.jsonl`` file.
    """

    def __init__(self, session_dir: Path) -> None:
        """Initialize the firehose for a session directory.

        The target file is ``session_dir/"session.jsonl"``. The directory is
        created if missing, but any existing log content is preserved: the file
        is never truncated or cleared here.

        Args:
            session_dir: The per-session ``.orchestra`` directory. Accepts a
                ``Path`` or any path-like value; it is coerced to ``Path``.
        """
        self.session_dir: Path = Path(session_dir)
        self.log_file: Path = self.session_dir / "session.jsonl"
        # Best-effort: never raise from construction. Subsequent writes will
        # also fail gracefully if the directory truly cannot be created.
        with contextlib.suppress(OSError):
            self.session_dir.mkdir(parents=True, exist_ok=True)

    def log(self, kind: str, **fields: Any) -> None:
        """Append a single firehose record.

        Writes one JSON line of the form ``{"ts": iso8601, "kind": kind, **fields}``
        to the log file. Non-serializable values are coerced via ``default=str``
        so a record is never dropped for containing an exotic object. All errors
        are swallowed: this method must never crash its caller.

        Args:
            kind: The record category (e.g. ``"prompt"``, ``"output"``,
                ``"event"``, ``"control"``, ``"state"``).
            **fields: Arbitrary extra fields merged into the record. Keys
                ``"ts"`` and ``"kind"`` are reserved and will be overwritten.
        """
        record: dict[str, Any] = dict(fields)
        record["ts"] = datetime.now().isoformat()
        record["kind"] = kind
        try:
            line = json.dumps(record, default=str, ensure_ascii=False)
        except (TypeError, ValueError):
            # Last-resort encoding: stringify the whole record so we still emit
            # a line rather than losing the event entirely.
            line = json.dumps(
                {
                    "ts": record["ts"],
                    "kind": kind,
                    "_unserializable": str(fields),
                },
                ensure_ascii=False,
            )
        self._append(line)

    def _append(self, line: str) -> None:
        """Append a single line to the log file using ``O_APPEND``.

        Each call performs one ``os.write`` so the line lands atomically. The
        file is created owner-only (``0o600``) since it persists cleartext
        prompts and output. Any I/O error is swallowed to keep the firehose
        non-fatal for callers.

        Args:
            line: The fully serialized JSON record, without a trailing newline.
        """
        self._maybe_rotate()
        try:
            fd = os.open(
                self.log_file,
                os.O_WRONLY | os.O_CREAT | os.O_APPEND,
                0o600,
            )
        except OSError:
            return
        try:
            os.write(fd, (line + "\n").encode("utf-8"))
        except OSError:
            pass
        finally:
            with contextlib.suppress(OSError):
                os.close(fd)

    def _maybe_rotate(self) -> None:
        """Rotate the log once if it has exceeded the high-ceiling hard cap.

        Honors the append-only "never truncate" contract for any realistic run:
        rotation only fires above a large cap (default 1 GiB, overridable via
        ``ARCHON_SESSION_LOG_MAX_BYTES``). When tripped, the current
        ``session.jsonl`` is moved to ``session.jsonl.1`` (overwriting any
        previous ``.1``) and the next append starts a fresh ``session.jsonl``,
        so the dashboard tail keeps following the active file by name.

        This is entirely best-effort: any error (including a missing file or a
        failed rename) is swallowed so the firehose never crashes its caller.
        """
        try:
            size = self.log_file.stat().st_size
        except OSError:
            return
        if size < _max_bytes():
            return
        rotated = self.log_file.with_name(self.log_file.name + ".1")
        with contextlib.suppress(OSError):
            os.replace(self.log_file, rotated)

    # -- Convenience methods ------------------------------------------------
    # Each is a thin wrapper around ``log`` that pins a record ``kind``.

    def prompt(
        self,
        worker_id: str,
        task_id: str | None,
        model: str | None,
        effort: str | None,
        system: str | None,
        body: str | None,
    ) -> None:
        """Record the prompt sent to a worker's CLI subprocess.

        Args:
            worker_id: The worker/terminal id (e.g. ``"t1"`` or ``"w3"``).
            task_id: The task id the prompt is for, if any.
            model: The resolved model or tier name passed to the CLI.
            effort: The reasoning-effort level passed to the CLI.
            system: The ``--append-system-prompt`` value (persona/system text).
            body: The user prompt body (the ``-p`` text).
        """
        self.log(
            "prompt",
            worker=worker_id,
            task_id=task_id,
            model=model,
            effort=effort,
            system=system,
            body=body,
        )

    def output(
        self,
        worker_id: str,
        task_id: str | None,
        content: str | None,
        profile: Any = None,
        timing: Any = None,
    ) -> None:
        """Record the full, untruncated output produced by a worker.

        Args:
            worker_id: The worker/terminal id that produced the output.
            task_id: The task id the output belongs to, if any.
            content: The complete output text (NOT truncated).
            profile: The execution-profile badge/dict used for the run.
            timing: Timing information for the run (e.g. duration seconds).
        """
        self.log(
            "output",
            worker=worker_id,
            task_id=task_id,
            content=content,
            profile=profile,
            timing=timing,
        )

    def event(self, type: str, payload: Any = None) -> None:
        """Record a generic orchestrator event.

        Args:
            type: The event type (e.g. the original requested ``EventType``
                before any dashboard coercion).
            payload: Arbitrary event payload (dict or value).
        """
        self.log("event", type=type, payload=payload)

    def control(self, command: Any) -> None:
        """Record a control-bus command as it is applied.

        Args:
            command: The control command (dict or value) drained from the bus.
        """
        self.log("control", command=command)

    def state(self, snapshot: Any) -> None:
        """Record a point-in-time status snapshot.

        Args:
            snapshot: The status/state snapshot (dict or value).
        """
        self.log("state", snapshot=snapshot)
