"""
Terminal Controller using subprocess to run a configured model CLI.

Instead of maintaining interactive sessions, each task is executed
as a single non-interactive CLI call for reliability.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

from .config import Config


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
    """Exception raised when Claude rate limit is hit."""

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
    ):
        self.terminal_id = terminal_id
        self.working_dir = working_dir
        self.system_prompt = system_prompt
        self.runtime_config = runtime_config or Config()
        self.verbose = verbose

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

    async def _execute_single_attempt(
        self,
        full_prompt: str,
        timeout: float,
        attempt: int,
    ) -> TerminalOutput:
        """
        Execute a single attempt of a task.

        Args:
            full_prompt: The complete prompt including system context
            timeout: Maximum time to wait for response
            attempt: Current attempt number (1-based)

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
            full_prompt,
            allow_unsafe=True,
        )

        # Use asyncio subprocess for non-blocking execution
        self._process = await asyncio.create_subprocess_exec(
<<<<<<< ours
            *command,
=======
            "claude",
            "--print",
            "--dangerously-skip-permissions",
            "-p",
            full_prompt,
>>>>>>> theirs
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
    ) -> TerminalOutput:
        """
        Execute a task using the configured model CLI (single attempt).

        Retry logic is handled by the orchestrator, not here.

        Args:
            prompt: The task prompt to send to Claude
            task_id: Optional task ID for tracking
            timeout: Maximum time to wait for response

        Returns:
            TerminalOutput with the result
        """
        self.current_task_id = task_id
        self.state = TerminalState.BUSY

        # Build full prompt with system context if provided
        full_prompt = prompt
        if self.system_prompt:
            full_prompt = f"{self.system_prompt}\n\n---\n\n{prompt}"

        self._log(f"Executing task: {prompt[:60]}...")

        try:
            result = await self._execute_single_attempt(
                full_prompt=full_prompt,
                timeout=timeout,
                attempt=1,
            )

<<<<<<< ours
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
=======
        for attempt in range(1, self.max_retries + 1):
            try:
                result = await self._execute_single_attempt(
                    full_prompt=full_prompt,
                    timeout=timeout,
                    attempt=attempt,
                )

                self.state = TerminalState.IDLE
                self._log(f"Task complete: {len(result.content)} chars output")
                return result

            except TimeoutError:
                self._log(f"Attempt {attempt}/{self.max_retries} timed out")
                last_error = TimeoutError(f"Task timed out after {timeout}s")

                # Clean up the timed-out process
                if self._process:
                    try:
                        self._process.terminate()
                        # Give it a moment to terminate gracefully
                        await asyncio.sleep(0.5)
                        if self._process.returncode is None:
                            self._process.kill()
                    except ProcessLookupError:
                        pass  # Process already terminated
                    finally:
                        self._process = None

                # Don't retry on timeout - it's likely a persistent issue
                if attempt >= self.max_retries:
                    break

                # Wait before retry
                retry_delay = 2**attempt  # Exponential backoff: 2s, 4s, 8s...
                self._log(f"Retrying in {retry_delay}s...")
                await asyncio.sleep(retry_delay)

            except RateLimitError as e:
                # Rate limit - don't retry, return immediately with clear message
                self._log(f"Rate limit hit! Resets: {e.reset_time or 'check Claude dashboard'}")
                self.state = TerminalState.ERROR

                return TerminalOutput(
                    content=f"RATE_LIMIT: {e.reset_time or 'Check Claude dashboard for reset time'}",
                    is_complete=True,
                    is_error=True,
                    attempt=attempt,
                )

            except TerminalError as e:
                self._log(f"Attempt {attempt}/{self.max_retries} failed: {e}")
                last_error = e

                if attempt >= self.max_retries:
                    break

                # Wait before retry with exponential backoff
                retry_delay = 2**attempt
                self._log(f"Retrying in {retry_delay}s...")
                await asyncio.sleep(retry_delay)

            except Exception as e:
                self._log(f"Attempt {attempt}/{self.max_retries} unexpected error: {e}")
                last_error = e

                # Clean up process if it exists
                if self._process:
                    try:
                        self._process.terminate()
                    except ProcessLookupError:
                        pass
                    finally:
                        self._process = None

                if attempt >= self.max_retries:
                    break

                retry_delay = 2**attempt
                self._log(f"Retrying in {retry_delay}s...")
                await asyncio.sleep(retry_delay)

        # All retries exhausted
        self.state = TerminalState.ERROR
        error_message = str(last_error) if last_error else "Unknown error after all retries"
        self._log(f"Task failed after {self.max_retries} attempts: {error_message}")
>>>>>>> theirs

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
