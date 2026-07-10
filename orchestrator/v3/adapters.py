"""PTY adapter layer (Q30): a generic hook + the Claude Code adapter (Addendum A1).

The generic :class:`PTYAdapter` stays in the architecture, but V3.0 ships only
:class:`ClaudeCodeAdapter`. Each adapter turns a spawn request (prompt + cwd)
into an ``argv`` list and a child environment. Provider credentials are stripped
from the child env (REQ-BE-062): agent terminals never receive the Claude key.
:class:`EchoAdapter` is a real generic adapter used by tests/harnesses to drive
the PTY machinery without the ``claude`` binary.
"""

from __future__ import annotations

import os
import shutil
import sys
from typing import Protocol, runtime_checkable

#: Provider-credential env vars stripped from every spawned agent child.
_STRIPPED_ENV = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_API_KEY", "CLAUDECODE")


@runtime_checkable
class PTYAdapter(Protocol):
    """A per-CLI adapter mapping a spawn request to an argv + child env."""

    name: str

    def build_argv(self, prompt: str | None) -> list[str]:
        """Return the argv to exec in the PTY for ``prompt``."""
        ...

    def build_env(self, base_env: dict[str, str] | None = None) -> dict[str, str]:
        """Return the child environment (provider creds stripped)."""
        ...


def _clean_env(base_env: dict[str, str] | None) -> dict[str, str]:
    env = dict(base_env if base_env is not None else os.environ)
    for key in _STRIPPED_ENV:
        env.pop(key, None)
    env["TERM"] = env.get("TERM", "xterm-256color")
    return env


class ClaudeCodeAdapter:
    """Spawn Claude Code in a PTY (``claude --print -p <prompt>``).

    Mirrors the existing orchestrator convention (``config.build_llm_command``):
    non-interactive ``--print`` streaming, permission bypass for autonomous
    agent work. ``--bare`` is never emitted (it breaks OAuth). Interactive stdin
    is deferred (Q11), so no prompt on the PTY means a bare ``claude`` shell.
    """

    name = "claude_code"

    def __init__(self, command: str = "claude", *, skip_permissions: bool = True, model: str | None = None) -> None:
        self.command = command
        self.skip_permissions = skip_permissions
        self.model = model

    def build_argv(self, prompt: str | None) -> list[str]:
        argv = [self.command, "--print"]
        if self.model:
            argv += ["--model", self.model]
        if self.skip_permissions:
            argv.append("--dangerously-skip-permissions")
        if prompt:
            argv += ["-p", prompt]
        return argv

    def build_env(self, base_env: dict[str, str] | None = None) -> dict[str, str]:
        return _clean_env(base_env)

    def available(self) -> bool:
        return shutil.which(self.command) is not None


class EchoAdapter:
    """Generic adapter that streams the prompt back then exits (test harness).

    Uses the current Python interpreter, so it runs anywhere without external
    binaries — exercising the full PTY spawn/stream/exit path deterministically.
    """

    name = "echo"

    def __init__(self, *, lines: int = 3, exit_code: int = 0) -> None:
        self.lines = lines
        self.exit_code = exit_code

    def build_argv(self, prompt: str | None) -> list[str]:
        text = prompt or "hello"
        script = (
            "import sys\n"
            f"for i in range({self.lines}):\n"
            f"    print('line', i, {text!r})\n"
            "    sys.stdout.flush()\n"
            f"sys.exit({self.exit_code})\n"
        )
        return [sys.executable, "-c", script]

    def build_env(self, base_env: dict[str, str] | None = None) -> dict[str, str]:
        return _clean_env(base_env)


def default_adapter() -> PTYAdapter:
    """Return the default adapter (Claude Code)."""
    return ClaudeCodeAdapter()


__all__ = ["PTYAdapter", "ClaudeCodeAdapter", "EchoAdapter", "default_adapter"]
