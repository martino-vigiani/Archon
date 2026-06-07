"""
Terminal Controller using subprocess to run a configured model CLI.

Instead of maintaining interactive sessions, each task is executed
as a single non-interactive CLI call for reliability.
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from .config import Config
from .execution import ExecutionProfile


class TerminalState(str, Enum):
    IDLE = "idle"
    BUSY = "busy"
    ERROR = "error"
    STOPPED = "stopped"


@dataclass
class TerminalOutput:
    """Captured output from a terminal."""

    content: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    is_complete: bool = False
    is_error: bool = False
    attempt: int = 1  # Which attempt this output is from


class TerminalError(Exception):
    """Custom exception for terminal errors."""

    def __init__(self, message: str, returncode: int | None = None):
        super().__init__(message)
        self.returncode = returncode


class RateLimitError(Exception):
    """Exception raised when provider rate limit is hit."""

    def __init__(self, message: str, reset_time: str | None = None):
        super().__init__(message)
        self.reset_time = reset_time  # e.g., "7pm (Europe/Berlin)"

    @classmethod
    def from_output(cls, output: str) -> "RateLimitError | None":
        """
        Check if output contains rate limit error and return RateLimitError if so.

        Looks for patterns like:
        - "You've hit your limit"
        - "resets 7pm (Europe/Berlin)"
        - "rate limit exceeded"
        """
        output_lower = output.lower()

        # Check for rate limit indicators
        rate_limit_indicators = [
            "hit your limit",
            "rate limit",
            "usage limit",
            "quota exceeded",
            "too many requests",
        ]

        if any(indicator in output_lower for indicator in rate_limit_indicators):
            # Try to extract reset time
            reset_time = None
            import re

            # Match patterns like "resets 7pm (Europe/Berlin)" or "resets at 19:00"
            reset_match = re.search(
                r"resets?\s+(?:at\s+)?(\d{1,2}(?::\d{2})?\s*(?:am|pm)?\s*(?:\([^)]+\))?)",
                output_lower,
            )
            if reset_match:
                reset_time = reset_match.group(1).strip()

            return cls(output, reset_time=reset_time)

        return None


class Terminal:
    """
    Controls a model-backed "terminal" using subprocess.

    Each task is run as a separate non-interactive CLI command.
    This is more reliable than maintaining interactive sessions.

    Retry logic is handled at the orchestrator level, not here.
    Each execute_task() call is a single attempt.
    """

    def __init__(
        self,
        terminal_id: str,
        working_dir: Path,
        system_prompt: str | None = None,
        runtime_config: Config | None = None,
        verbose: bool = True,
        default_profile: ExecutionProfile | None = None,
        session_log: Any | None = None,
    ):
        self.terminal_id = terminal_id
        self.working_dir = working_dir
        self.system_prompt = system_prompt
        self.runtime_config = runtime_config or Config()
        self.verbose = verbose
        # Default execution profile for this worker; per-task profiles override it.
        self.default_profile = default_profile
        # Optional firehose (``session_log.SessionLog``). When provided, captured
        # prompts are mirrored into the total session log (F16). Best-effort:
        # never required, never allowed to break a run.
        self.session_log = session_log

        self.state = TerminalState.IDLE
        self.current_task_id: str | None = None
        self.last_output: str = ""
        self._process: asyncio.subprocess.Process | None = None

    def _log(self, message: str):
        """Log a message if verbose mode is enabled."""
        if self.verbose:
            print(f"[{self.terminal_id}] {message}")

    async def start(self) -> bool:
        """Initialize the terminal (no-op for subprocess approach)."""
        self.state = TerminalState.IDLE
        self._log("Ready")
        return True

    @staticmethod
    def _extract_flag_value(command: list[str], flag: str) -> str | None:
        """Return the value following ``flag`` in a built CLI command, or None.

        The command is the flat argv list produced by
        :meth:`Config.build_llm_command`, so the value (when present) is the next
        element after the flag token.

        Args:
            command: The argv list to scan.
            flag: The flag whose value to extract (e.g. ``"--model"``).

        Returns:
            The string value following ``flag``, or None when the flag is absent or
            has no following token.
        """
        try:
            idx = command.index(flag)
        except ValueError:
            return None
        if idx + 1 < len(command):
            return command[idx + 1]
        return None

    def _capture_prompt(self, command: list[str]) -> None:
        """Persist a JSONL record of the prompt/modes sent to the CLI (F8).

        Writes one append-only line to
        ``<orchestra_dir>/terminal_prompts/<worker_id>.jsonl`` and, when a
        firehose ``session_log`` is attached, mirrors the same record there.

        The recorded ``model``/``effort``/``permission_mode``/``system``/``body``
        are read back from the *built* command so they reflect exactly what the
        subprocess receives (after profile/effort-dial resolution), rather than
        re-deriving them. ``permission_mode`` reports ``"bypass"`` when the
        permission-skip flag is present.

        Best-effort by contract: any failure (missing dir, serialization, I/O) is
        swallowed so prompt capture never breaks task execution.

        Args:
            command: The argv list returned by ``build_llm_command``.
        """
        try:
            model = self._extract_flag_value(command, "--model")
            effort = self._extract_flag_value(command, "--effort")
            system = self._extract_flag_value(command, "--append-system-prompt")
            body = self._extract_flag_value(command, "-p")

            permission_mode = self._extract_flag_value(command, "--permission-mode")
            if permission_mode is None and "--dangerously-skip-permissions" in command:
                permission_mode = "bypass"

            record = {
                "ts": datetime.now().isoformat(),
                "worker": self.terminal_id,
                "task_id": self.current_task_id,
                "model": model,
                "effort": effort,
                "permission_mode": permission_mode,
                "system": system,
                "body": body,
            }

            self._write_prompt_record(record)
            self._mirror_prompt_to_firehose(record)
        except Exception as e:  # noqa: BLE001 - capture must never break the run
            self._log(f"Prompt capture skipped: {e}")

    def _write_prompt_record(self, record: dict[str, Any]) -> None:
        """Append a prompt record to the per-worker JSONL file (best-effort)."""
        try:
            orchestra_dir = getattr(self.runtime_config, "orchestra_dir", None)
            if orchestra_dir is None:
                return
            prompts_dir = Path(orchestra_dir) / "terminal_prompts"
            prompts_dir.mkdir(parents=True, exist_ok=True)
            path = prompts_dir / f"{self.terminal_id}.jsonl"
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, default=str) + "\n")
        except Exception as e:  # noqa: BLE001 - best-effort file I/O
            self._log(f"Prompt record write failed: {e}")

    def _mirror_prompt_to_firehose(self, record: dict[str, Any]) -> None:
        """Mirror a prompt record into the session firehose, if one is attached."""
        log = self.session_log
        if log is None:
            return
        try:
            log.prompt(
                worker_id=record["worker"],
                task_id=record["task_id"],
                model=record["model"],
                effort=record["effort"],
                system=record["system"],
                body=record["body"],
            )
        except Exception as e:  # noqa: BLE001 - firehose mirror is best-effort
            self._log(f"Prompt firehose mirror failed: {e}")

    async def _execute_single_attempt(
        self,
        prompt: str,
        timeout: float,
        attempt: int,
        profile: ExecutionProfile | None = None,
    ) -> TerminalOutput:
        """
        Execute a single attempt of a task.

        Args:
            prompt: The task prompt (the persona/system prompt is passed separately to
                ``build_llm_command`` as ``--append-system-prompt`` so it can be
                prompt-cached across tasks instead of being re-sent inline).
            timeout: Maximum time to wait for response
            attempt: Current attempt number (1-based)
            profile: optional per-task :class:`ExecutionProfile` selecting model tier,
                effort, plan mode, dynamic agents, etc.

        Returns:
            TerminalOutput with the result

        Raises:
            TerminalError: If the command fails with a non-zero exit code
            asyncio.TimeoutError: If the command times out
        """
        self._log(f"Executing attempt {attempt}")

        # Clean env: remove CLAUDECODE to allow nested Claude Code sessions
        import os
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

        command = self.runtime_config.build_llm_command(
            prompt,
            allow_unsafe=True,
            profile=profile,
            system_prompt=self.system_prompt,
        )

        # F8: capture the exact prompt + resolved modes that were sent to the CLI.
        # Best-effort: a capture/write failure must never break the run.
        self._capture_prompt(command)

        # Use asyncio subprocess for non-blocking execution
        self._process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self.working_dir),
            env=env,
        )

        # Wait for completion with timeout
        stdout, stderr = await asyncio.wait_for(
            self._process.communicate(),
            timeout=timeout,
        )

        # IMPORTANT: Save returncode BEFORE setting _process to None
        returncode = self._process.returncode
        output = stdout.decode("utf-8") if stdout else ""
        error = stderr.decode("utf-8") if stderr else ""

        # Clean up process reference
        self._process = None

        # Combine output and error if needed
        if error and not output:
            output = error
        elif error and output:
            output = f"{output}\n\n--- STDERR ---\n{error}"

        self.last_output = output

        # Check for rate limit FIRST (even on success, the message might be in output)
        combined_output = f"{output} {error}"
        rate_limit_error = RateLimitError.from_output(combined_output)
        if rate_limit_error:
            self._log(f"Rate limit detected! Resets: {rate_limit_error.reset_time or 'unknown'}")
            raise rate_limit_error

        # Check for error based on saved returncode
        is_error = returncode != 0

        if is_error:
            # Check again for rate limit in error output
            rate_limit_error = RateLimitError.from_output(error or output)
            if rate_limit_error:
                raise rate_limit_error

            raise TerminalError(
                f"Command failed with exit code {returncode}: {error or output[:200]}",
                returncode=returncode,
            )

        return TerminalOutput(
            content=output,
            is_complete=True,
            is_error=False,
            attempt=attempt,
        )

    async def execute_task(
        self,
        prompt: str,
        task_id: str | None = None,
        timeout: float = 300,
        profile: ExecutionProfile | None = None,
    ) -> TerminalOutput:
        """
        Execute a task using the configured model CLI (single attempt).

        Retry logic is handled by the orchestrator, not here.

        Args:
            prompt: The task prompt to send to the configured model runtime
            task_id: Optional task ID for tracking
            timeout: Maximum time to wait for response (a profile timeout overrides it)
            profile: optional per-task :class:`ExecutionProfile`; falls back to this
                terminal's ``default_profile``.

        Returns:
            TerminalOutput with the result
        """
        self.current_task_id = task_id
        self.state = TerminalState.BUSY

        effective_profile = profile or self.default_profile
        if effective_profile is not None and effective_profile.timeout:
            timeout = effective_profile.timeout

        self._log(f"Executing task: {prompt[:60]}...")

        try:
            result = await self._execute_single_attempt(
                prompt=prompt,
                timeout=timeout,
                attempt=1,
                profile=effective_profile,
            )

            self.state = TerminalState.IDLE
            self._log(f"Task complete: {len(result.content)} chars output")
            return result

        except asyncio.TimeoutError:
            self._log("Task timed out")

            # Clean up the timed-out process
            if self._process:
                try:
                    self._process.terminate()
                    await asyncio.sleep(0.5)
                    if self._process.returncode is None:
                        self._process.kill()
                except ProcessLookupError:
                    pass
                finally:
                    self._process = None

            self.state = TerminalState.ERROR
            return TerminalOutput(
                content=f"Task timed out after {timeout}s",
                is_complete=True,
                is_error=True,
            )

        except RateLimitError as e:
            self._log(f"Rate limit hit! Resets: {e.reset_time or 'check provider dashboard'}")
            self.state = TerminalState.ERROR

            return TerminalOutput(
                content=f"RATE_LIMIT: {e.reset_time or 'Check provider dashboard for reset time'}",
                is_complete=True,
                is_error=True,
            )

        except TerminalError as e:
            self._log(f"Task failed: {e}")
            self.state = TerminalState.ERROR

            return TerminalOutput(
                content=str(e),
                is_complete=True,
                is_error=True,
            )

        except Exception as e:
            self._log(f"Unexpected error: {e}")

            # Clean up process if it exists
            if self._process:
                try:
                    self._process.terminate()
                except ProcessLookupError:
                    pass
                finally:
                    self._process = None

            self.state = TerminalState.ERROR
            return TerminalOutput(
                content=str(e),
                is_complete=True,
                is_error=True,
            )

    async def stop(self) -> None:
        """Stop any running task."""
        if self._process:
            try:
                self._process.terminate()
                await asyncio.sleep(0.5)
                if self._process.returncode is None:
                    self._process.kill()
            except ProcessLookupError:
                pass  # Process already terminated
            finally:
                self._process = None
        self.state = TerminalState.STOPPED
        self._log("Stopped")

    def is_alive(self) -> bool:
        """Check if the terminal is operational."""
        return self.state != TerminalState.STOPPED

    def is_idle(self) -> bool:
        """Check if the terminal is ready for new tasks."""
        return self.state == TerminalState.IDLE

    def is_busy(self) -> bool:
        """Check if the terminal is currently executing a task."""
        return self.state == TerminalState.BUSY
