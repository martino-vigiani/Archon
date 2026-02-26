"""
Tests for the Terminal subprocess controller.

The Terminal manages Claude Code subprocess execution:
- State machine: IDLE -> BUSY -> IDLE/ERROR/STOPPED
- Retry logic with exponential backoff
- Rate limit detection and handling
- Timeout management
- System prompt prepending

All subprocess calls are mocked - never spawn real Claude Code.
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.terminal import (
    RateLimitError,
    Terminal,
    TerminalError,
    TerminalOutput,
    TerminalState,
)


class TestTerminalState:
    """Test terminal state machine."""

    def test_initial_state_is_idle(self, tmp_path: Path) -> None:
        """New terminal should start IDLE."""
        terminal = Terminal("t1", tmp_path)
        assert terminal.state == TerminalState.IDLE

    def test_start_sets_idle(self, tmp_path: Path) -> None:
        """start() should set state to IDLE."""
        terminal = Terminal("t1", tmp_path)
        result = asyncio.get_event_loop().run_until_complete(terminal.start())
        assert result is True
        assert terminal.state == TerminalState.IDLE

    def test_is_idle(self, tmp_path: Path) -> None:
        """is_idle should return True when state is IDLE."""
        terminal = Terminal("t1", tmp_path)
        assert terminal.is_idle()

    def test_is_alive(self, tmp_path: Path) -> None:
        """is_alive should return True when not STOPPED."""
        terminal = Terminal("t1", tmp_path)
        assert terminal.is_alive()

    def test_is_not_alive_when_stopped(self, tmp_path: Path) -> None:
        """is_alive should return False when STOPPED."""
        terminal = Terminal("t1", tmp_path)
        terminal.state = TerminalState.STOPPED
        assert not terminal.is_alive()

    def test_is_busy(self, tmp_path: Path) -> None:
        """is_busy should return True when state is BUSY."""
        terminal = Terminal("t1", tmp_path)
        terminal.state = TerminalState.BUSY
        assert terminal.is_busy()


class TestTerminalOutput:
    """Test TerminalOutput data structure."""

    def test_output_defaults(self) -> None:
        """TerminalOutput should have sensible defaults."""
        output = TerminalOutput(content="Hello")
        assert output.content == "Hello"
        assert output.is_complete is False
        assert output.is_error is False
        assert output.attempt == 1
        assert output.timestamp is not None


class TestRateLimitDetection:
    """Test rate limit detection from output text."""

    @pytest.mark.parametrize(
        "output_text",
        [
            "You've hit your limit for today",
            "Rate limit exceeded, try again later",
            "Usage limit reached",
            "Quota exceeded for this period",
            "Too many requests, please wait",
        ],
    )
    def test_detects_rate_limit_indicators(self, output_text: str) -> None:
        """Should detect various rate limit message patterns."""
        error = RateLimitError.from_output(output_text)
        assert error is not None

    def test_no_rate_limit_in_normal_output(self) -> None:
        """Normal output should not trigger rate limit detection."""
        error = RateLimitError.from_output("Task completed successfully. Created 3 files.")
        assert error is None

    def test_extracts_reset_time(self) -> None:
        """Should extract reset time from rate limit message."""
        output = "You've hit your limit. Your limit resets 7pm (Europe/Berlin)"
        error = RateLimitError.from_output(output)
        assert error is not None
        assert error.reset_time is not None
        assert "7pm" in error.reset_time

    def test_rate_limit_without_reset_time(self) -> None:
        """Rate limit without explicit reset time should still be detected."""
        error = RateLimitError.from_output("Rate limit exceeded")
        assert error is not None
        assert error.reset_time is None


class TestTerminalError:
    """Test TerminalError exception."""

    def test_terminal_error_with_returncode(self) -> None:
        """TerminalError should store return code."""
        err = TerminalError("Command failed", returncode=1)
        assert str(err) == "Command failed"
        assert err.returncode == 1

    def test_terminal_error_without_returncode(self) -> None:
        """TerminalError without returncode defaults to None."""
        err = TerminalError("Generic failure")
        assert err.returncode is None


class TestTerminalConfiguration:
    """Test terminal configuration options."""

    def test_system_prompt_stored(self, tmp_path: Path) -> None:
        """System prompt should be stored for use in prompts."""
        terminal = Terminal("t1", tmp_path, system_prompt="You are T1, the Craftsman.")
        assert terminal.system_prompt == "You are T1, the Craftsman."

    def test_verbose_default(self, tmp_path: Path) -> None:
        """Verbose should default to True."""
        terminal = Terminal("t1", tmp_path)
        assert terminal.verbose is True


class TestExecuteTaskMocked:
    """Test task execution with mocked subprocess."""

    def test_successful_execution(self, tmp_path: Path) -> None:
        """Successful execution should return content and set IDLE state."""
        terminal = Terminal("t1", tmp_path, verbose=False)

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"Task completed successfully", b""))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = asyncio.get_event_loop().run_until_complete(
                terminal.execute_task("Build the login UI", task_id="task_001")
            )

        assert result.content == "Task completed successfully"
        assert result.is_complete is True
        assert result.is_error is False
        assert terminal.state == TerminalState.IDLE

    def test_task_id_tracked(self, tmp_path: Path) -> None:
        """Current task ID should be tracked during execution."""
        terminal = Terminal("t1", tmp_path, verbose=False)

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"Done", b""))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            asyncio.get_event_loop().run_until_complete(
                terminal.execute_task("test", task_id="my_task_123")
            )

        assert terminal.current_task_id == "my_task_123"

    def test_system_prompt_prepended(self, tmp_path: Path) -> None:
        """System prompt should be prepended to the task prompt."""
        terminal = Terminal("t1", tmp_path, system_prompt="You are the Craftsman.", verbose=False)

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"Done", b""))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock_exec:
            asyncio.get_event_loop().run_until_complete(terminal.execute_task("Build UI"))

            # The prompt argument should contain both system prompt and task
            call_args = mock_exec.call_args
            prompt_arg = call_args[0][4]  # -p is at index 3, value at 4
            assert "You are the Craftsman." in prompt_arg
            assert "Build UI" in prompt_arg

    def test_failed_execution_returns_error(self, tmp_path: Path) -> None:
        """Failed execution should return error output."""
        terminal = Terminal("t1", tmp_path, verbose=False)

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"", b"Error: command not found"))
        mock_process.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = asyncio.get_event_loop().run_until_complete(terminal.execute_task("bad task"))

        assert result.is_error is True
        assert terminal.state == TerminalState.ERROR

    def test_rate_limit_returns_immediately(self, tmp_path: Path) -> None:
        """Rate limit should return error immediately."""
        terminal = Terminal("t1", tmp_path, verbose=False)

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(
            return_value=(b"You've hit your limit. Rate limit exceeded.", b"")
        )
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = asyncio.get_event_loop().run_until_complete(terminal.execute_task("test"))

        assert result.is_error is True
        assert "RATE_LIMIT" in result.content
        assert terminal.state == TerminalState.ERROR


class TestTerminalStop:
    """Test terminal stop/cleanup."""

    def test_stop_sets_stopped_state(self, tmp_path: Path) -> None:
        """stop() should set state to STOPPED."""
        terminal = Terminal("t1", tmp_path, verbose=False)
        asyncio.get_event_loop().run_until_complete(terminal.stop())
        assert terminal.state == TerminalState.STOPPED

    def test_stop_terminates_running_process(self, tmp_path: Path) -> None:
        """stop() should terminate any running subprocess."""
        terminal = Terminal("t1", tmp_path, verbose=False)

        mock_process = AsyncMock()
        mock_process.returncode = None  # Still running
        mock_process.terminate = MagicMock()
        mock_process.kill = MagicMock()

        terminal._process = mock_process

        asyncio.get_event_loop().run_until_complete(terminal.stop())

        mock_process.terminate.assert_called_once()
        assert terminal._process is None

    def test_stop_handles_already_terminated(self, tmp_path: Path) -> None:
        """stop() should handle ProcessLookupError gracefully."""
        terminal = Terminal("t1", tmp_path, verbose=False)

        mock_process = AsyncMock()
        mock_process.returncode = None
        mock_process.terminate = MagicMock(side_effect=ProcessLookupError)

        terminal._process = mock_process

        # Should not raise
        asyncio.get_event_loop().run_until_complete(terminal.stop())
        assert terminal.state == TerminalState.STOPPED


class TestTerminalLogging:
    """Test terminal logging behavior."""

    def test_verbose_logging(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """Verbose terminal should print log messages."""
        terminal = Terminal("t1", tmp_path, verbose=True)
        terminal._log("Test message")

        captured = capsys.readouterr()
        assert "[t1] Test message" in captured.out

    def test_quiet_logging(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """Non-verbose terminal should suppress log messages."""
        terminal = Terminal("t1", tmp_path, verbose=False)
        terminal._log("Test message")

        captured = capsys.readouterr()
        assert captured.out == ""
