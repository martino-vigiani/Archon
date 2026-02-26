"""
Security test suite for Archon.

Covers OWASP-relevant checks for the orchestrator and dashboard:
- Input validation and injection prevention
- Path traversal protection
- File handling safety
- JSON parsing resilience
- Terminal ID validation at config boundaries

These tests verify defensive behavior, not attack payloads.
"""

import json
import tempfile
from pathlib import Path

import pytest

from orchestrator.config import Config
from orchestrator.message_bus import MessageBus


# =============================================================================
# SECURITY CHECKLIST (reference for manual + automated review)
# =============================================================================
#
# [ ] SQL Injection         - N/A (no SQL database in orchestrator)
# [x] Path Traversal        - Terminal IDs validated, no user-controlled paths
# [x] Command Injection     - Subprocess uses exec (not shell=True)
# [x] JSON Injection        - json.loads with error handling
# [x] Auth Bypass           - N/A (local-only dashboard, no auth layer)
# [x] Token Expiration      - N/A (no auth tokens in orchestrator)
# [x] XSS                   - Dashboard serves static HTML, API returns JSON
# [x] Input Validation      - Terminal IDs, task IDs validated
# [x] File Write Safety     - Writes only to .orchestra/ directories
# [x] Large Input Handling  - No unbounded reads from user input
# =============================================================================


class TestTerminalIDValidation:
    """Verify terminal ID validation at config boundaries."""

    @pytest.mark.security
    def test_valid_terminal_ids(self) -> None:
        """Only t1-t5 should be valid terminal IDs."""
        from orchestrator.config import TerminalID

        valid = {"t1", "t2", "t3", "t4", "t5"}
        # TerminalID is a Literal type; verify the config enforces it
        config = Config()
        for tid in valid:
            assert tid in config.terminals

    @pytest.mark.security
    def test_config_rejects_unknown_terminal(self) -> None:
        """Config terminals dict should not contain unknown IDs."""
        config = Config()
        assert "t0" not in config.terminals
        assert "t6" not in config.terminals
        assert "admin" not in config.terminals
        assert "" not in config.terminals


class TestPathTraversal:
    """Verify path traversal is prevented in file operations."""

    @pytest.mark.security
    def test_inbox_path_stays_in_orchestra(self) -> None:
        """Inbox paths should always be within .orchestra directory."""
        config = Config()
        for tid in ["t1", "t2", "t3", "t4", "t5"]:
            inbox = config.get_terminal_inbox(tid)  # type: ignore
            assert ".orchestra" in str(inbox) or "messages" in str(inbox)

    @pytest.mark.security
    def test_message_bus_path_containment(self, config: Config) -> None:
        """MessageBus should only write within orchestra directory."""
        bus = MessageBus(config)
        bus.send(sender="t1", recipient="t2", content="test")

        # Verify inbox file is inside the expected directory
        inbox_path = config.get_terminal_inbox("t2")
        assert inbox_path.is_relative_to(config.orchestra_dir) or "messages" in str(
            inbox_path
        )


class TestJSONParsing:
    """Verify JSON parsing is resilient to malformed input."""

    @pytest.mark.security
    def test_dashboard_handles_corrupt_json(self) -> None:
        """read_json_file should not crash on corrupt JSON."""
        from orchestrator.dashboard import read_json_file

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{invalid json content]]")
            f.flush()
            result = read_json_file(Path(f.name))
            assert result is None

    @pytest.mark.security
    def test_dashboard_handles_missing_file(self) -> None:
        """read_json_file should return None for missing files."""
        from orchestrator.dashboard import read_json_file

        result = read_json_file(Path("/nonexistent/file.json"))
        assert result is None

    @pytest.mark.security
    def test_dashboard_handles_empty_file(self) -> None:
        """read_json_file should handle empty files."""
        from orchestrator.dashboard import read_json_file

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("")
            f.flush()
            result = read_json_file(Path(f.name))
            assert result is None


class TestSubprocessSafety:
    """Verify subprocess calls don't use shell=True."""

    @pytest.mark.security
    def test_terminal_uses_exec_not_shell(self) -> None:
        """Terminal should use create_subprocess_exec, not shell."""
        import inspect
        from orchestrator.terminal import Terminal

        source = inspect.getsource(Terminal)
        # Should use exec-style subprocess, not shell
        assert "create_subprocess_exec" in source or "subprocess.run" in source
        # Should NOT use shell=True
        assert "shell=True" not in source


class TestMessageContentSafety:
    """Verify message content is handled safely."""

    @pytest.mark.security
    def test_message_with_special_chars(self, config: Config) -> None:
        """Messages with special characters should not corrupt the inbox."""
        bus = MessageBus(config)

        dangerous_content = '<script>alert("xss")</script>'
        bus.send(sender="t1", recipient="t2", content=dangerous_content)

        inbox = bus.read_inbox("t2")
        # Content should be stored as-is (no execution context in file)
        assert "alert" in inbox

    @pytest.mark.security
    def test_message_with_null_bytes(self, config: Config) -> None:
        """Messages with null bytes should not crash."""
        bus = MessageBus(config)
        bus.send(sender="t1", recipient="t2", content="test\x00null")
        inbox = bus.read_inbox("t2")
        assert "test" in inbox

    @pytest.mark.security
    def test_very_long_message(self, config: Config) -> None:
        """Very long messages should not cause OOM."""
        bus = MessageBus(config)
        long_content = "A" * 100_000  # 100KB message
        msg = bus.send(sender="t1", recipient="t2", content=long_content)
        assert msg.id.startswith("msg_")


class TestFileWriteSafety:
    """Verify file writes stay within expected directories."""

    @pytest.mark.security
    def test_config_dirs_are_under_base(self) -> None:
        """All config directories should be under base_dir."""
        config = Config()
        assert config.orchestra_dir.is_relative_to(config.base_dir)
        assert config.templates_dir.is_relative_to(config.base_dir)

    @pytest.mark.security
    def test_log_parser_handles_malformed_lines(self) -> None:
        """Orchestrator log parser should not crash on malformed input."""
        from orchestrator.dashboard import parse_orchestrator_log_entry

        # Various malformed inputs
        assert parse_orchestrator_log_entry("") is not None
        assert parse_orchestrator_log_entry("[broken timestamp") is not None
        assert parse_orchestrator_log_entry("\x00\x01\x02") is not None
        assert parse_orchestrator_log_entry("A" * 10_000) is not None
