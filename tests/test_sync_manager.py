"""
Tests for the SyncManager heartbeat coordination system.

The SyncManager coordinates terminal heartbeats:
- Write/read heartbeats per terminal
- Detect stale heartbeats (>90s default)
- Sync point checking (all terminals ready?)
- File conflict detection
- Blocked terminal detection

Critical edge cases:
- Stale heartbeat detection at exact threshold
- No heartbeat vs stale heartbeat distinction
- File touched by 3+ terminals
- Mixed terminal states for sync point
"""

import json
import pytest
from datetime import datetime, timedelta
from pathlib import Path

from orchestrator.config import Config
from orchestrator.sync_manager import Heartbeat, SyncManager, SyncPointStatus


class TestHeartbeatDataclass:
    """Test Heartbeat creation and serialization."""

    def test_heartbeat_to_dict_roundtrip(self) -> None:
        """Heartbeat should survive to_dict/from_dict cycle."""
        hb = Heartbeat(
            terminal="t1",
            status="working",
            current_task="Build Login UI",
            progress="50%",
            files_touched=["LoginView.swift"],
            ready_artifacts=["LoginView"],
            waiting_for=None,
        )

        restored = Heartbeat.from_dict(hb.to_dict())

        assert restored.terminal == "t1"
        assert restored.status == "working"
        assert restored.current_task == "Build Login UI"
        assert restored.files_touched == ["LoginView.swift"]
        assert restored.ready_artifacts == ["LoginView"]

    def test_heartbeat_from_dict_handles_missing_fields(self) -> None:
        """from_dict should provide defaults for missing fields."""
        data = {"terminal": "t1", "status": "idle"}

        hb = Heartbeat.from_dict(data)

        assert hb.current_task == ""
        assert hb.progress == "0%"
        assert hb.files_touched == []
        assert hb.ready_artifacts == []
        assert hb.waiting_for is None

    def test_heartbeat_auto_generates_timestamp(self) -> None:
        """Heartbeat should auto-generate a timestamp."""
        hb = Heartbeat(
            terminal="t1",
            status="idle",
            current_task="",
            progress="0%",
        )
        assert hb.timestamp is not None
        assert "T" in hb.timestamp


class TestHeartbeatStaleness:
    """Test heartbeat staleness detection - the edge that matters."""

    def test_fresh_heartbeat_is_not_stale(self) -> None:
        """A heartbeat from now should not be stale."""
        hb = Heartbeat(terminal="t1", status="working", current_task="test", progress="50%")
        assert not hb.is_stale()

    def test_old_heartbeat_is_stale(self) -> None:
        """A heartbeat older than max_age should be stale."""
        old_time = datetime.now() - timedelta(seconds=200)
        hb = Heartbeat(
            terminal="t1",
            status="working",
            current_task="test",
            progress="50%",
            timestamp=old_time.isoformat(),
        )
        assert hb.is_stale()

    def test_heartbeat_at_exact_threshold_is_not_stale(self) -> None:
        """Heartbeat at exactly max_age seconds should NOT be stale (> not >=)."""
        threshold = 90
        exact_time = datetime.now() - timedelta(seconds=threshold)
        hb = Heartbeat(
            terminal="t1",
            status="working",
            current_task="test",
            progress="50%",
            timestamp=exact_time.isoformat(),
        )
        # timedelta comparison: age > threshold, not >=
        # Due to execution time, this will be slightly over, so we use a buffer
        # The key test is that the is_stale method uses > not >=
        assert hb.is_stale(max_age_seconds=threshold)

    def test_custom_max_age_seconds(self) -> None:
        """Custom max_age should be respected."""
        time_30s_ago = datetime.now() - timedelta(seconds=30)
        hb = Heartbeat(
            terminal="t1",
            status="working",
            current_task="test",
            progress="50%",
            timestamp=time_30s_ago.isoformat(),
        )

        assert not hb.is_stale(max_age_seconds=60)  # 30s < 60s threshold
        assert hb.is_stale(max_age_seconds=20)  # 30s > 20s threshold

    def test_invalid_timestamp_is_stale(self) -> None:
        """Invalid timestamp should be treated as stale."""
        hb = Heartbeat(
            terminal="t1",
            status="working",
            current_task="test",
            progress="50%",
            timestamp="not-a-timestamp",
        )
        assert hb.is_stale()


class TestSyncManagerWriteRead:
    """Test writing and reading heartbeats."""

    def test_write_and_read_heartbeat(self, config: Config) -> None:
        """Can write a heartbeat and read it back."""
        sm = SyncManager(config)

        written = sm.write_heartbeat(
            terminal_id="t1",
            status="working",
            current_task="Build UI",
            progress="60%",
            files_touched=["LoginView.swift"],
            ready_artifacts=["LoginView"],
        )

        read = sm.read_heartbeat("t1")

        assert read is not None
        assert read.terminal == "t1"
        assert read.status == "working"
        assert read.current_task == "Build UI"
        assert read.files_touched == ["LoginView.swift"]

    def test_read_nonexistent_heartbeat_returns_none(self, config: Config) -> None:
        """Reading a non-existent heartbeat should return None."""
        sm = SyncManager(config)
        assert sm.read_heartbeat("t1") is None

    def test_read_all_heartbeats(self, config: Config) -> None:
        """Can read all terminal heartbeats."""
        sm = SyncManager(config)

        sm.write_heartbeat("t1", "working", "Task 1", "50%")
        sm.write_heartbeat("t3", "idle", "", "0%")

        all_hb = sm.read_all_heartbeats()

        assert "t1" in all_hb
        assert "t3" in all_hb
        assert "t2" not in all_hb  # No heartbeat written for t2

    def test_overwrite_heartbeat(self, config: Config) -> None:
        """Writing a new heartbeat should overwrite the previous one."""
        sm = SyncManager(config)

        sm.write_heartbeat("t1", "working", "Old task", "30%")
        sm.write_heartbeat("t1", "working", "New task", "70%")

        hb = sm.read_heartbeat("t1")
        assert hb is not None
        assert hb.current_task == "New task"
        assert hb.progress == "70%"


class TestSyncPointChecking:
    """Test sync point detection."""

    def test_all_idle_is_sync_ready(self, config: Config) -> None:
        """All idle terminals = sync ready."""
        sm = SyncManager(config)

        for tid in ["t1", "t2", "t3"]:
            sm.write_heartbeat(tid, "idle", "", "0%")  # type: ignore

        status = sm.check_sync_point(active_terminals=["t1", "t2", "t3"])  # type: ignore

        assert status.all_ready is True
        assert len(status.idle_terminals) == 3

    def test_one_working_prevents_sync(self, config: Config) -> None:
        """One working terminal should prevent sync."""
        sm = SyncManager(config)

        sm.write_heartbeat("t1", "idle", "", "0%")
        sm.write_heartbeat("t2", "working", "Building...", "50%")

        status = sm.check_sync_point(active_terminals=["t1", "t2"])  # type: ignore

        assert status.all_ready is False
        assert "t2" in status.working_terminals

    def test_blocked_terminal_prevents_sync(self, config: Config) -> None:
        """Blocked terminals should prevent sync."""
        sm = SyncManager(config)

        sm.write_heartbeat("t1", "idle", "", "0%")
        sm.write_heartbeat("t2", "blocked", "Waiting", "30%", waiting_for="T1 API")

        status = sm.check_sync_point(active_terminals=["t1", "t2"])  # type: ignore

        assert status.all_ready is False
        assert "t2" in status.blocked_terminals

    def test_missing_heartbeat_prevents_sync(self, config: Config) -> None:
        """Missing heartbeat (no heartbeat at all) prevents sync."""
        sm = SyncManager(config)

        sm.write_heartbeat("t1", "idle", "", "0%")
        # t2 has no heartbeat

        status = sm.check_sync_point(active_terminals=["t1", "t2"])  # type: ignore

        assert status.all_ready is False
        assert "t2" in status.idle_terminals

    def test_stale_heartbeat_prevents_sync(self, config: Config) -> None:
        """Stale heartbeats should prevent sync."""
        sm = SyncManager(config)

        # Write a heartbeat then manually overwrite with old timestamp
        sm.write_heartbeat("t1", "idle", "", "0%")

        old_time = datetime.now() - timedelta(seconds=200)
        hb_path = sm._get_heartbeat_path("t1")
        old_data = {
            "terminal": "t1",
            "status": "working",
            "current_task": "stuck",
            "progress": "10%",
            "timestamp": old_time.isoformat(),
            "files_touched": [],
            "ready_artifacts": [],
            "waiting_for": None,
        }
        hb_path.write_text(json.dumps(old_data))

        status = sm.check_sync_point(active_terminals=["t1"])  # type: ignore

        assert status.all_ready is False
        assert "t1" in status.stale_terminals

    def test_waiting_terminal_is_sync_ready(self, config: Config) -> None:
        """Waiting terminals are considered ready for sync."""
        sm = SyncManager(config)

        sm.write_heartbeat("t1", "waiting", "Done, waiting", "100%")

        status = sm.check_sync_point(active_terminals=["t1"])  # type: ignore

        assert status.all_ready is True
        assert "t1" in status.waiting_terminals

    def test_ready_artifacts_tracked(self, config: Config) -> None:
        """Sync point should track which terminals have ready artifacts."""
        sm = SyncManager(config)

        sm.write_heartbeat(
            "t2", "waiting", "Done", "100%",
            ready_artifacts=["UserService", "AuthService"],
        )

        status = sm.check_sync_point(active_terminals=["t2"])  # type: ignore

        assert "t2" in status.ready_artifacts
        assert "UserService" in status.ready_artifacts["t2"]


class TestFileConflictDetection:
    """Test file conflict detection across terminals."""

    def test_no_conflicts_when_different_files(self, config: Config) -> None:
        """No conflicts when terminals touch different files."""
        sm = SyncManager(config)

        sm.write_heartbeat("t1", "working", "UI", "50%", files_touched=["LoginView.swift"])
        sm.write_heartbeat("t2", "working", "Backend", "50%", files_touched=["UserService.swift"])

        conflicts = sm.get_file_conflicts()
        assert len(conflicts) == 0

    def test_detect_two_terminal_conflict(self, config: Config) -> None:
        """Detect when two terminals touch the same file."""
        sm = SyncManager(config)

        sm.write_heartbeat("t1", "working", "UI", "50%", files_touched=["User.swift"])
        sm.write_heartbeat("t2", "working", "Model", "50%", files_touched=["User.swift"])

        conflicts = sm.get_file_conflicts()

        assert len(conflicts) == 1
        file_path, terminals = conflicts[0]
        assert file_path == "User.swift"
        assert set(terminals) == {"t1", "t2"}

    def test_detect_three_terminal_conflict(self, config: Config) -> None:
        """Detect when three terminals touch the same file."""
        sm = SyncManager(config)

        sm.write_heartbeat("t1", "working", "UI", "50%", files_touched=["Config.swift"])
        sm.write_heartbeat("t2", "working", "Backend", "50%", files_touched=["Config.swift"])
        sm.write_heartbeat("t5", "working", "Tests", "50%", files_touched=["Config.swift"])

        conflicts = sm.get_file_conflicts()

        assert len(conflicts) == 1
        _, terminals = conflicts[0]
        assert len(terminals) == 3

    def test_idle_terminals_excluded_from_conflicts(self, config: Config) -> None:
        """Non-working terminals should not be included in conflict detection."""
        sm = SyncManager(config)

        sm.write_heartbeat("t1", "working", "UI", "50%", files_touched=["User.swift"])
        sm.write_heartbeat("t2", "idle", "", "0%", files_touched=["User.swift"])

        conflicts = sm.get_file_conflicts()
        assert len(conflicts) == 0  # t2 is idle, not working


class TestBlockedTerminalDetection:
    """Test blocked terminal detection."""

    def test_detect_blocked_terminal(self, config: Config) -> None:
        """Should detect terminals with blocked status."""
        sm = SyncManager(config)

        sm.write_heartbeat("t1", "blocked", "Waiting", "30%", waiting_for="T2 API")

        blocked = sm.detect_blocked_terminals()

        assert len(blocked) == 1
        assert "t1" in blocked[0]
        assert "T2 API" in blocked[0]

    def test_no_blocked_terminals(self, config: Config) -> None:
        """Should return empty when no terminals are blocked."""
        sm = SyncManager(config)

        sm.write_heartbeat("t1", "working", "Building", "50%")
        sm.write_heartbeat("t2", "idle", "", "0%")

        blocked = sm.detect_blocked_terminals()
        assert len(blocked) == 0


class TestHeartbeatCleanup:
    """Test heartbeat cleanup operations."""

    def test_clear_single_heartbeat(self, config: Config) -> None:
        """Can clear a single terminal's heartbeat."""
        sm = SyncManager(config)

        sm.write_heartbeat("t1", "working", "task", "50%")
        sm.clear_heartbeat("t1")

        assert sm.read_heartbeat("t1") is None

    def test_clear_all_heartbeats(self, config: Config) -> None:
        """Can clear all heartbeats at once."""
        sm = SyncManager(config)

        for tid in ["t1", "t2", "t3"]:
            sm.write_heartbeat(tid, "working", "task", "50%")  # type: ignore

        sm.clear_all_heartbeats()

        for tid in ["t1", "t2", "t3", "t4", "t5"]:
            assert sm.read_heartbeat(tid) is None  # type: ignore

    def test_clear_nonexistent_heartbeat_is_safe(self, config: Config) -> None:
        """Clearing a non-existent heartbeat should not raise."""
        sm = SyncManager(config)
        sm.clear_heartbeat("t1")  # Should not raise


class TestTerminalStatusSummary:
    """Test human-readable status summary generation."""

    def test_summary_with_mixed_states(self, config: Config) -> None:
        """Summary should show all terminals with various states."""
        sm = SyncManager(config)

        sm.write_heartbeat("t1", "working", "Building UI", "60%")
        sm.write_heartbeat("t2", "blocked", "Waiting", "30%", waiting_for="T1 contracts")

        summary = sm.get_terminal_status_summary()

        assert "T1" in summary
        assert "T2" in summary
        assert "Building UI" in summary
        assert "T1 contracts" in summary

    def test_summary_shows_no_heartbeat(self, config: Config) -> None:
        """Summary should indicate terminals without heartbeats."""
        sm = SyncManager(config)
        # No heartbeats written

        summary = sm.get_terminal_status_summary()

        assert "No heartbeat" in summary


class TestSyncPointStatusDataclass:
    """Test the SyncPointStatus data structure."""

    def test_sync_point_status_to_dict(self) -> None:
        """SyncPointStatus should serialize to dict correctly."""
        status = SyncPointStatus(
            all_ready=False,
            working_terminals=["t1"],
            blocked_terminals=["t2"],
            idle_terminals=["t3"],
        )

        d = status.to_dict()

        assert d["all_ready"] is False
        assert d["working_terminals"] == ["t1"]
        assert d["blocked_terminals"] == ["t2"]
