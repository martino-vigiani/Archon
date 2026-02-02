"""
Event Logger for Archon Orchestrator.

Logs all events (task starts, completions, subagent usage, errors)
to a JSON file that the dashboard can read.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Literal
from dataclasses import dataclass, asdict

EventType = Literal[
    "orchestrator_start",
    "orchestrator_stop",
    "task_start",
    "task_complete",
    "task_failed",
    "task_injected",
    "task_cancelled",
    "terminal_busy",
    "terminal_idle",
    "terminal_error",
    "subagent_invoked",
    "message_sent",
    "plan_created",
    "execution_paused",
    "execution_resumed",
]


@dataclass
class Event:
    timestamp: str
    type: EventType
    terminal: str | None
    task_id: str | None
    task_title: str | None
    message: str
    details: dict | None = None


class EventLogger:
    """Logs events to a JSON file for dashboard consumption."""

    def __init__(self, log_file: Path):
        self.log_file = log_file
        self.events: list[Event] = []
        self._load()

    def _load(self):
        """Load existing events from file."""
        try:
            if self.log_file.exists():
                data = json.loads(self.log_file.read_text())
                self.events = [Event(**e) for e in data[-100:]]  # Keep last 100
        except (json.JSONDecodeError, FileNotFoundError):
            self.events = []

    def _save(self):
        """Save events to file."""
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        data = [asdict(e) for e in self.events[-100:]]
        self.log_file.write_text(json.dumps(data, indent=2))

    def log(
        self,
        event_type: EventType,
        message: str,
        terminal: str | None = None,
        task_id: str | None = None,
        task_title: str | None = None,
        details: dict | None = None,
    ):
        """Log an event."""
        event = Event(
            timestamp=datetime.now().isoformat(),
            type=event_type,
            terminal=terminal,
            task_id=task_id,
            task_title=task_title,
            message=message,
            details=details,
        )
        self.events.append(event)
        self._save()

    def get_recent(self, count: int = 50) -> list[dict]:
        """Get recent events as dicts."""
        return [asdict(e) for e in self.events[-count:]][::-1]

    def clear(self):
        """Clear all events."""
        self.events = []
        self._save()

    # Convenience methods
    def orchestrator_started(self, task: str):
        self.log("orchestrator_start", f"Started with task: {task[:50]}...")

    def orchestrator_stopped(self, completed: int, failed: int):
        self.log("orchestrator_stop", f"Stopped. Completed: {completed}, Failed: {failed}")

    def task_started(self, terminal: str, task_id: str, title: str):
        self.log("task_start", f"Started: {title}", terminal, task_id, title)

    def task_completed(self, terminal: str, task_id: str, title: str):
        self.log("task_complete", f"Completed: {title}", terminal, task_id, title)

    def task_failed(self, terminal: str, task_id: str, title: str, error: str):
        self.log("task_failed", f"Failed: {title} - {error}", terminal, task_id, title, {"error": error})

    def subagent_invoked(self, terminal: str, subagent: str, task_title: str):
        self.log(
            "subagent_invoked",
            f"Subagent {subagent} invoked",
            terminal,
            task_title=task_title,
            details={"subagent": subagent},
        )

    def plan_created(self, task_count: int, summary: str):
        self.log("plan_created", f"Plan created with {task_count} tasks: {summary[:50]}...")

    def terminal_state_changed(self, terminal: str, state: str, task_title: str | None = None):
        event_type = "terminal_busy" if state == "busy" else "terminal_idle" if state == "idle" else "terminal_error"
        msg = f"Terminal {terminal} is {state}"
        if task_title:
            msg += f" - working on: {task_title}"
        self.log(event_type, msg, terminal, task_title=task_title)

    def log_event(self, event_type: str, details: dict | None = None):
        """Generic event logging for custom events."""
        # Use a safe type cast for custom events
        safe_type = event_type if event_type in [
            "orchestrator_start", "orchestrator_stop", "task_start", "task_complete",
            "task_failed", "task_injected", "task_cancelled", "terminal_busy",
            "terminal_idle", "terminal_error", "subagent_invoked", "message_sent",
            "plan_created", "execution_paused", "execution_resumed"
        ] else "message_sent"  # Fallback to a valid type

        message = details.get("title", event_type) if details else event_type
        self.log(safe_type, message, details=details)  # type: ignore
