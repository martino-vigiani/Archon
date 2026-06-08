"""
Archon Dashboard - Real-time monitoring web interface.

Run with: python -m orchestrator.dashboard
Or: uvicorn orchestrator.dashboard:app --reload

Multi-session aware: every read endpoint and every ``POST /api/control/*`` accepts
an optional ``?session=<id>`` query parameter that selects the per-session
``.orchestra/runs/<id>/`` tree via :func:`resolve_config`. With no parameter the
legacy single-session ``.orchestra`` config is used, so pre-session behavior is
unchanged.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import secrets
import signal
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import Body, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import file_tracker, metrics, sessions
from .config import Config
from .control import ControlChannel
from .dynamic_agents import derive_agents

app = FastAPI(title="Archon Dashboard", version="0.5.0")

_CSRF_SAFE_HOSTS = {"127.0.0.1", "localhost", "::1"}

# Optional shared-secret gate for the control plane. When ``ARCHON_DASHBOARD_TOKEN``
# is set, every state-changing request (and the WebSocket) must present it via the
# ``X-Archon-Token`` header (or ``?token=`` for the WS handshake). Unset (the
# default) preserves the loopback-only, no-auth dev behavior — set it to harden a
# dashboard that any local process / a CSRF drive-by could otherwise steer (it
# can inject tasks and spawn/kill processes).
DASHBOARD_TOKEN = os.environ.get("ARCHON_DASHBOARD_TOKEN") or None

# Resource-exhaustion guards for the unauthenticated, process-spawning /api/runs
# endpoint (each run forks an orchestrator that forks N model subprocesses).
_MAX_GOAL_LEN = 20_000
_MAX_INSTRUCTIONS_LEN = 20_000
_MAX_ROSTER_BYTES = 256 * 1024
_MAX_CONCURRENT_RUNS = int(os.environ.get("ARCHON_MAX_CONCURRENT_RUNS", "8") or "8")


def _token_ok(provided: str | None) -> bool:
    """Constant-time check of a presented control-plane token.

    Always True when no token is configured (opt-in hardening).
    """
    if not DASHBOARD_TOKEN:
        return True
    return bool(provided) and secrets.compare_digest(provided, DASHBOARD_TOKEN)


@app.middleware("http")
async def _csrf_origin_guard(request, call_next):
    """Block cross-origin state-changing requests + enforce the optional token.

    The dashboard binds loopback, but a victim's browser visiting a malicious page
    can still POST to ``http://localhost:8420`` — and our mutating endpoints spawn
    and kill processes. Browsers send an ``Origin`` header on cross-origin (and
    same-origin) POSTs; we reject any whose host isn't loopback. Requests with no
    ``Origin`` (curl, server-to-server, the test client) are allowed through the
    origin check — but when ``ARCHON_DASHBOARD_TOKEN`` is configured they must
    still present a valid ``X-Archon-Token`` header.
    """
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        origin = request.headers.get("origin")
        if origin:
            host = urlparse(origin).hostname
            if host not in _CSRF_SAFE_HOSTS:
                return JSONResponse(
                    {"detail": "cross-origin request blocked"}, status_code=403
                )
        if not _token_ok(request.headers.get("x-archon-token")):
            return JSONResponse({"detail": "invalid or missing token"}, status_code=401)
    return await call_next(request)

# Legacy single-session config + control channel. These remain the default target
# when a request omits ``?session=`` so every pre-session endpoint and its tests
# behave exactly as before.
config = Config()
control = ControlChannel(config.orchestra_dir)

# Bind host for the dashboard server. Per the build contract (testing-phase
# security) the dashboard binds loopback only — `/api/runs` spawns processes and
# `/api/dirs` exposes the filesystem, so it must not be reachable off-host.
DASHBOARD_HOST = "127.0.0.1"
DASHBOARD_PORT = 8420


# ---------------------------------------------------------------------------
# Session resolution
# ---------------------------------------------------------------------------
# A "session" is one orchestrator process owning a namespaced
# `<base>/.orchestra/runs/<session_id>/` dir. The dashboard is a SEPARATE process
# that reads those files (and writes the per-session control bus). We resolve a
# session id to a `Config` (and a `ControlChannel`) once and cache it per id, so
# repeated requests for the same session share file-path computation.

_config_cache: dict[str, Config] = {}
_control_cache: dict[str, ControlChannel] = {}

# Statuses considered "live" when auto-selecting the default session.
_RUNNING_STATUSES = ("running", "starting", "paused")


def _base_dir() -> Path:
    """Return the repository base dir used to locate the session registry.

    Returns:
        The legacy config's ``base_dir`` — the root that owns ``.orchestra``.
    """
    return config.base_dir


def resolve_config(session: str | None) -> Config:
    """Resolve a session id (or ``None``) to the ``Config`` that owns its paths.

    Resolution order:
        * An explicit, well-formed ``session`` id maps to
          :meth:`Config.for_session` (cached per id).
        * ``None`` defaults to the most-recent *running* session in the registry
          (``sessions.list_sessions``) when one exists.
        * Otherwise the legacy single-session global :data:`config` is returned,
          so endpoints called with no session behave exactly as before.

    Args:
        session: A session id, or ``None`` for the default/legacy target.

    Returns:
        The ``Config`` whose ``orchestra_dir`` points at the resolved tree.
    """
    if session:
        sid = session.strip()
        if sid and _safe_session_id(sid):
            cached = _config_cache.get(sid)
            if cached is None:
                cached = Config.for_session(sid, base_dir=_base_dir())
                _config_cache[sid] = cached
            return cached
        # Malformed id → fall back rather than build a bogus path.
        return config

    # No explicit session: prefer the newest live session, else legacy.
    try:
        for entry in sessions.list_sessions(_base_dir()):
            if entry.get("status") in _RUNNING_STATUSES:
                sid = entry.get("session_id")
                if isinstance(sid, str) and _safe_session_id(sid):
                    return resolve_config(sid)
    except Exception:
        pass
    return config


def resolve_control(session: str | None) -> ControlChannel:
    """Resolve a session id (or ``None``) to its per-session ``ControlChannel``.

    The control bus is per-session: each session's commands live under its own
    ``control/commands.jsonl``. ``None`` returns the legacy global channel.

    Args:
        session: A session id, or ``None`` for the legacy channel.

    Returns:
        The ``ControlChannel`` writing into the resolved session's tree.
    """
    cfg = resolve_config(session)
    key = cfg.session_id or "__legacy__"
    cached = _control_cache.get(key)
    if cached is None:
        cached = ControlChannel(cfg.orchestra_dir)
        _control_cache[key] = cached
    return cached


def _safe_session_id(session_id: str) -> bool:
    """Validate a session id so it can never escape the runs directory.

    Session ids are minted as ``YYYYMMDD-HHMMSS-<slug>`` where the slug is
    lowercase ascii/digits/hyphens. We accept that conservative shape and reject
    anything containing path separators or ``..``.

    Args:
        session_id: Candidate id.

    Returns:
        ``True`` if the id is a safe single path component.
    """
    if not session_id or "/" in session_id or "\\" in session_id or ".." in session_id:
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9._-]+", session_id))


def _known_terminal_ids(cfg: Config | None = None) -> list[str]:
    """Terminal ids present in the live status (dynamic-aware), falling back to the
    legacy roster."""
    cfg = cfg or config
    status = read_json_file(cfg.status_file) or {}
    ids = list((status.get("terminals") or {}).keys())
    return ids or ["t1", "t2", "t3", "t4", "t5"]


_LEGACY_IDS = ("t1", "t2", "t3", "t4", "t5")


def _valid_terminal_id(terminal_id: str, cfg: Config | None = None) -> bool:
    """A terminal id is valid if it is the legacy roster (always) OR a dynamic w-id
    currently present in the live status. Used by read endpoints. Independent of which
    roster the current run happens to use, so it never rejects a legitimate id."""
    if not terminal_id:
        return False
    return terminal_id in _LEGACY_IDS or terminal_id in _known_terminal_ids(cfg)


def _well_formed_worker_id(terminal_id: str) -> bool:
    """Format check for control targets (e.g. t1, w3). Membership is NOT required here:
    the dynamic roster may not be in the status file yet, and the orchestrator only
    applies a control command to a worker that actually exists at apply time."""
    return bool(re.fullmatch(r"[a-z]+\d+", terminal_id or ""))


# Serve static files
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    js_dir = static_dir / "js"
    if js_dir.exists():
        app.mount("/js", StaticFiles(directory=str(js_dir)), name="js")


# ---------------------------------------------------------------------------
# CONTRACT 1 (dapi → windowmgr/design): runtime labels on each terminal entry.
#
# The live status file (`.orchestra/status.json`) carries the *raw* runtime per
# terminal — `provider`, `model`, `reasoning_profile`, `mode` — but no
# human-readable names, so the UI cannot show what a worker actually runs.
# The helpers below derive `model_label` and `effort_label` from that raw data
# WITHOUT renaming or dropping any existing field. They are pure and never raise:
# unknown/empty inputs fall back to a sane non-empty label.
# ---------------------------------------------------------------------------

# Pretty short names for known model ids/tiers. Keys are matched case-insensitively
# as substrings of the raw model value, so `claude-opus-4-8`, `opus`, and `Opus`
# all resolve to "Opus".
_MODEL_PRETTY: tuple[tuple[str, str], ...] = (
    ("opus", "Opus"),
    ("sonnet", "Sonnet"),
    ("haiku", "Haiku"),
)

# Raw effort token (from `mode`, else `reasoning_profile`) → human effort label.
_EFFORT_LABELS: dict[str, str] = {
    "xhigh": "max",
    "max": "max",
    "high": "high",
    "medium": "medium",
    "standard": "medium",
    "low": "low",
    "minimal": "low",
    "auto": "auto",
    "default": "auto",
    "inherit": "inherit",
}


def model_label_for(provider: str, model: str, codex_model: str = "") -> str:
    """Return a human-readable model name for a terminal's raw runtime fields.

    Implements the `model_label` half of CONTRACT 1. Never returns an empty
    string.

    Args:
        provider: Raw provider, e.g. ``"claude"`` or ``"codex"``.
        model: Raw model id from status, e.g. ``"default"`` or ``"claude-opus-4-8"``.
        codex_model: Optional codex model fallback when ``model`` is empty/default.

    Returns:
        A short pretty name such as ``"Opus"``, ``"Sonnet"``, ``"Haiku"``,
        ``"Opus (plan default)"`` (claude + ``default``), or, for codex, the
        configured model id.
    """
    raw = (model or "").strip()
    prov = (provider or "").strip().lower()

    if prov == "codex":
        # Codex carries its concrete model id (or a configured default) — surface it.
        return raw if raw and raw.lower() != "default" else (codex_model or "Codex")

    # Claude (or any non-codex provider): an unset/"default" model means the
    # subprocess inherits the plan's default model (currently Opus).
    if not raw or raw.lower() == "default":
        return "Opus (plan default)"

    lowered = raw.lower()
    for needle, pretty in _MODEL_PRETTY:
        if needle in lowered:
            return pretty
    return raw  # Unknown but real id — show it verbatim rather than nothing.


def effort_label_for(mode: str, reasoning_profile: str) -> str:
    """Return a human-readable reasoning-effort label for a terminal.

    Implements the `effort_label` half of CONTRACT 1. Prefers the per-task
    ``mode`` (the live effort the worker is running) and falls back to the
    terminal's standing ``reasoning_profile``. Never returns an empty string.

    Args:
        mode: Raw per-task mode, e.g. ``"high"``, ``"low"``, ``"auto"``, ``"default"``.
        reasoning_profile: Raw standing profile, e.g. ``"high"``, ``"xhigh"``.

    Returns:
        One of ``"max" | "high" | "medium" | "low" | "auto" | "inherit"`` when
        recognized, otherwise the raw source token verbatim, or ``"inherit"``
        when both inputs are empty.
    """
    source = (mode or "").strip() or (reasoning_profile or "").strip()
    if not source:
        return "inherit"
    return _EFFORT_LABELS.get(source.lower(), source)


def _annotate_terminal_runtime(status: dict) -> dict:
    """Add `model_label` + `effort_label` to every `status.terminals[id]` entry.

    Pure-ish in spirit: mutates the passed status dict in place (the caller owns
    a fresh dict read from disk) and returns it for convenience. Only ADDS the two
    new keys per CONTRACT 1 — existing fields, including `provider`, are untouched.
    Tolerant of malformed entries: a non-dict terminal value is skipped.
    """
    terminals = status.get("terminals")
    if not isinstance(terminals, dict):
        return status
    for entry in terminals.values():
        if not isinstance(entry, dict):
            continue
        entry["model_label"] = model_label_for(
            entry.get("provider", ""),
            entry.get("model", ""),
            entry.get("codex_model", ""),
        )
        entry["effort_label"] = effort_label_for(
            entry.get("mode", ""),
            entry.get("reasoning_profile", ""),
        )
    return status


def read_json_file(path: Path) -> Any:
    """Safely read a JSON file."""
    try:
        if path.exists():
            return json.loads(path.read_text())
    except (json.JSONDecodeError, FileNotFoundError, PermissionError) as e:
        print(f"[Dashboard] Error reading {path}: {e}")
    return None


def _tail_text(path: Path, max_lines: int) -> str:
    """Return the last ``max_lines`` lines of ``path`` reading only its tail.

    Seeks from EOF in blocks instead of loading the whole file, so tailing a
    multi-hundred-MB firehose/log costs a bounded amount of RAM. Output matches
    the previous ``content.strip().split("\\n")[-max_lines:]`` behavior.
    """
    block = 65536
    data = b""
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        pos = f.tell()
        # Read backwards until we have more than max_lines newlines (so the first
        # — possibly partial — line is the one we slice off) or reach the start.
        while pos > 0 and data.count(b"\n") <= max_lines:
            read = min(block, pos)
            pos -= read
            f.seek(pos)
            data = f.read(read) + data
    text = data.decode("utf-8", errors="replace").strip()
    if not text:
        return ""
    return "\n".join(text.split("\n")[-max_lines:])


def read_text_file(path: Path, max_lines: int | None = None) -> str:
    """Safely read a text file, optionally limiting to last N lines.

    When ``max_lines`` is set, only the tail of the file is read (bounded RAM)
    rather than the whole file.
    """
    try:
        if path.exists():
            if max_lines:
                return _tail_text(path, max_lines)
            # errors="replace": a log file rotated on a byte boundary can begin with a
            # partial UTF-8 sequence; never let that crash the dashboard read.
            return path.read_text(errors="replace")
    except (FileNotFoundError, PermissionError, ValueError, OSError) as e:
        print(f"[Dashboard] Error reading {path}: {e}")
    return ""


def _tail_jsonl(path: Path, since: int = 0, limit: int | None = None) -> tuple[list[dict], int]:
    """Read JSON-object lines from an append-only ``.jsonl`` file.

    Args:
        path: The ``.jsonl`` file to read.
        since: Number of leading lines to skip (a simple line offset cursor).
        limit: Optional cap on how many lines to return (most recent within the
            window beyond ``since``).

    Returns:
        ``(records, next_offset)`` where ``records`` is the parsed list of dicts
        and ``next_offset`` is the total line count (usable as the next
        ``since``). Robust to a missing file (returns ``([], since)``).
    """
    try:
        if not path.exists():
            return [], max(0, since)
        lines = path.read_text(errors="replace").splitlines()
    except (OSError, ValueError):
        return [], max(0, since)

    total = len(lines)
    start = max(0, since)
    window = lines[start:]
    records: list[dict] = []
    for raw in window:
        raw = raw.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            records.append(obj)
    if limit is not None and limit >= 0:
        records = records[-limit:] if limit else []
    return records, total


def ensure_terminal_output_dir(cfg: Config | None = None) -> Path:
    """Ensure terminal_output directory exists and return its path."""
    cfg = cfg or config
    terminal_output_dir = cfg.orchestra_dir / "terminal_output"
    terminal_output_dir.mkdir(parents=True, exist_ok=True)
    return terminal_output_dir


def save_terminal_output(terminal_id: str, output: str, cfg: Config | None = None) -> None:
    """Save terminal output to a dedicated file."""
    cfg = cfg or config
    terminal_output_dir = ensure_terminal_output_dir(cfg)
    output_file = terminal_output_dir / f"{terminal_id}.txt"

    # Append output with timestamp
    timestamp = datetime.now().isoformat()
    entry = f"\n--- [{timestamp}] ---\n{output}\n"

    with open(output_file, "a") as f:
        f.write(entry)


def get_terminal_output(terminal_id: str, max_lines: int = 100, cfg: Config | None = None) -> str:
    """Get the last N lines of terminal output."""
    cfg = cfg or config
    terminal_output_dir = cfg.orchestra_dir / "terminal_output"
    output_file = terminal_output_dir / f"{terminal_id}.txt"
    return read_text_file(output_file, max_lines)


def get_subagents_invoked(cfg: Config | None = None) -> list[dict]:
    """Get list of subagents invoked from events.json."""
    cfg = cfg or config
    events_file = cfg.orchestra_dir / "events.json"
    events = read_json_file(events_file) or []

    subagent_events = [event for event in events if event.get("type") == "subagent_invoked"]

    # Return newest first
    return subagent_events[::-1]


def parse_orchestrator_log_entry(line: str) -> dict:
    """Parse a single orchestrator log line into structured data."""
    entry = {"timestamp": None, "type": "state", "message": line, "raw": line}

    # Try to extract timestamp and categorize
    # Common log formats:
    # [2024-01-15 10:30:45] INFO: message
    # [10:30:45] message
    # Phase 1 starting...
    # Routing task to T1...

    line_lower = line.lower()

    # Detect type based on keywords
    if any(kw in line_lower for kw in ["error", "failed", "exception", "crash"]):
        entry["type"] = "error"
    elif any(kw in line_lower for kw in ["routing", "assign", "dispatch", "-> t"]):
        entry["type"] = "routing"
    elif any(kw in line_lower for kw in ["decision", "chose", "selected", "strategy"]):
        entry["type"] = "decision"
    elif any(kw in line_lower for kw in ["phase", "state", "status", "complete", "start"]):
        entry["type"] = "state"

    # Try to extract timestamp
    # Match [HH:MM:SS] or [YYYY-MM-DD HH:MM:SS]
    time_match = re.search(r"\[(\d{2}:\d{2}(?::\d{2})?)\]", line)
    if time_match:
        entry["timestamp"] = time_match.group(1)
        # Remove timestamp from message
        entry["message"] = line[time_match.end() :].strip()
        if entry["message"].startswith(":"):
            entry["message"] = entry["message"][1:].strip()

    return entry


def get_orchestrator_thoughts(max_entries: int = 50, cfg: Config | None = None) -> list[dict]:
    """Get orchestrator decision log entries as structured data."""
    cfg = cfg or config
    log_file = cfg.orchestra_dir / "orchestrator.log"
    content = read_text_file(log_file)
    if not content:
        return []

    lines = content.strip().split("\n")
    entries = []

    for line in lines[-max_entries:]:
        if line.strip():
            entry = parse_orchestrator_log_entry(line.strip())
            entries.append(entry)

    return entries[::-1]  # Newest first


def get_project_info(cfg: Config | None = None) -> dict:
    """Get current project information."""
    cfg = cfg or config
    project_file = cfg.orchestra_dir / "last_project.json"
    project_data = read_json_file(project_file)

    if project_data:
        return {
            "name": project_data.get("name", "Unknown"),
            "path": project_data.get("path", str(cfg.base_dir)),
            "type": project_data.get("type", "other"),
            "status": project_data.get("status", "active"),
        }

    return {
        "name": "Archon",
        "path": str(cfg.base_dir),
        "type": "orchestrator",
        "status": "active",
    }


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Serve the dashboard HTML."""
    html_path = static_dir / "index.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text())
    return HTMLResponse(content="<h1>Dashboard not found</h1>")


@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard():
    """Serve the API admin dashboard."""
    html_path = static_dir / "admin.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text())
    return HTMLResponse(content="<h1>Admin dashboard not found</h1>")


def _status_payload(cfg: Config) -> dict:
    """Build the annotated status payload for a session config.

    Mirrors the ``/api/status`` response: reads ``status.json`` (or a sane idle
    default), stamps a timestamp + project info, and annotates each terminal with
    CONTRACT 1 labels. Never raises.
    """
    try:
        status = read_json_file(cfg.status_file) or {
            "state": "idle",
            "terminals": {},
            "tasks": {
                "pending_count": 0,
                "in_progress_count": 0,
                "completed_count": 0,
                "failed_count": 0,
                "total_count": 0,
            },
        }
        status["timestamp"] = datetime.now().isoformat()
        status["project"] = get_project_info(cfg)
        _annotate_terminal_runtime(status)
        return status
    except Exception as e:
        return {
            "state": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }


@app.get("/api/status")
async def get_status(session: str | None = None):
    """Get current orchestrator status (optionally scoped to ``?session=``)."""
    return _status_payload(resolve_config(session))


@app.get("/api/tasks")
async def get_tasks(session: str | None = None):
    """Get all tasks from all queues (optionally scoped to ``?session=``)."""
    cfg = resolve_config(session)
    try:
        pending = read_json_file(cfg.tasks_dir / "pending.json") or []
        in_progress = read_json_file(cfg.tasks_dir / "in_progress.json") or []
        completed = read_json_file(cfg.tasks_dir / "completed.json") or []
        failed = []  # TaskQueue doesn't maintain a separate failed queue

        return {
            "pending": pending,
            "in_progress": in_progress,
            "completed": completed,
            "failed": failed,
        }
    except Exception as e:
        return {
            "pending": [],
            "in_progress": [],
            "completed": [],
            "failed": [],
            "error": str(e),
        }


@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str, session: str | None = None):
    """Get a specific task by ID."""
    cfg = resolve_config(session)
    try:
        for queue in ["pending", "in_progress", "completed", "failed"]:
            tasks = read_json_file(cfg.tasks_dir / f"{queue}.json") or []
            for task in tasks:
                if task.get("id") == task_id:
                    return task
        raise HTTPException(status_code=404, detail="Task not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/messages")
async def get_messages(session: str | None = None):
    """Get messages from all inboxes."""
    cfg = resolve_config(session)
    try:
        messages = {}
        for tid in _known_terminal_ids(cfg):
            inbox_path = cfg.messages_dir / f"{tid}_inbox.md"
            if inbox_path.exists():
                messages[tid] = inbox_path.read_text()

        broadcast_path = cfg.get_broadcast_file()
        if broadcast_path.exists():
            messages["broadcast"] = broadcast_path.read_text()

        return messages
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/terminals")
async def get_terminals(session: str | None = None):
    """Get terminal configurations."""
    cfg = resolve_config(session)
    try:
        return {
            tid: {
                "id": tid,
                "role": tcfg.role,
                "description": tcfg.description,
                "subagents": tcfg.subagents,
                "specialization": tcfg.specialization,
                "provider": cfg.llm_provider,
                "model": (
                    (cfg.llm_model or tcfg.codex_model)
                    if cfg.llm_provider == "codex"
                    else (cfg.llm_model or "default")
                ),
                "reasoning_profile": tcfg.codex_reasoning,
            }
            for tid, tcfg in cfg.terminals.items()
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/terminal-output/{terminal_id}")
async def get_terminal_output_endpoint(
    terminal_id: str, max_lines: int = 100, session: str | None = None
):
    """Get the last output from a specific terminal."""
    cfg = resolve_config(session)
    if not _valid_terminal_id(terminal_id, cfg):
        raise HTTPException(status_code=400, detail="Invalid terminal_id.")

    try:
        output = get_terminal_output(terminal_id, max_lines, cfg)
        terminal_config = cfg.terminals.get(terminal_id)

        return {
            "terminal_id": terminal_id,
            "role": terminal_config.role if terminal_config else "Unknown",
            "output": output,
            "timestamp": datetime.now().isoformat(),
            "has_output": bool(output.strip()),
        }
    except Exception as e:
        return {
            "terminal_id": terminal_id,
            "role": "Unknown",
            "output": "",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
            "has_output": False,
        }


@app.get("/api/subagents")
async def get_subagents(session: str | None = None):
    """Get list of subagents that have been invoked.

    Returns a consistent data structure with:
    - invoked: list of subagent invocation events
    - available: list of all available subagent names
    - total_invocations: total count
    """
    cfg = resolve_config(session)
    try:
        subagents = get_subagents_invoked(cfg)

        # Get available subagents from terminal configs
        available_subagents = set()
        for terminal_config in cfg.terminals.values():
            available_subagents.update(terminal_config.subagents)

        # Transform subagent events to a consistent format
        formatted_subagents = []
        for event in subagents[:20]:  # Last 20
            formatted_subagents.append(
                {
                    "name": event.get("subagent", event.get("name", "unknown")),
                    "terminal": event.get("terminal_id", event.get("terminal", "unknown")),
                    "task": event.get("task", event.get("description", "No task info")),
                    "timestamp": event.get("timestamp", datetime.now().isoformat()),
                    "active": event.get("active", True),
                    "id": event.get("id", f"sa-{len(formatted_subagents)}"),
                }
            )

        return {
            "invoked": formatted_subagents,
            "available": sorted(available_subagents),
            "total_invocations": len(subagents),
        }
    except Exception as e:
        return {
            "invoked": [],
            "available": [],
            "total_invocations": 0,
            "error": str(e),
        }


@app.get("/api/orchestrator-log")
async def get_orchestrator_log(max_entries: int = 50, session: str | None = None):
    """Get orchestrator decision log as structured entries."""
    cfg = resolve_config(session)
    try:
        entries = get_orchestrator_thoughts(max_entries, cfg)
        log_file = cfg.orchestra_dir / "orchestrator.log"

        return {
            "entries": entries,
            "count": len(entries),
            "log_file": str(log_file),
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        return {
            "entries": [],
            "count": 0,
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }


@app.get("/api/project")
async def get_project(session: str | None = None):
    """Get current project information."""
    cfg = resolve_config(session)
    try:
        project_data = get_project_info(cfg)
        project_data["loaded_at"] = datetime.now().isoformat()
        return project_data
    except Exception as e:
        return {
            "name": "Unknown",
            "path": str(cfg.base_dir),
            "error": str(e),
            "loaded_at": datetime.now().isoformat(),
        }


@app.get("/api/artifacts")
async def get_artifacts(session: str | None = None):
    """List artifacts in the artifacts directory."""
    cfg = resolve_config(session)
    try:
        artifacts = []
        if cfg.artifacts_dir.exists():
            for f in cfg.artifacts_dir.iterdir():
                artifacts.append(
                    {
                        "name": f.name,
                        "path": str(f),
                        "size": f.stat().st_size if f.is_file() else 0,
                        "is_dir": f.is_dir(),
                    }
                )
        return artifacts
    except Exception:
        return []


@app.get("/api/events")
async def get_events(session: str | None = None):
    """Get recent events from the event log."""
    cfg = resolve_config(session)
    try:
        events_file = cfg.orchestra_dir / "events.json"
        events = read_json_file(events_file) or []
        return events[-50:][::-1]  # Last 50, newest first
    except Exception:
        return []


@app.post("/api/terminal-output/{terminal_id}")
async def post_terminal_output(terminal_id: str, output: dict, session: str | None = None):
    """Save terminal output."""
    cfg = resolve_config(session)
    if not _valid_terminal_id(terminal_id, cfg):
        raise HTTPException(status_code=400, detail="Invalid terminal_id.")

    try:
        content = output.get("content", "")
        if content:
            save_terminal_output(terminal_id, content, cfg)

        return {
            "status": "saved",
            "terminal_id": terminal_id,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Metrics / files / workspace-graph (F9, F12, F13)
# ---------------------------------------------------------------------------
def _metrics_block(cfg: Config) -> dict:
    """Resolve a session's metrics block.

    Prefers the metrics the orchestrator already wrote into ``status.json``
    (``status["metrics"]``); when absent, recomputes from the loaded status +
    task summary via :func:`metrics.compute_metrics`. Never raises.
    """
    status = read_json_file(cfg.status_file) or {}
    if isinstance(status, dict):
        existing = status.get("metrics")
        if isinstance(existing, dict) and existing:
            return existing
    try:
        task_summary = status.get("tasks") if isinstance(status, dict) else None
        started_at = status.get("started_at") if isinstance(status, dict) else None
        return metrics.compute_metrics(
            status if isinstance(status, dict) else {},
            task_summary if isinstance(task_summary, dict) else {},
            started_at if isinstance(started_at, str) else None,
            datetime.now().isoformat(),
        )
    except Exception:
        return {
            "completion_pct": 0.0,
            "in_progress": 0,
            "pending": 0,
            "completed": 0,
            "failed": 0,
            "throughput_per_min": 0.0,
            "elapsed_sec": 0,
            "per_worker": {},
        }


@app.get("/api/metrics")
async def get_metrics(session: str | None = None):
    """Return the live metrics block for a session (status.json or recomputed)."""
    return _metrics_block(resolve_config(session))


@app.get("/api/files")
async def get_files(session: str | None = None):
    """Return the deduplicated file-event provenance timeline for a session."""
    cfg = resolve_config(session)
    try:
        return file_tracker.collect_file_events(cfg.orchestra_dir)
    except Exception:
        return []


@app.get("/api/workspace-graph")
async def get_workspace_graph(session: str | None = None):
    """Return the agent/file workspace graph for a session."""
    cfg = resolve_config(session)
    try:
        return file_tracker.build_workspace_graph(cfg.orchestra_dir)
    except Exception:
        return {"nodes": [], "edges": []}


@app.get("/api/terminal-prompt/{worker_id}")
async def get_terminal_prompt(worker_id: str, session: str | None = None, limit: int = 50):
    """Return the captured prompt records for a worker (F8).

    Reads ``terminal_prompts/<worker_id>.jsonl`` from the session tree. Records
    carry the resolved model, effort, permission mode, the system prompt, and the
    task body sent to the worker.
    """
    if not _well_formed_worker_id(worker_id):
        raise HTTPException(status_code=400, detail="valid worker id required")
    cfg = resolve_config(session)
    path = cfg.orchestra_dir / "terminal_prompts" / f"{worker_id}.jsonl"
    records, _ = _tail_jsonl(path, since=0, limit=limit)
    return {"worker_id": worker_id, "prompts": records, "count": len(records)}


# ---------------------------------------------------------------------------
# Roster preview (F3) — pure, pre-run derivation
# ---------------------------------------------------------------------------
def _as_bool(value: str | None, default: bool) -> bool:
    """Parse a query-string boolean (``1/true/yes/on``), falling back to default."""
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


@app.get("/api/preview-roster")
async def preview_roster(
    goal: str = "",
    agent_count: int | None = None,
    dynamic: str | None = None,  # noqa: ARG001 - accepted for API parity (see docstring)
    testing: str | None = None,
):
    """Preview the dynamic worker roster for a goal, before launching (F3).

    Calls :func:`dynamic_agents.derive_agents` with the SAME arguments the
    orchestrator uses at spawn time (``get_all_subagents()``, ``max_terminals``,
    ``not disable_testing``, ``tiering=True``), so the preview matches the run.

    Args:
        goal: The run goal text the roster is derived from.
        agent_count: Optional cap on roster size (maps to ``max_agents``).
        dynamic: Unused for derivation parity (the roster is always task-shaped
            here); accepted so the UI can pass its toggle without error.
        testing: Whether the QA/testing lane is included (default on).

    Returns:
        ``[AgentSpec.to_dict(), ...]`` — empty list on any failure.
    """
    try:
        max_agents = (
            agent_count
            if (isinstance(agent_count, int) and agent_count > 0)
            else config.max_terminals
        )
        include_testing = _as_bool(testing, default=not config.disable_testing)
        roster = derive_agents(
            goal or "",
            available_subagents=config.get_all_subagents(),
            max_agents=max_agents,
            include_testing=include_testing,
            tiering=True,
        )
        return [spec.to_dict() for spec in roster]
    except Exception:
        return []


# WebSocket for real-time updates
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        dead_connections = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                dead_connections.append(connection)
        for conn in dead_connections:
            self.disconnect(conn)


manager = ConnectionManager()


async def gather_full_state(session: str | None = None) -> dict:
    """Gather all dashboard state into a single consolidated update.

    Adds the session-aware blocks (``roster``, ``metrics``, ``files``,
    ``stuck``/``needs_input``) on top of the legacy payload. With no session the
    legacy single-session tree is used, so existing consumers are unaffected.
    """
    cfg = resolve_config(session)

    # `_status_payload` already annotates each terminal with CONTRACT 1's
    # `model_label` + `effort_label`, so the WS payload carries them via
    # payload["status"].
    status = _status_payload(cfg)
    tasks = await get_tasks(session)

    terminal_outputs = {}
    for tid in _known_terminal_ids(cfg):
        terminal_outputs[tid] = get_terminal_output(tid, max_lines=50, cfg=cfg)

    orchestrator_log = get_orchestrator_thoughts(max_entries=20, cfg=cfg)

    # Read events.json once for both subagents and events
    events_file = cfg.orchestra_dir / "events.json"
    all_events = read_json_file(events_file) or []

    subagent_events = [e for e in all_events if e.get("type") == "subagent_invoked"]
    recent_events = all_events[-50:][::-1]

    # Session-aware additions (F9/F12/F15). Each is best-effort and never raises.
    roster = status.get("roster") if isinstance(status, dict) else None
    if not isinstance(roster, list):
        roster = []
    metrics_block = _metrics_block(cfg)
    try:
        files = file_tracker.collect_file_events(cfg.orchestra_dir)
    except Exception:
        files = []
    stuck = bool(status.get("stuck")) if isinstance(status, dict) else False
    needs_input = status.get("needs_input") if isinstance(status, dict) else None

    return {
        "type": "update",
        "timestamp": datetime.now().isoformat(),
        "status": status,
        "tasks": tasks,
        "terminal_outputs": terminal_outputs,
        "subagents": subagent_events[::-1][:20],
        "orchestrator_log": orchestrator_log,
        "events": recent_events[:20],
        "roster": roster,
        "metrics": metrics_block,
        "files": files,
        "stuck": stuck,
        "needs_input": needs_input,
    }


# Shared state cache: many WS connections read the SAME state each tick, so gather
# once per interval and share it instead of re-reading every file per connection.
# Keyed by session so distinct sessions do not stomp each other's cache.
_shared_state: dict[str, dict[str, Any]] = {}
_shared_lock = asyncio.Lock()


def _state_hash(payload: dict) -> int:
    """Hash the payload for change detection, EXCLUDING per-tick wall-clocks.

    The top-level ``timestamp`` and ``status.timestamp`` change every tick — if
    they entered the hash the 'send only when state changes' guard would never
    skip. The session-aware additions (``roster``/``metrics``/``files``/``stuck``/
    ``needs_input``) ARE included, except ``metrics.elapsed_sec``, which is a
    wall-clock and would otherwise defeat the guard.
    """
    stable = {k: v for k, v in payload.items() if k != "timestamp"}
    status = stable.get("status")
    if isinstance(status, dict) and "timestamp" in status:
        status = {k: v for k, v in status.items() if k != "timestamp"}
        stable["status"] = status
    # Drop the only wall-clock-derived metric so steady state hashes stable.
    metrics_block = stable.get("metrics")
    if isinstance(metrics_block, dict) and "elapsed_sec" in metrics_block:
        metrics_block = {k: v for k, v in metrics_block.items() if k != "elapsed_sec"}
        stable["metrics"] = metrics_block
    return hash(json.dumps(stable, sort_keys=True, default=str))


async def get_shared_state(
    min_interval: float = 1.5, session: str | None = None
) -> tuple[int, dict]:
    """Return (hash, payload), recomputing at most once per ``min_interval`` seconds.

    State is cached per session id so concurrent watchers of different sessions do
    not invalidate each other's cache.
    """
    import time

    cfg = resolve_config(session)
    key = cfg.session_id or "__legacy__"
    now = time.monotonic()
    async with _shared_lock:
        entry = _shared_state.get(key)
        if entry is None or entry.get("payload") is None or (now - entry["at"]) >= min_interval:
            payload = await gather_full_state(session)
            entry = {"payload": payload, "hash": _state_hash(payload), "at": now}
            _shared_state[key] = entry
        return entry["hash"], entry["payload"]


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates.

    Sends consolidated 'update' messages only when state changes. State is gathered
    once per tick and shared across all connections watching the same session.
    The optional ``?session=<id>`` query param scopes the stream to that session.
    """
    # Reject cross-origin WS handshakes (the HTTP CSRF guard does not cover the
    # WebSocket) and enforce the optional control-plane token. A browser cannot
    # set custom WS headers, so the token is accepted via ``?token=``.
    origin = websocket.headers.get("origin")
    if origin and urlparse(origin).hostname not in _CSRF_SAFE_HOSTS:
        await websocket.close(code=1008)
        return
    if not _token_ok(websocket.query_params.get("token") or websocket.headers.get("x-archon-token")):
        await websocket.close(code=1008)
        return

    session = websocket.query_params.get("session")
    await manager.connect(websocket)
    last_hash = 0
    try:
        while True:
            state_hash, full_state = await get_shared_state(session=session)
            if state_hash != last_hash:
                last_hash = state_hash
                await websocket.send_json(full_state)
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)


# ---------------------------------------------------------------------------
# Control plane — direct steering of a running orchestrator (via ControlChannel).
# ---------------------------------------------------------------------------
def _build_profile_dict(body: dict) -> dict | None:
    """Translate a UI mode body into an ExecutionProfile dict.

    Accepts: model_tier (cheap/standard/deep), effort (low..max),
    plan (bool -> permission_mode), agents (dict), append_system_prompt /
    instructions (the how-to instructions carried into a worker run, F2).
    Returns None if nothing set.
    """
    profile: dict[str, Any] = {}
    if body.get("model_tier"):
        profile["model_tier"] = body["model_tier"]
    if body.get("model_override"):
        profile["model_override"] = body["model_override"]
    if body.get("effort"):
        profile["effort"] = body["effort"]
    if body.get("plan"):
        profile["permission_mode"] = "plan"
    elif body.get("permission_mode"):
        profile["permission_mode"] = body["permission_mode"]
    if body.get("agents"):
        profile["agents"] = body["agents"]
    # F2: how-to instructions become the worker's appended system prompt. Accept
    # either explicit `append_system_prompt` or the friendlier `instructions`.
    append_system_prompt = body.get("append_system_prompt") or body.get("instructions")
    if isinstance(append_system_prompt, str) and append_system_prompt.strip():
        profile["append_system_prompt"] = append_system_prompt
    return profile or None


@app.post("/api/control/pause")
async def control_pause(session: str | None = None):
    resolve_control(session).submit({"type": "pause"})
    return {"ok": True, "action": "pause"}


@app.post("/api/control/resume")
async def control_resume(session: str | None = None):
    resolve_control(session).submit({"type": "resume"})
    return {"ok": True, "action": "resume"}


@app.post("/api/control/inject")
async def control_inject(body: dict = Body(...), session: str | None = None):
    title = (body.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title is required")
    command = {
        "type": "inject",
        "title": title,
        "description": body.get("description", ""),
        "target": body.get("target"),
        "priority": body.get("priority", "high"),
    }
    profile = _build_profile_dict(body)
    if profile:
        command["profile"] = profile
    resolve_control(session).submit(command)
    return {"ok": True, "action": "inject", "target": command["target"]}


@app.post("/api/control/mode")
async def control_mode(body: dict = Body(...), session: str | None = None):
    target = body.get("target")
    if not target or not _well_formed_worker_id(target):
        raise HTTPException(status_code=400, detail="valid target worker id required")
    ctrl = resolve_control(session)
    # clear=true removes any standing per-worker mode override (back to lane/auto).
    if body.get("clear"):
        ctrl.submit({"type": "set_mode", "target": target, "clear": True})
        return {"ok": True, "action": "clear_mode", "target": target}
    profile = _build_profile_dict(body)
    if not profile:
        raise HTTPException(status_code=400, detail="no mode fields provided")
    ctrl.submit({"type": "set_mode", "target": target, "profile": profile})
    return {"ok": True, "action": "set_mode", "target": target, "profile": profile}


@app.post("/api/control/config")
async def control_config(body: dict = Body(...), session: str | None = None):
    command = {"type": "set_config"}
    for key in ("model_tiering", "effort_dial", "dynamic_agents"):
        if key in body:
            command[key] = bool(body[key])
    resolve_control(session).submit(command)
    return {"ok": True, "action": "set_config", "config": command}


@app.post("/api/control/cancel")
async def control_cancel(body: dict = Body(...), session: str | None = None):
    task_id = body.get("task_id")
    if not task_id:
        raise HTTPException(status_code=400, detail="task_id required")
    resolve_control(session).submit({"type": "cancel", "task_id": task_id})
    return {"ok": True, "action": "cancel", "task_id": task_id}


@app.post("/api/control/spawn")
async def control_spawn(body: dict = Body(...), session: str | None = None):
    """Spawn a new dynamic worker mid-run (F10).

    Body: ``{focus | lane, profile?}`` — at least one of ``focus`` / ``lane`` is
    required. The orchestrator mints a fresh non-colliding worker id, builds an
    ``AgentSpec``, gates the profile, and spawns the terminal.
    """
    focus = (body.get("focus") or "").strip() if isinstance(body.get("focus"), str) else ""
    lane = (body.get("lane") or "").strip() if isinstance(body.get("lane"), str) else ""
    if not focus and not lane:
        raise HTTPException(status_code=400, detail="focus or lane is required")
    command: dict[str, Any] = {"type": "spawn_worker"}
    if focus:
        command["focus"] = focus
    if lane:
        command["lane"] = lane
    profile = _build_profile_dict(body)
    if profile:
        command["profile"] = profile
    resolve_control(session).submit(command)
    return {"ok": True, "action": "spawn_worker", "focus": focus, "lane": lane}


@app.post("/api/control/chat")
async def control_chat(body: dict = Body(...), session: str | None = None):
    """Submit a manager-chat query against the live run (F4).

    Body: ``{text, chat_session_id}``. The orchestrator answers against its live
    state and appends the answer to the per-chat reply channel, polled via
    ``GET /api/chat/replies``.
    """
    text = (body.get("text") or "").strip() if isinstance(body.get("text"), str) else ""
    # Sanitize the channel id before it travels the bus → orchestrator file path
    # (the orchestrator sanitizes too, but stop the bad value at the door).
    chat_session_id = re.sub(r"[^A-Za-z0-9._-]", "_", str(body.get("chat_session_id") or "default")) or "default"
    if ".." in chat_session_id:
        chat_session_id = "default"
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    resolve_control(session).submit(
        {"type": "chat", "text": text, "chat_session_id": chat_session_id}
    )
    return {"ok": True, "action": "chat", "chat_session_id": chat_session_id}


@app.get("/api/chat/replies")
async def get_chat_replies(
    chat_session_id: str = "default", since: int = 0, session: str | None = None
):
    """Tail a chat session's reply channel (F4).

    Reads ``chat/<chat_session_id>.replies.jsonl`` from the session tree starting
    at line offset ``since``. Returns the new replies plus the next offset.
    """
    cfg = resolve_config(session)
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", str(chat_session_id)) or "default"
    path = cfg.orchestra_dir / "chat" / f"{safe}.replies.jsonl"
    replies, next_offset = _tail_jsonl(path, since=max(0, since), limit=None)
    return {"chat_session_id": safe, "replies": replies, "next": next_offset}


# ---------------------------------------------------------------------------
# Sessions registry + run launch (F1, F14)
# ---------------------------------------------------------------------------
@app.get("/api/sessions")
async def list_sessions_endpoint():
    """List all known sessions, newest first (F14)."""
    try:
        return sessions.list_sessions(_base_dir())
    except Exception:
        return []


@app.get("/api/sessions/{session_id}")
async def get_session_endpoint(session_id: str):
    """Return a single session's registry entry, or 404."""
    if not _safe_session_id(session_id):
        raise HTTPException(status_code=404, detail="session not found")
    try:
        entry = sessions.read_session(_base_dir(), session_id)
    except Exception:
        entry = None
    if not entry:
        raise HTTPException(status_code=404, detail="session not found")
    return entry


def _pid_looks_like_archon(pid: int) -> bool:
    """Best-effort check that ``pid`` is actually an Archon orchestrator process.

    The session registry (``sessions.json``) is a plain file any local process
    can rewrite, and the dashboard SIGTERMs the stored pid — so a tampered
    registry could turn ``stop`` into "kill an arbitrary pid". Before signalling,
    confirm the process command line looks like our orchestrator. Returns False
    on any uncertainty so we never signal an unverified pid.
    """
    try:
        out = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if out.returncode != 0:
        return False
    cmd = (out.stdout or "").strip()
    return "orchestrator" in cmd


@app.post("/api/sessions/{session_id}/stop")
async def stop_session_endpoint(session_id: str):
    """Stop a running session: SIGTERM its pid and submit a ``stop`` command.

    Both paths are best-effort: a missing pid or already-dead process is not an
    error. The session status is moved to ``stopped`` in the registry.
    """
    if not _safe_session_id(session_id):
        raise HTTPException(status_code=404, detail="session not found")
    base = _base_dir()
    try:
        entry = sessions.read_session(base, session_id)
    except Exception:
        entry = None
    if not entry:
        raise HTTPException(status_code=404, detail="session not found")

    # File-bus stop request so the orchestrator can shut down gracefully.
    with contextlib.suppress(Exception):
        resolve_control(session_id).submit({"type": "stop"})

    # Best-effort SIGTERM of the recorded pid — but only if it really is an
    # orchestrator process (the registry is locally writable, so a forged pid
    # must not let this signal an arbitrary process).
    pid = entry.get("pid")
    signalled = False
    if isinstance(pid, int) and pid > 0 and _pid_looks_like_archon(pid):
        try:
            os.kill(pid, signal.SIGTERM)
            signalled = True
        except (ProcessLookupError, PermissionError, OSError):
            signalled = False

    with contextlib.suppress(Exception):
        sessions.update_session_status(base, session_id, "stopped")

    return {"ok": True, "action": "stop", "session_id": session_id, "signalled": signalled}


@app.get("/api/sessions/{session_id}/log")
async def get_session_log(session_id: str, since: int = 0, limit: int = 200):
    """Tail a session's firehose log ``session.jsonl`` (F16).

    Args:
        session_id: The session whose firehose to read.
        since: Line offset to start from (cursor returned as ``next``).
        limit: Maximum records to return.

    Returns:
        ``{"session_id", "entries", "next"}`` — empty entries when absent.
    """
    if not _safe_session_id(session_id):
        raise HTTPException(status_code=404, detail="session not found")
    cfg = resolve_config(session_id)
    path = cfg.orchestra_dir / "session.jsonl"
    entries, next_offset = _tail_jsonl(path, since=max(0, since), limit=max(0, limit))
    return {"session_id": session_id, "entries": entries, "next": next_offset}


# Allowed root for the directory picker: never list anything above the user home.
def _dirs_allowed_root() -> Path:
    """Return the sandbox root for ``/api/dirs`` (the user's home directory).

    All listed paths must resolve to within this root; anything above it (``/``,
    other users' homes, ``..`` traversal) is rejected.
    """
    try:
        return Path.home().resolve()
    except Exception:
        return Path("/").resolve()


@app.get("/api/dirs")
async def list_dirs(path: str = ""):
    """List immediate subdirectories of ``path`` for the working-dir picker (F1a).

    SANDBOXED: the resolved path must lie within the user's home directory. Any
    traversal that would escape it (``..``, absolute paths outside home, ``/etc``)
    is rejected by clamping back to the home root rather than erroring — the
    picker simply shows home. ``/`` and anything above home are never listed.

    Args:
        path: A candidate directory path. Empty defaults to the home root.

    Returns:
        ``{"path", "parent", "dirs": [{"name", "path"}, ...]}`` where ``parent``
        is ``None`` at the sandbox root. Robust to a missing/denied directory.
    """
    root = _dirs_allowed_root()

    # Resolve the requested path. Empty / relative inputs are anchored to home.
    raw = (path or "").strip()
    try:
        candidate = Path(raw).expanduser() if raw else root
        if not candidate.is_absolute():
            candidate = root / candidate
        resolved = candidate.resolve()
    except (OSError, ValueError, RuntimeError):
        resolved = root

    # Sandbox: clamp anything outside the home root back to the root.
    if resolved != root and root not in resolved.parents:
        resolved = root

    dirs: list[dict[str, str]] = []
    try:
        if resolved.is_dir():
            for child in sorted(resolved.iterdir(), key=lambda p: p.name.lower()):
                # Skip hidden dirs and non-directories; never surface symlinks
                # that point outside the sandbox.
                try:
                    if not child.is_dir() or child.name.startswith("."):
                        continue
                    child_resolved = child.resolve()
                except OSError:
                    continue
                # A symlink may resolve outside the sandbox root — skip those.
                if child_resolved != root and root not in child_resolved.parents:
                    continue
                dirs.append({"name": child.name, "path": str(child_resolved)})
    except (OSError, PermissionError):
        dirs = []

    # Parent is None at the sandbox root; otherwise the (sandboxed) parent dir.
    parent: str | None = None
    if resolved != root:
        candidate_parent = resolved.parent
        if candidate_parent == root or root in candidate_parent.parents:
            parent = str(candidate_parent)
        else:
            parent = str(root)

    return {"path": str(resolved), "parent": parent, "dirs": dirs}


# Body flag → CLI flag mapping for /api/runs. Boolean truthiness gates store_true
# flags; the off-by-default effort dial is special-cased (presence of a CLI flag
# DISABLES it).
def _run_flags(body: dict) -> list[str]:
    """Translate an ``/api/runs`` body into orchestrator CLI flags.

    Args:
        body: The request body.

    Returns:
        The list of CLI flags to append after the goal positional argument.
    """
    flags: list[str] = []
    if body.get("dynamic_agents"):
        flags.append("--dynamic-agents")
    if body.get("model_tiering"):
        flags.append("--model-tiering")
    # effort_dial is ON by default; only emit the disable flag when explicitly off.
    if "effort_dial" in body and not body.get("effort_dial"):
        flags.append("--no-effort-dial")
    if body.get("no_testing"):
        flags.append("--no-testing")
    agent_count = body.get("agent_count")
    if isinstance(agent_count, int) and agent_count > 0:
        flags.extend(["--agent-count", str(agent_count)])
    project_path = body.get("project_path")
    if isinstance(project_path, str) and project_path.strip():
        flags.extend(["--project", project_path.strip()])
    return flags


@app.post("/api/runs")
async def create_run(body: dict = Body(...)):
    """Launch a new orchestrator run as a detached subprocess (F1).

    Validates the goal, mints a session id, pre-creates the session dir, persists
    ``roster_overrides.json`` and an ``instructions.txt`` (when provided), spawns
    ``python -m orchestrator <goal> --session-id <sid> [flags]`` detached with the
    session env wired, registers the session, and returns
    ``{session_id, status: "starting"}``.

    Body keys: ``goal`` (required), ``project_path?``, ``dynamic_agents?``,
    ``agent_count?``, ``model_tiering?``, ``effort_dial?``, ``no_testing?``,
    ``roster_overrides?``, ``instructions?``.
    """
    goal = (body.get("goal") or "").strip() if isinstance(body.get("goal"), str) else ""
    if not goal:
        raise HTTPException(status_code=400, detail="goal is required")
    if len(goal) > _MAX_GOAL_LEN:
        raise HTTPException(status_code=400, detail=f"goal exceeds {_MAX_GOAL_LEN} chars")
    # Defense in depth against argv flag-smuggling: the goal is a positional arg to
    # `python -m orchestrator`. A leading '-' could be parsed as an option. We also
    # pass it after a '--' end-of-options separator below.
    if goal.startswith("-"):
        raise HTTPException(status_code=400, detail="goal must not start with '-'")

    agent_count = body.get("agent_count")
    if agent_count is not None and (not isinstance(agent_count, int) or agent_count <= 0):
        raise HTTPException(status_code=400, detail="agent_count must be a positive integer")

    instructions = body.get("instructions")
    if isinstance(instructions, str) and len(instructions) > _MAX_INSTRUCTIONS_LEN:
        raise HTTPException(
            status_code=400, detail=f"instructions exceed {_MAX_INSTRUCTIONS_LEN} chars"
        )

    project_path = body.get("project_path")
    if project_path is not None and not isinstance(project_path, str):
        raise HTTPException(status_code=400, detail="project_path must be a string")
    # Containment: confine the (unauthenticated) dashboard's working dir to the
    # user's home, mirroring the /api/dirs picker sandbox. Autonomous workers run
    # permission-bypassed, so an out-of-home path could write anywhere. The CLI
    # --project (operator-trusted) is unaffected.
    if isinstance(project_path, str) and project_path.strip():
        try:
            resolved_pp = Path(project_path.strip()).expanduser().resolve()
            home = Path.home().resolve()
        except (OSError, ValueError, RuntimeError):
            raise HTTPException(status_code=400, detail="invalid project_path")
        if resolved_pp != home and home not in resolved_pp.parents:
            raise HTTPException(status_code=400, detail="project_path must be within the home directory")

    base = _base_dir()

    # Cap concurrent live runs so a loop of POST /api/runs cannot fork-bomb the host.
    try:
        active = sum(
            1 for s in sessions.list_sessions(base)
            if s.get("status") in _RUNNING_STATUSES
        )
    except Exception:
        active = 0
    if active >= _MAX_CONCURRENT_RUNS:
        raise HTTPException(
            status_code=429,
            detail=f"too many active runs ({active}); max is {_MAX_CONCURRENT_RUNS}",
        )
    sid = sessions.make_session_id(goal)
    session_path = sessions.session_dir(base, sid)

    # Pre-create the session dir + persist roster overrides / instructions so the
    # orchestrator finds them at spawn (F5/F2).
    try:
        session_path.mkdir(parents=True, exist_ok=True)
        roster_overrides = body.get("roster_overrides")
        if isinstance(roster_overrides, dict) and roster_overrides:
            roster_json = json.dumps(roster_overrides, indent=2, default=str)
            if len(roster_json.encode("utf-8")) > _MAX_ROSTER_BYTES:
                raise HTTPException(
                    status_code=400, detail=f"roster_overrides exceed {_MAX_ROSTER_BYTES} bytes"
                )
            (session_path / "roster_overrides.json").write_text(roster_json, encoding="utf-8")
        if isinstance(instructions, str) and instructions.strip():
            (session_path / "instructions.txt").write_text(instructions, encoding="utf-8")
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"could not prepare session dir: {e}")

    flags = ["--session-id", sid, *_run_flags(body)]
    # '--' terminates option parsing so the goal can never be read as a flag.
    cmd = [sys.executable, "-m", "orchestrator", *flags, "--", goal]
    env = {
        **os.environ,
        "ARCHON_SESSION_ID": sid,
        "ARCHON_ORCHESTRA_DIR": str(session_path),
    }

    try:
        proc = subprocess.Popen(  # noqa: S603 - inputs validated above
            cmd,
            start_new_session=True,
            cwd=str(base),
            env=env,
        )
        pid = proc.pid
    except (OSError, ValueError) as e:
        raise HTTPException(status_code=500, detail=f"failed to launch run: {e}")

    # Registration is best-effort; the orchestrator also registers itself.
    with contextlib.suppress(Exception):
        sessions.register_session(
            base,
            {
                "session_id": sid,
                "goal": goal,
                "project_path": project_path.strip() if isinstance(project_path, str) else None,
                "pid": pid,
                "status": "starting",
                "orchestra_dir": str(session_path),
            },
        )

    return {"session_id": sid, "status": "starting", "pid": pid}


# Utility function to be used by orchestrator
def log_terminal_output(terminal_id: str, output: str) -> None:
    """Utility function for orchestrator to log terminal output."""
    save_terminal_output(terminal_id, output)


if __name__ == "__main__":
    import uvicorn

    # Ensure directories exist
    config.ensure_dirs()
    ensure_terminal_output_dir()

    # Bind loopback only (testing-phase security): /api/runs spawns processes and
    # /api/dirs exposes the filesystem.
    uvicorn.run(app, host=DASHBOARD_HOST, port=DASHBOARD_PORT)
