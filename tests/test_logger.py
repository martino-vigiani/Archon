"""
Tests for the Event Logger system.

The EventLogger provides:
- JSON-based event logging to file
- Event persistence with auto-load
- Convenience methods for common events
- Recent event retrieval with reverse ordering
- Event clearing

All file I/O uses tmp_path - no real log files.
"""

import json
import pytest
from pathlib import Path

from orchestrator.logger import Event, EventLogger


class TestEventDataclass:
    """Test Event creation."""

    def test_event_fields(self) -> None:
        """Event should store all provided fields."""
        event = Event(
            timestamp="2024-01-01T00:00:00",
            type="task_start",
            terminal="t1",
            task_id="task_001",
            task_title="Build UI",
            message="Started building",
            details={"extra": "info"},
        )
        assert event.type == "task_start"
        assert event.terminal == "t1"
        assert event.details == {"extra": "info"}

    def test_event_optional_fields(self) -> None:
        """Optional fields should default to None."""
        event = Event(
            timestamp="2024-01-01T00:00:00",
            type="orchestrator_start",
            terminal=None,
            task_id=None,
            task_title=None,
            message="Started",
        )
        assert event.terminal is None
        assert event.details is None


class TestEventLoggerInit:
    """Test EventLogger initialization and persistence."""

    def test_creates_empty_logger(self, tmp_path: Path) -> None:
        """New logger with no file should start empty."""
        log_file = tmp_path / "events.json"
        logger = EventLogger(log_file)
        assert len(logger.events) == 0

    def test_loads_existing_events(self, tmp_path: Path) -> None:
        """Logger should load events from existing file."""
        log_file = tmp_path / "events.json"
        events = [
            {
                "timestamp": "2024-01-01T00:00:00",
                "type": "task_start",
                "terminal": "t1",
                "task_id": "task_001",
                "task_title": "Build UI",
                "message": "Started",
            }
        ]
        log_file.write_text(json.dumps(events))

        logger = EventLogger(log_file)
        assert len(logger.events) == 1
        assert logger.events[0].type == "task_start"

    def test_handles_corrupt_file(self, tmp_path: Path) -> None:
        """Corrupt JSON file should result in empty events."""
        log_file = tmp_path / "events.json"
        log_file.write_text("not valid json {{{")

        logger = EventLogger(log_file)
        assert len(logger.events) == 0

    def test_limits_loaded_events_to_100(self, tmp_path: Path) -> None:
        """Should only load last 100 events from file."""
        log_file = tmp_path / "events.json"
        events = [
            {
                "timestamp": f"2024-01-01T{i:05d}",
                "type": "task_start",
                "terminal": "t1",
                "task_id": f"task_{i}",
                "task_title": f"Task {i}",
                "message": f"Event {i}",
            }
            for i in range(150)
        ]
        log_file.write_text(json.dumps(events))

        logger = EventLogger(log_file)
        assert len(logger.events) == 100


class TestLogging:
    """Test event logging and persistence."""

    def test_log_creates_event(self, tmp_path: Path) -> None:
        """log() should add event to list and save."""
        logger = EventLogger(tmp_path / "events.json")
        logger.log("task_start", "Started task", terminal="t1", task_id="task_001")
        assert len(logger.events) == 1
        assert logger.events[0].type == "task_start"
        assert logger.events[0].terminal == "t1"

    def test_log_persists_to_file(self, tmp_path: Path) -> None:
        """Logged events should be saved to disk."""
        log_file = tmp_path / "events.json"
        logger = EventLogger(log_file)
        logger.log("orchestrator_start", "Started")

        assert log_file.exists()
        data = json.loads(log_file.read_text())
        assert len(data) == 1
        assert data[0]["type"] == "orchestrator_start"

    def test_log_creates_parent_dirs(self, tmp_path: Path) -> None:
        """Save should create parent directories if needed."""
        log_file = tmp_path / "deep" / "nested" / "events.json"
        logger = EventLogger(log_file)
        logger.log("orchestrator_start", "Started")
        assert log_file.exists()

    def test_multiple_events_accumulate(self, tmp_path: Path) -> None:
        """Multiple log calls should accumulate events."""
        logger = EventLogger(tmp_path / "events.json")
        logger.log("task_start", "Task 1")
        logger.log("task_complete", "Task 1 done")
        logger.log("task_start", "Task 2")
        assert len(logger.events) == 3


class TestGetRecent:
    """Test recent event retrieval."""

    def test_get_recent_default(self, tmp_path: Path) -> None:
        """get_recent should return events in reverse order."""
        logger = EventLogger(tmp_path / "events.json")
        logger.log("task_start", "First")
        logger.log("task_complete", "Second")

        recent = logger.get_recent()
        assert len(recent) == 2
        assert recent[0]["message"] == "Second"  # Most recent first
        assert recent[1]["message"] == "First"

    def test_get_recent_with_limit(self, tmp_path: Path) -> None:
        """get_recent should respect count parameter."""
        logger = EventLogger(tmp_path / "events.json")
        for i in range(10):
            logger.log("task_start", f"Event {i}")

        recent = logger.get_recent(count=3)
        assert len(recent) == 3

    def test_get_recent_returns_dicts(self, tmp_path: Path) -> None:
        """get_recent should return list of dicts, not Events."""
        logger = EventLogger(tmp_path / "events.json")
        logger.log("task_start", "Test")

        recent = logger.get_recent()
        assert isinstance(recent[0], dict)
        assert "timestamp" in recent[0]
        assert "type" in recent[0]


class TestClear:
    """Test event clearing."""

    def test_clear_removes_all_events(self, tmp_path: Path) -> None:
        """clear() should remove all events."""
        logger = EventLogger(tmp_path / "events.json")
        logger.log("task_start", "Event 1")
        logger.log("task_complete", "Event 2")

        logger.clear()
        assert len(logger.events) == 0

    def test_clear_persists_empty(self, tmp_path: Path) -> None:
        """clear() should save empty array to file."""
        log_file = tmp_path / "events.json"
        logger = EventLogger(log_file)
        logger.log("task_start", "Event")
        logger.clear()

        data = json.loads(log_file.read_text())
        assert data == []


class TestConvenienceMethods:
    """Test convenience logging methods."""

    def test_orchestrator_started(self, tmp_path: Path) -> None:
        """orchestrator_started should log start event."""
        logger = EventLogger(tmp_path / "events.json")
        logger.orchestrator_started("Build a meditation app")

        assert len(logger.events) == 1
        assert logger.events[0].type == "orchestrator_start"
        assert "meditation" in logger.events[0].message.lower()

    def test_orchestrator_stopped(self, tmp_path: Path) -> None:
        """orchestrator_stopped should log completion stats."""
        logger = EventLogger(tmp_path / "events.json")
        logger.orchestrator_stopped(completed=5, failed=1)

        assert logger.events[0].type == "orchestrator_stop"
        assert "5" in logger.events[0].message
        assert "1" in logger.events[0].message

    def test_task_started(self, tmp_path: Path) -> None:
        """task_started should log with terminal and task info."""
        logger = EventLogger(tmp_path / "events.json")
        logger.task_started("t1", "task_001", "Build Login UI")

        e = logger.events[0]
        assert e.type == "task_start"
        assert e.terminal == "t1"
        assert e.task_id == "task_001"
        assert "Build Login UI" in e.message

    def test_task_completed(self, tmp_path: Path) -> None:
        """task_completed should log completion."""
        logger = EventLogger(tmp_path / "events.json")
        logger.task_completed("t2", "task_002", "Build API")
        assert logger.events[0].type == "task_complete"

    def test_task_failed(self, tmp_path: Path) -> None:
        """task_failed should log with error details."""
        logger = EventLogger(tmp_path / "events.json")
        logger.task_failed("t1", "task_001", "Build UI", "Timeout")

        e = logger.events[0]
        assert e.type == "task_failed"
        assert e.details is not None
        assert e.details["error"] == "Timeout"

    def test_subagent_invoked(self, tmp_path: Path) -> None:
        """subagent_invoked should log subagent details."""
        logger = EventLogger(tmp_path / "events.json")
        logger.subagent_invoked("t1", "swiftui-crafter", "Build Views")

        e = logger.events[0]
        assert e.type == "subagent_invoked"
        assert e.details["subagent"] == "swiftui-crafter"

    def test_plan_created(self, tmp_path: Path) -> None:
        """plan_created should log task count."""
        logger = EventLogger(tmp_path / "events.json")
        logger.plan_created(8, "Build iOS meditation app")
        assert logger.events[0].type == "plan_created"
        assert "8" in logger.events[0].message

    def test_terminal_state_changed_busy(self, tmp_path: Path) -> None:
        """terminal_state_changed for busy should use terminal_busy type."""
        logger = EventLogger(tmp_path / "events.json")
        logger.terminal_state_changed("t1", "busy", "Building UI")
        assert logger.events[0].type == "terminal_busy"

    def test_terminal_state_changed_idle(self, tmp_path: Path) -> None:
        """terminal_state_changed for idle should use terminal_idle type."""
        logger = EventLogger(tmp_path / "events.json")
        logger.terminal_state_changed("t2", "idle")
        assert logger.events[0].type == "terminal_idle"

    def test_terminal_state_changed_error(self, tmp_path: Path) -> None:
        """terminal_state_changed for error should use terminal_error type."""
        logger = EventLogger(tmp_path / "events.json")
        logger.terminal_state_changed("t1", "error")
        assert logger.events[0].type == "terminal_error"


class TestLogEvent:
    """Test generic event logging."""

    def test_known_event_type(self, tmp_path: Path) -> None:
        """Known event types should be used directly."""
        logger = EventLogger(tmp_path / "events.json")
        logger.log_event("task_start", {"title": "Build UI"})
        assert logger.events[0].type == "task_start"

    def test_unknown_type_falls_back(self, tmp_path: Path) -> None:
        """Unknown event type should fall back to message_sent."""
        logger = EventLogger(tmp_path / "events.json")
        logger.log_event("custom_event", {"title": "Something"})
        assert logger.events[0].type == "message_sent"
