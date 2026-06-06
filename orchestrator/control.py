"""
Control channel: a tiny file-based command bus for steering a running orchestrator.

The dashboard (a separate FastAPI process) cannot call the orchestrator's in-memory
methods directly. Instead it appends JSON command lines to
``.orchestra/control/commands.jsonl``; the orchestrator drains and applies them once
per loop tick. This mirrors Archon's existing file-based coordination (status.json,
message inboxes) and keeps the two processes decoupled.

Command shapes (``type`` is required):
    {"type": "pause"}
    {"type": "resume"}
    {"type": "inject", "title": str, "description": str,
        "target": "<agent id|null>", "priority": "high",
        "profile": {<ExecutionProfile dict, optional>}}
    {"type": "set_mode", "target": "<agent id>", "profile": {<ExecutionProfile dict>}}
    {"type": "set_config", "model_tiering": bool, "effort_dial": bool, "dynamic_agents": bool}
    {"type": "cancel", "task_id": str}
"""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from typing import Any


class ControlChannel:
    """Append/drain JSON commands via a newline-delimited file.

    Writers (dashboard) call :meth:`submit`. The single reader (orchestrator) calls
    :meth:`drain`, which returns all unread commands and advances a byte offset stored
    in a sidecar file so commands are processed exactly once across restarts.
    """

    def __init__(self, orchestra_dir: Path):
        self.dir = orchestra_dir / "control"
        self.commands_file = self.dir / "commands.jsonl"
        self.offset_file = self.dir / ".offset"

    def _ensure(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)

    def submit(self, command: dict[str, Any]) -> None:
        """Append a command (writer side; safe to call from another process)."""
        self._ensure()
        line = json.dumps(command, separators=(",", ":"), default=str)
        with open(self.commands_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def drain(self) -> list[dict[str, Any]]:
        """Return all unread commands and advance the offset (reader side)."""
        if not self.commands_file.exists():
            return []
        try:
            offset = int(self.offset_file.read_text()) if self.offset_file.exists() else 0
        except (ValueError, OSError):
            offset = 0

        # If the file shrank (rotated/cleared/recreated smaller than the stored offset),
        # restart from the beginning. This must be checked against the real file size:
        # seeking past EOF then calling f.tell() returns the seek position, not the size,
        # so a post-seek comparison would never detect the shrink.
        try:
            if self.commands_file.stat().st_size < offset:
                offset = 0
        except OSError:
            offset = 0

        try:
            with open(self.commands_file, encoding="utf-8") as f:
                f.seek(offset)
                new_data = f.read()
                new_offset = f.tell()
        except OSError:
            return []

        commands: list[dict[str, Any]] = []
        for raw in new_data.splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
                if isinstance(obj, dict) and "type" in obj:
                    commands.append(obj)
            except json.JSONDecodeError:
                continue

        self._ensure()
        with contextlib.suppress(OSError):
            self.offset_file.write_text(str(new_offset))
        return commands

    def reset(self) -> None:
        """Clear the command log and offset (e.g. at the start of a fresh run)."""
        self._ensure()
        try:
            self.commands_file.write_text("")
            self.offset_file.write_text("0")
        except OSError:
            pass
