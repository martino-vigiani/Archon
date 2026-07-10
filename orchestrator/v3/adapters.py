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


class SleepAdapter:
    """Generic adapter that prints, holds the PTY open, then exits (test harness).

    Like :class:`EchoAdapter` it needs no external binary, but it stays alive for
    ``hold_s`` seconds after its first line so a harness can (a) let it run to a
    natural ``completed`` exit, or (b) ``kill`` a genuinely-live PTY session and
    observe ``exit_reason: killed`` — both deterministically and offline. It
    writes nothing to disk (project tree stays byte-identical).
    """

    name = "sleep"

    def __init__(self, *, hold_s: float = 2.0) -> None:
        self.hold_s = hold_s

    def build_argv(self, prompt: str | None) -> list[str]:
        text = prompt or "archon-e2e"
        script = (
            "import sys, time\n"
            f"print('archon-e2e ready', {text!r}, flush=True)\n"
            f"time.sleep({float(self.hold_s)!r})\n"
            "print('archon-e2e done', flush=True)\n"
            "sys.exit(0)\n"
        )
        return [sys.executable, "-c", script]

    def build_env(self, base_env: dict[str, str] | None = None) -> dict[str, str]:
        return _clean_env(base_env)


def default_adapter() -> PTYAdapter:
    """Return the default PTY adapter.

    Production always uses :class:`ClaudeCodeAdapter`. The optional
    ``ARCHON_V3_ADAPTER`` env var selects a credential-free stub adapter for E2E
    harnesses driving the real ``python -m orchestrator.v3`` boot without the
    ``claude`` binary/OAuth (values: ``echo`` → :class:`EchoAdapter`, ``sleep`` →
    :class:`SleepAdapter`). Unset/unknown → Claude Code (no behavior change).
    """
    choice = os.environ.get("ARCHON_V3_ADAPTER", "").strip().lower()
    if choice == "echo":
        return EchoAdapter()
    if choice == "sleep":
        hold_raw = os.environ.get("ARCHON_V3_STUB_HOLD_S", "2.0")
        try:
            hold_s = float(hold_raw)
        except (TypeError, ValueError):
            hold_s = 2.0
        return SleepAdapter(hold_s=hold_s)
    return ClaudeCodeAdapter()


__all__ = ["PTYAdapter", "ClaudeCodeAdapter", "EchoAdapter", "SleepAdapter", "default_adapter"]
