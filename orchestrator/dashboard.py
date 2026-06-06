"""
Archon Dashboard - Real-time monitoring web interface.

Run with: python -m orchestrator.dashboard
Or: uvicorn orchestrator.dashboard:app --reload
"""

import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .config import Config
from .control import ControlChannel

app = FastAPI(title="Archon Dashboard", version="0.4.0")
config = Config()
control = ControlChannel(config.orchestra_dir)


def _known_terminal_ids() -> list[str]:
    """Terminal ids present in the live status (dynamic-aware), falling back to the
    legacy roster."""
    status = read_json_file(config.status_file) or {}
    ids = list((status.get("terminals") or {}).keys())
    return ids or ["t1", "t2", "t3", "t4", "t5"]


_LEGACY_IDS = ("t1", "t2", "t3", "t4", "t5")


def _valid_terminal_id(terminal_id: str) -> bool:
    """A terminal id is valid if it is the legacy roster (always) OR a dynamic w-id
    currently present in the live status. Used by read endpoints. Independent of which
    roster the current run happens to use, so it never rejects a legitimate id."""
    if not terminal_id:
        return False
    return terminal_id in _LEGACY_IDS or terminal_id in _known_terminal_ids()


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


def read_json_file(path: Path) -> Any:
    """Safely read a JSON file."""
    try:
        if path.exists():
            return json.loads(path.read_text())
    except (json.JSONDecodeError, FileNotFoundError, PermissionError) as e:
        print(f"[Dashboard] Error reading {path}: {e}")
    return None


def read_text_file(path: Path, max_lines: int | None = None) -> str:
    """Safely read a text file, optionally limiting to last N lines."""
    try:
        if path.exists():
            # errors="replace": a log file rotated on a byte boundary can begin with a
            # partial UTF-8 sequence; never let that crash the dashboard read.
            content = path.read_text(errors="replace")
            if max_lines:
                lines = content.strip().split("\n")
                return "\n".join(lines[-max_lines:])
            return content
    except (FileNotFoundError, PermissionError, ValueError) as e:
        print(f"[Dashboard] Error reading {path}: {e}")
    return ""


def ensure_terminal_output_dir() -> Path:
    """Ensure terminal_output directory exists and return its path."""
    terminal_output_dir = config.orchestra_dir / "terminal_output"
    terminal_output_dir.mkdir(parents=True, exist_ok=True)
    return terminal_output_dir


def save_terminal_output(terminal_id: str, output: str) -> None:
    """Save terminal output to a dedicated file."""
    terminal_output_dir = ensure_terminal_output_dir()
    output_file = terminal_output_dir / f"{terminal_id}.txt"

    # Append output with timestamp
    timestamp = datetime.now().isoformat()
    entry = f"\n--- [{timestamp}] ---\n{output}\n"

    with open(output_file, "a") as f:
        f.write(entry)


def get_terminal_output(terminal_id: str, max_lines: int = 100) -> str:
    """Get the last N lines of terminal output."""
    terminal_output_dir = config.orchestra_dir / "terminal_output"
    output_file = terminal_output_dir / f"{terminal_id}.txt"
    return read_text_file(output_file, max_lines)


def get_subagents_invoked() -> list[dict]:
    """Get list of subagents invoked from events.json."""
    events_file = config.orchestra_dir / "events.json"
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


def get_orchestrator_thoughts(max_entries: int = 50) -> list[dict]:
    """Get orchestrator decision log entries as structured data."""
    log_file = config.orchestra_dir / "orchestrator.log"
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


def get_project_info() -> dict:
    """Get current project information."""
    project_file = config.orchestra_dir / "last_project.json"
    project_data = read_json_file(project_file)

    if project_data:
        return {
            "name": project_data.get("name", "Unknown"),
            "path": project_data.get("path", str(config.base_dir)),
            "type": project_data.get("type", "other"),
            "status": project_data.get("status", "active"),
        }

    return {
        "name": "Archon",
        "path": str(config.base_dir),
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


@app.get("/api/status")
async def get_status():
    """Get current orchestrator status."""
    try:
        status = read_json_file(config.status_file) or {
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
        status["project"] = get_project_info()
        return status
    except Exception as e:
        return {
            "state": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }


@app.get("/api/tasks")
async def get_tasks():
    """Get all tasks from all queues."""
    try:
        pending = read_json_file(config.tasks_dir / "pending.json") or []
        in_progress = read_json_file(config.tasks_dir / "in_progress.json") or []
        completed = read_json_file(config.tasks_dir / "completed.json") or []
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
async def get_task(task_id: str):
    """Get a specific task by ID."""
    try:
        for queue in ["pending", "in_progress", "completed", "failed"]:
            tasks = read_json_file(config.tasks_dir / f"{queue}.json") or []
            for task in tasks:
                if task.get("id") == task_id:
                    return task
        raise HTTPException(status_code=404, detail="Task not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/messages")
async def get_messages():
    """Get messages from all inboxes."""
    try:
        messages = {}
        for tid in _known_terminal_ids():
            inbox_path = config.messages_dir / f"{tid}_inbox.md"
            if inbox_path.exists():
                messages[tid] = inbox_path.read_text()

        broadcast_path = config.get_broadcast_file()
        if broadcast_path.exists():
            messages["broadcast"] = broadcast_path.read_text()

        return messages
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/terminals")
async def get_terminals():
    """Get terminal configurations."""
    try:
        return {
            tid: {
                "id": tid,
                "role": cfg.role,
                "description": cfg.description,
                "subagents": cfg.subagents,
                "specialization": cfg.specialization,
                "provider": config.llm_provider,
                "model": (
                    (config.llm_model or cfg.codex_model)
                    if config.llm_provider == "codex"
                    else (config.llm_model or "default")
                ),
                "reasoning_profile": cfg.codex_reasoning,
            }
            for tid, cfg in config.terminals.items()
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/terminal-output/{terminal_id}")
async def get_terminal_output_endpoint(terminal_id: str, max_lines: int = 100):
    """Get the last output from a specific terminal."""
    if not _valid_terminal_id(terminal_id):
        raise HTTPException(status_code=400, detail="Invalid terminal_id.")

    try:
        output = get_terminal_output(terminal_id, max_lines)
        terminal_config = config.terminals.get(terminal_id)

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
async def get_subagents():
    """Get list of subagents that have been invoked.

    Returns a consistent data structure with:
    - invoked: list of subagent invocation events
    - available: list of all available subagent names
    - total_invocations: total count
    """
    try:
        subagents = get_subagents_invoked()

        # Get available subagents from terminal configs
        available_subagents = set()
        for terminal_config in config.terminals.values():
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
async def get_orchestrator_log(max_entries: int = 50):
    """Get orchestrator decision log as structured entries."""
    try:
        entries = get_orchestrator_thoughts(max_entries)
        log_file = config.orchestra_dir / "orchestrator.log"

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
async def get_project():
    """Get current project information."""
    try:
        project_data = get_project_info()
        project_data["loaded_at"] = datetime.now().isoformat()
        return project_data
    except Exception as e:
        return {
            "name": "Unknown",
            "path": str(config.base_dir),
            "error": str(e),
            "loaded_at": datetime.now().isoformat(),
        }


@app.get("/api/artifacts")
async def get_artifacts():
    """List artifacts in the artifacts directory."""
    try:
        artifacts = []
        if config.artifacts_dir.exists():
            for f in config.artifacts_dir.iterdir():
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
async def get_events():
    """Get recent events from the event log."""
    try:
        events_file = config.orchestra_dir / "events.json"
        events = read_json_file(events_file) or []
        return events[-50:][::-1]  # Last 50, newest first
    except Exception:
        return []


@app.post("/api/terminal-output/{terminal_id}")
async def post_terminal_output(terminal_id: str, output: dict):
    """Save terminal output."""
    if not _valid_terminal_id(terminal_id):
        raise HTTPException(status_code=400, detail="Invalid terminal_id.")

    try:
        content = output.get("content", "")
        if content:
            save_terminal_output(terminal_id, content)

        return {
            "status": "saved",
            "terminal_id": terminal_id,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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


async def gather_full_state() -> dict:
    """Gather all dashboard state into a single consolidated update."""
    status = await get_status()
    tasks = await get_tasks()

    terminal_outputs = {}
    for tid in _known_terminal_ids():
        terminal_outputs[tid] = get_terminal_output(tid, max_lines=50)

    orchestrator_log = get_orchestrator_thoughts(max_entries=20)

    # Read events.json once for both subagents and events
    events_file = config.orchestra_dir / "events.json"
    all_events = read_json_file(events_file) or []

    subagent_events = [e for e in all_events if e.get("type") == "subagent_invoked"]
    recent_events = all_events[-50:][::-1]

    return {
        "type": "update",
        "timestamp": datetime.now().isoformat(),
        "status": status,
        "tasks": tasks,
        "terminal_outputs": terminal_outputs,
        "subagents": subagent_events[::-1][:20],
        "orchestrator_log": orchestrator_log,
        "events": recent_events[:20],
    }


# Shared state cache: many WS connections read the SAME state each tick, so gather
# once per interval and share it instead of re-reading every file per connection.
_shared_state: dict[str, Any] = {"hash": 0, "payload": None, "at": 0.0}
_shared_lock = asyncio.Lock()


def _state_hash(payload: dict) -> int:
    """Hash the payload for change detection, EXCLUDING the wall-clock timestamps that
    change every tick (top-level and status.timestamp) — otherwise the hash always
    differs and the 'send only when state changes' guard never skips."""
    stable = {k: v for k, v in payload.items() if k != "timestamp"}
    status = stable.get("status")
    if isinstance(status, dict) and "timestamp" in status:
        status = {k: v for k, v in status.items() if k != "timestamp"}
        stable["status"] = status
    return hash(json.dumps(stable, sort_keys=True, default=str))


async def get_shared_state(min_interval: float = 1.5) -> tuple[int, dict]:
    """Return (hash, payload), recomputing at most once per ``min_interval`` seconds."""
    import time

    now = time.monotonic()
    async with _shared_lock:
        if _shared_state["payload"] is None or (now - _shared_state["at"]) >= min_interval:
            payload = await gather_full_state()
            _shared_state["payload"] = payload
            _shared_state["hash"] = _state_hash(payload)
            _shared_state["at"] = now
        return _shared_state["hash"], _shared_state["payload"]


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates.

    Sends consolidated 'update' messages only when state changes. State is gathered
    once per tick and shared across all connections.
    """
    await manager.connect(websocket)
    last_hash = 0
    try:
        while True:
            state_hash, full_state = await get_shared_state()
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
    plan (bool -> permission_mode), agents (dict). Returns None if nothing set.
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
    return profile or None


@app.post("/api/control/pause")
async def control_pause():
    control.submit({"type": "pause"})
    return {"ok": True, "action": "pause"}


@app.post("/api/control/resume")
async def control_resume():
    control.submit({"type": "resume"})
    return {"ok": True, "action": "resume"}


@app.post("/api/control/inject")
async def control_inject(body: dict = Body(...)):
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
    control.submit(command)
    return {"ok": True, "action": "inject", "target": command["target"]}


@app.post("/api/control/mode")
async def control_mode(body: dict = Body(...)):
    target = body.get("target")
    if not target or not _well_formed_worker_id(target):
        raise HTTPException(status_code=400, detail="valid target worker id required")
    # clear=true removes any standing per-worker mode override (back to lane/auto).
    if body.get("clear"):
        control.submit({"type": "set_mode", "target": target, "clear": True})
        return {"ok": True, "action": "clear_mode", "target": target}
    profile = _build_profile_dict(body)
    if not profile:
        raise HTTPException(status_code=400, detail="no mode fields provided")
    control.submit({"type": "set_mode", "target": target, "profile": profile})
    return {"ok": True, "action": "set_mode", "target": target, "profile": profile}


@app.post("/api/control/config")
async def control_config(body: dict = Body(...)):
    command = {"type": "set_config"}
    for key in ("model_tiering", "effort_dial", "dynamic_agents"):
        if key in body:
            command[key] = bool(body[key])
    control.submit(command)
    return {"ok": True, "action": "set_config", "config": command}


@app.post("/api/control/cancel")
async def control_cancel(body: dict = Body(...)):
    task_id = body.get("task_id")
    if not task_id:
        raise HTTPException(status_code=400, detail="task_id required")
    control.submit({"type": "cancel", "task_id": task_id})
    return {"ok": True, "action": "cancel", "task_id": task_id}


# Utility function to be used by orchestrator
def log_terminal_output(terminal_id: str, output: str) -> None:
    """Utility function for orchestrator to log terminal output."""
    save_terminal_output(terminal_id, output)


if __name__ == "__main__":
    import uvicorn

    # Ensure directories exist
    config.ensure_dirs()
    ensure_terminal_output_dir()

    uvicorn.run(app, host="0.0.0.0", port=8420)
