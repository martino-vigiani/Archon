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
import os
import stat
from pathlib import Path
from typing import Any

# Profile fields a remote/untrusted control-bus writer is allowed to set. This
# mirrors the dashboard's ``_build_profile_dict`` allowlist so a writer that
# bypasses the HTTP API (by appending straight to ``commands.jsonl``) cannot
# smuggle the dangerous fields (``add_dirs``, ``allowed_tools``,
# ``disallowed_tools``, ``bare``, ``max_turns``, ``fallback_model``) that widen
# a permission-bypassed worker's reach. The orchestrator still re-gates every
# profile via ``Config.gate_profile``; this is defense in depth at the boundary.
_ALLOWED_PROFILE_FIELDS = frozenset(
    {
        "model_tier",
        "model_override",
        "effort",
        "permission_mode",
        "agents",
        "append_system_prompt",
    }
)


def _sanitize_profile(profile: Any) -> Any:
    """Strip a control-bus profile dict down to the allowlisted fields.

    Non-dict profiles are returned unchanged (the orchestrator already ignores
    a non-dict profile). Unknown/dangerous keys are dropped silently.
    """
    if not isinstance(profile, dict):
        return profile
    return {k: v for k, v in profile.items() if k in _ALLOWED_PROFILE_FIELDS}


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
        # Restrict the control dir + command log to the owner: the bus can inject
        # tasks and steer a permission-bypassed worker, so another local account
        # must not be able to read or append to it.
        with contextlib.suppress(OSError):
            os.chmod(self.dir, stat.S_IRWXU)  # 0o700
        with contextlib.suppress(OSError):
            if self.commands_file.exists():
                os.chmod(self.commands_file, stat.S_IRUSR | stat.S_IWUSR)  # 0o600

    def submit(self, command: dict[str, Any]) -> None:
        """Append a command (writer side; safe to call from another process)."""
        self._ensure()
        line = json.dumps(command, separators=(",", ":"), default=str)
        with open(self.commands_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        with contextlib.suppress(OSError):
            os.chmod(self.commands_file, stat.S_IRUSR | stat.S_IWUSR)  # 0o600

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
                    # Defense in depth: a writer that bypasses the dashboard's
                    # field allowlist (by appending here directly) must not be
                    # able to inject dangerous profile fields. Sanitize any
                    # carried profile down to the allowlist before it reaches
                    # the orchestrator.
                    if isinstance(obj.get("profile"), dict):
                        obj["profile"] = _sanitize_profile(obj["profile"])
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
