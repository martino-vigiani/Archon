"""
Sync Manager for terminal heartbeats and synchronization.

Manages real-time status updates from terminals, enabling the orchestrator
to make dynamic decisions about task assignments and detect blocking conditions.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from .config import Config, TerminalID


HeartbeatStatus = Literal["working", "waiting", "blocked", "idle"]


@dataclass
class Heartbeat:
    """Heartbeat data from a terminal."""

    terminal: TerminalID
    status: HeartbeatStatus
    current_task: str
    progress: str
    files_touched: list[str] = field(default_factory=list)
    ready_artifacts: list[str] = field(default_factory=list)
    waiting_for: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        """Convert heartbeat to dictionary."""
        return {
            "terminal": self.terminal,
            "status": self.status,
            "current_task": self.current_task,
            "progress": self.progress,
            "files_touched": self.files_touched,
            "ready_artifacts": self.ready_artifacts,
            "waiting_for": self.waiting_for,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Heartbeat":
        """Create heartbeat from dictionary."""
        return cls(
            terminal=data.get("terminal", "unknown"),
            status=data.get("status", "idle"),
            current_task=data.get("current_task", ""),
            progress=data.get("progress", "0%"),
            files_touched=data.get("files_touched", []),
            ready_artifacts=data.get("ready_artifacts", []),
            waiting_for=data.get("waiting_for"),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
        )

    def is_stale(self, max_age_seconds: int = 90) -> bool:
        """
        Check if heartbeat is stale (not updated recently).

        Args:
            max_age_seconds: Maximum age in seconds before considered stale

        Returns:
            True if heartbeat is older than max_age_seconds
        """
        try:
            heartbeat_time = datetime.fromisoformat(self.timestamp)
            age = datetime.now() - heartbeat_time
            return age > timedelta(seconds=max_age_seconds)
        except (ValueError, TypeError):
            return True


@dataclass
class SyncPointStatus:
    """Aggregated status of all terminals at a sync point."""

    all_ready: bool
    working_terminals: list[TerminalID] = field(default_factory=list)
    waiting_terminals: list[TerminalID] = field(default_factory=list)
    blocked_terminals: list[TerminalID] = field(default_factory=list)
    idle_terminals: list[TerminalID] = field(default_factory=list)
    stale_terminals: list[TerminalID] = field(default_factory=list)
    ready_artifacts: dict[TerminalID, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "all_ready": self.all_ready,
            "working_terminals": self.working_terminals,
            "waiting_terminals": self.waiting_terminals,
            "blocked_terminals": self.blocked_terminals,
            "idle_terminals": self.idle_terminals,
            "stale_terminals": self.stale_terminals,
            "ready_artifacts": self.ready_artifacts,
        }


class SyncManager:
    """
    Manages terminal heartbeats for real-time synchronization.

    The SyncManager provides a lightweight coordination mechanism where
    terminals write their status every 30 seconds. The orchestrator uses
    these heartbeats to:
    - Detect when terminals are blocked or waiting
    - Know when all terminals are ready for a sync point
    - Track which files are being modified to avoid conflicts
    - Identify available artifacts for other terminals
    """

    def __init__(self, config: Config):
        """
        Initialize the SyncManager.

        Args:
            config: Orchestrator configuration
        """
        self.config = config
        self._ensure_dirs()

    @property
    def state_dir(self) -> Path:
        """Get the state directory for heartbeats."""
        return self.config.orchestra_dir / "state"

    def _ensure_dirs(self) -> None:
        """Create state directory if it doesn't exist."""
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def _get_heartbeat_path(self, terminal_id: TerminalID) -> Path:
        """Get the path to a terminal's heartbeat file."""
        return self.state_dir / f"{terminal_id}_heartbeat.json"

    def write_heartbeat(
        self,
        terminal_id: TerminalID,
        status: HeartbeatStatus,
        current_task: str,
        progress: str,
        files_touched: list[str] | None = None,
        ready_artifacts: list[str] | None = None,
        waiting_for: str | None = None,
    ) -> Heartbeat:
        """
        Write a heartbeat for a terminal.

        Args:
            terminal_id: Terminal identifier
            status: Current status (working, waiting, blocked, idle)
            current_task: Description of current task
            progress: Progress description or percentage
            files_touched: List of files currently being modified
            ready_artifacts: List of artifacts ready for other terminals
            waiting_for: What the terminal is waiting for (if status is waiting/blocked)

        Returns:
            The created Heartbeat object
        """
        heartbeat = Heartbeat(
            terminal=terminal_id,
            status=status,
            current_task=current_task,
            progress=progress,
            files_touched=files_touched or [],
            ready_artifacts=ready_artifacts or [],
            waiting_for=waiting_for,
        )

        heartbeat_path = self._get_heartbeat_path(terminal_id)
        heartbeat_path.write_text(json.dumps(heartbeat.to_dict(), indent=2))

        return heartbeat

    def read_heartbeat(self, terminal_id: TerminalID) -> Heartbeat | None:
        """
        Read a terminal's heartbeat.

        Args:
            terminal_id: Terminal identifier

        Returns:
            Heartbeat object if exists and valid, None otherwise
        """
        heartbeat_path = self._get_heartbeat_path(terminal_id)

        if not heartbeat_path.exists():
            return None

        try:
            data = json.loads(heartbeat_path.read_text())
            return Heartbeat.from_dict(data)
        except (json.JSONDecodeError, KeyError, IOError) as e:
            print(f"[SyncManager] Error reading heartbeat for {terminal_id}: {e}")
            return None

    def read_all_heartbeats(self) -> dict[str, dict]:
        """
        Read all terminal heartbeats.

        Returns:
            Dictionary mapping terminal IDs to heartbeat dictionaries
        """
        heartbeats = {}

        for terminal_id in ["t1", "t2", "t3", "t4", "t5"]:
            heartbeat = self.read_heartbeat(terminal_id)  # type: ignore
            if heartbeat:
                heartbeats[terminal_id] = heartbeat.to_dict()

        return heartbeats

    def check_sync_point(self, active_terminals: list[TerminalID] | None = None) -> SyncPointStatus:
        """
        Check if all terminals are ready for synchronization.

        Args:
            active_terminals: List of terminals to check. If None, checks all terminals.

        Returns:
            SyncPointStatus with aggregated information
        """
        terminals_to_check = active_terminals or ["t1", "t2", "t3", "t4", "t5"]  # type: ignore

        status = SyncPointStatus(all_ready=True)
        missing_heartbeat_count = 0

        for terminal_id in terminals_to_check:
            heartbeat = self.read_heartbeat(terminal_id)  # type: ignore

            if not heartbeat:
                # No heartbeat = terminal not started or crashed
                status.idle_terminals.append(terminal_id)  # type: ignore
                missing_heartbeat_count += 1
                continue

            if heartbeat.is_stale():
                status.stale_terminals.append(terminal_id)  # type: ignore
                continue

            # Categorize by status
            if heartbeat.status == "working":
                status.working_terminals.append(terminal_id)  # type: ignore
            elif heartbeat.status == "waiting":
                status.waiting_terminals.append(terminal_id)  # type: ignore
                # Waiting is considered "ready" for sync
            elif heartbeat.status == "blocked":
                status.blocked_terminals.append(terminal_id)  # type: ignore
            elif heartbeat.status == "idle":
                status.idle_terminals.append(terminal_id)  # type: ignore
                # Idle is considered "ready"

            # Track ready artifacts
            if heartbeat.ready_artifacts:
                status.ready_artifacts[terminal_id] = heartbeat.ready_artifacts  # type: ignore

        # All ready if no terminals are working, blocked, stale, or missing
        status.all_ready = (
            len(status.working_terminals) == 0
            and len(status.blocked_terminals) == 0
            and len(status.stale_terminals) == 0
            and missing_heartbeat_count == 0
        )

        return status

    def detect_blocked_terminals(self) -> list[str]:
        """
        Detect terminals that are blocked and what they're waiting for.

        Returns:
            List of strings describing blocked terminals
        """
        blocked = []

        for terminal_id in ["t1", "t2", "t3", "t4", "t5"]:
            heartbeat = self.read_heartbeat(terminal_id)  # type: ignore

            if heartbeat and heartbeat.status == "blocked":
                waiting_for = heartbeat.waiting_for or "unknown reason"
                blocked.append(f"{terminal_id}: blocked waiting for {waiting_for}")

        return blocked

    def get_terminal_status_summary(self) -> str:
        """
        Get a human-readable summary of all terminal statuses.

        Returns:
            Formatted string with terminal status overview
        """
        lines = ["# Terminal Status Summary\n"]

        for terminal_id in ["t1", "t2", "t3", "t4", "t5"]:
            heartbeat = self.read_heartbeat(terminal_id)  # type: ignore
            terminal_config = self.config.get_terminal_config(terminal_id)  # type: ignore

            if not heartbeat:
                lines.append(f"**{terminal_id.upper()}** ({terminal_config.role}): No heartbeat")
                continue

            age_info = ""
            if heartbeat.is_stale():
                try:
                    heartbeat_time = datetime.fromisoformat(heartbeat.timestamp)
                    age = int((datetime.now() - heartbeat_time).total_seconds())
                    age_info = f" (STALE - {age}s ago)"
                except (ValueError, TypeError):
                    age_info = " (STALE - invalid timestamp)"

            status_emoji = {
                "working": "🔨",
                "waiting": "⏸️",
                "blocked": "🚫",
                "idle": "💤",
            }

            emoji = status_emoji.get(heartbeat.status, "❓")
            lines.append(
                f"**{terminal_id.upper()}** ({terminal_config.role}): "
                f"{emoji} {heartbeat.status.upper()}{age_info}"
            )
            lines.append(f"  Task: {heartbeat.current_task}")
            lines.append(f"  Progress: {heartbeat.progress}")

            if heartbeat.waiting_for:
                lines.append(f"  Waiting for: {heartbeat.waiting_for}")

            if heartbeat.files_touched:
                files_str = ", ".join(heartbeat.files_touched[:3])
                if len(heartbeat.files_touched) > 3:
                    files_str += f" (+{len(heartbeat.files_touched) - 3} more)"
                lines.append(f"  Files: {files_str}")

            if heartbeat.ready_artifacts:
                artifacts_str = ", ".join(heartbeat.ready_artifacts[:3])
                if len(heartbeat.ready_artifacts) > 3:
                    artifacts_str += f" (+{len(heartbeat.ready_artifacts) - 3} more)"
                lines.append(f"  Ready artifacts: {artifacts_str}")

            lines.append("")

        return "\n".join(lines)

    def clear_heartbeat(self, terminal_id: TerminalID) -> None:
        """
        Clear a terminal's heartbeat.

        Args:
            terminal_id: Terminal identifier
        """
        heartbeat_path = self._get_heartbeat_path(terminal_id)
        if heartbeat_path.exists():
            heartbeat_path.unlink()

    def clear_all_heartbeats(self) -> None:
        """Clear all terminal heartbeats."""
        for terminal_id in ["t1", "t2", "t3", "t4", "t5"]:
            self.clear_heartbeat(terminal_id)  # type: ignore

    def get_file_conflicts(self) -> list[tuple[str, list[TerminalID]]]:
        """
        Detect files being touched by multiple terminals simultaneously.

        Returns:
            List of tuples (file_path, list_of_terminal_ids)
        """
        file_map: dict[str, list[TerminalID]] = {}

        for terminal_id in ["t1", "t2", "t3", "t4", "t5"]:
            heartbeat = self.read_heartbeat(terminal_id)  # type: ignore

            if heartbeat and heartbeat.status == "working":
                for file_path in heartbeat.files_touched:
                    if file_path not in file_map:
                        file_map[file_path] = []
                    file_map[file_path].append(terminal_id)  # type: ignore

        # Return only conflicts (files touched by 2+ terminals)
        conflicts = [(f, terminals) for f, terminals in file_map.items() if len(terminals) > 1]
        return conflicts
