"""The per-instance :class:`V3State` container (single-project binding, Q3).

Holds everything one bound orchestrator instance needs: resolved out-of-project
:class:`~orchestrator.v3.storage.StatePaths`, the bearer token, bound port, git
project info, the :class:`~orchestrator.v3.events.EventBus`, and the four feature
services (sessions / kanban / memory / conductor). ``app.py`` constructs the
services and injects them here, so this module imports only the foundation and
never the feature modules (keeps the import graph acyclic).
"""

from __future__ import annotations

import subprocess
import time
from typing import Any

from . import ORCHESTRATOR_VERSION, PROTOCOL_VERSION, SUPPORTED_PROVIDER
from .events import EventBus
from .storage import StatePaths
from .util import now_iso


def git_info(project_path: str) -> dict[str, Any]:
    """Return ``{is_repo, branch, head, dirty}`` for the project (best-effort)."""
    info: dict[str, Any] = {"is_repo": False, "branch": None, "head": None, "dirty": False}

    def _run(args: list[str]) -> str | None:
        try:
            out = subprocess.run(
                ["git", *args],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if out.returncode != 0:
            return None
        return out.stdout.strip()

    inside = _run(["rev-parse", "--is-inside-work-tree"])
    if inside != "true":
        return info
    info["is_repo"] = True
    info["branch"] = _run(["rev-parse", "--abbrev-ref", "HEAD"])
    head = _run(["rev-parse", "--short", "HEAD"])
    info["head"] = head
    status = _run(["status", "--porcelain"])
    info["dirty"] = bool(status)
    return info


class V3State:
    """Live state for one bound project instance."""

    def __init__(
        self,
        *,
        paths: StatePaths,
        token: str,
        port: int,
        bus: EventBus,
        provider_ready: bool = False,
    ) -> None:
        self.paths = paths
        self.token = token
        self.port = port
        self.bus = bus
        self.provider_ready = provider_ready
        self.opened_at = now_iso()
        self._t0 = time.monotonic()
        self._git = git_info(str(paths.project_path))

        # Feature services — injected by app.py after construction.
        self.sessions: Any = None
        self.kanban: Any = None
        self.memory: Any = None
        self.writeguard: Any = None
        self.conductor: Any = None

    # -- descriptors -------------------------------------------------------
    def uptime_s(self) -> float:
        return time.monotonic() - self._t0

    @property
    def project_id(self) -> str:
        return self.paths.project_id

    @property
    def project_path(self) -> str:
        return str(self.paths.project_path)

    def project_info(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "path": self.project_path,
            "name": self.paths.project_path.name,
            "provider": SUPPORTED_PROVIDER,
            "opened_at": self.opened_at,
            "git": dict(self._git),
            "state_dir": str(self.paths.state_dir),
        }

    def conductor_state(self) -> str:
        """Current orb/conductor state (server-owned five of the six; §3.4)."""
        if self.conductor is not None:
            try:
                return self.conductor.current_state()
            except Exception:  # noqa: BLE001
                pass
        if self.sessions is not None:
            try:
                if self.sessions.live_count() > 0:
                    return "streaming"
            except Exception:  # noqa: BLE001
                pass
        return "idle"

    def session_count(self) -> int:
        if self.sessions is None:
            return 0
        try:
            return self.sessions.live_count()
        except Exception:  # noqa: BLE001
            return 0

    def capabilities(self) -> dict[str, Any]:
        from . import DRY_RUN_MAX_S, HARD_CEILING_DEFAULT, REPLAY_MAX_EVENTS, REPLAY_WINDOW_S

        ceiling = HARD_CEILING_DEFAULT
        if self.sessions is not None:
            ceiling = getattr(self.sessions, "ceiling", HARD_CEILING_DEFAULT)
        return {
            "stream_transport": "websocket",
            "replay_events": REPLAY_MAX_EVENTS,
            "replay_window_s": REPLAY_WINDOW_S,
            "hard_ceiling": ceiling,
            "supported_provider": SUPPORTED_PROVIDER,
            "memory_kinds": ["CLAUDE.md", "AGENTS.md", "overlay"],
            "dry_run_max_s": DRY_RUN_MAX_S,
        }

    def health(self, uptime_s: float) -> dict[str, Any]:
        return {
            "status": "ok",
            "pv": PROTOCOL_VERSION,
            "orchestrator_version": ORCHESTRATOR_VERSION,
            "project_id": self.project_id,
            "uptime_s": round(uptime_s, 1),
            "provider_ready": self.provider_ready,
            "conductor_state": self.conductor_state(),
            "session_count": self.session_count(),
            "capabilities": self.capabilities(),
        }

    async def start(self) -> None:
        """Best-effort startup for feature services (crash recovery, etc.)."""
        for svc in (self.sessions,):
            start = getattr(svc, "start", None)
            if start is not None:
                await start()

    async def stop(self) -> None:
        """Tear down feature services (reap PTYs, close DBs)."""
        for svc in (self.sessions, self.conductor):
            stop = getattr(svc, "shutdown", None)
            if stop is not None:
                try:
                    await stop()
                except Exception:  # noqa: BLE001
                    pass
        if self.kanban is not None:
            close = getattr(self.kanban, "close", None)
            if close is not None:
                try:
                    close()
                except Exception:  # noqa: BLE001
                    pass


__all__ = ["V3State", "git_info"]
