"""Claude Code PTY session lifecycle + spawn-policy engine (contract §2.3).

Single spawn authority (REQ-BE-001): every PTY is created here. Enforces the
user/session cap (REQ-BE-003) and the hard ceiling (REQ-BE-004), best-effort
resource-aware admission (REQ-BE-005/006), per-session idle *flagging* only
(Q32 — never auto-kill), graceful SIGTERM→SIGKILL termination with reaping
(REQ-BE-033), and streams PTY bytes as base64 ``pty_output`` chunks coalesced to
a ~16 ms window (REQ-ARCH-010, REQ-BE-044) with a per-session ``stream_seq``.

Lifecycle states (REQ-ARCH-020): ``requested → spawning → running → (completed |
failed | killed)``. Terminal state is authoritative from the child ``wait()``;
no ``completed`` is inferred from output.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import logging
import os
import pty
import signal
import time
from dataclasses import dataclass, field
from typing import Any

from . import HARD_CEILING_DEFAULT
from .adapters import PTYAdapter, default_adapter
from .errors import ApiError
from .events import EventBus
from .ids import new_ulid
from .storage import StatePaths
from .util import now_iso

_log = logging.getLogger(__name__)

#: Coalescing window (one 60 Hz frame) and max bytes per pty_output chunk.
COALESCE_S = 0.016
MAX_CHUNK_BYTES = 32 * 1024

#: Cap on retained *terminal* (completed/failed/killed) sessions so a long-running
#: instance doesn't accumulate session metadata forever. Live sessions are never
#: evicted; only the oldest-ended terminal ones beyond this cap are dropped.
MAX_TERMINAL_SESSIONS = 256

#: Per-session limits (REQ-BE-034).
DEFAULT_MAX_RSS_BYTES = 1_500 * 1024 * 1024  # 1.5 GB
DEFAULT_IDLE_TIMEOUT_S = 30 * 60  # flag only, never kill
DEFAULT_GRACE_MS = 5000

_LIVE_STATES = {"requested", "spawning", "running"}
_STATUS_BY_STATE = {
    "requested": "idle",
    "spawning": "idle",
    "running": "running",
    "completed": "done",
    "failed": "error",
    "killed": "done",
}


@dataclass
class _Session:
    session_id: str
    state: str
    provider: str
    cwd: str
    initiator: str
    request_id: str | None
    prompt: str | None
    card_id: str | None = None
    pid: int | None = None
    created_at: str = field(default_factory=now_iso)
    started_at: str | None = None
    ended_at: str | None = None
    exit_code: int | None = None
    exit_reason: str | None = None
    idle_flagged: bool = False
    last_activity_at: str = field(default_factory=now_iso)
    last_output_seq: int = 0
    stream_seq: int = 0
    _created_monotonic: float = field(default_factory=time.monotonic)
    _last_activity_monotonic: float = field(default_factory=time.monotonic)
    _ended_monotonic: float | None = None
    # runtime handles (never serialized)
    proc: Any = None
    master_fd: int | None = None
    buffer: bytearray = field(default_factory=bytearray)
    kill_requested: bool = False
    finalized: bool = False
    flusher: Any = None
    waiter: Any = None

    def elapsed_s(self) -> float:
        end = self._ended_monotonic if self._ended_monotonic is not None else time.monotonic()
        return round(end - self._created_monotonic, 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "state": self.state,
            "status": _STATUS_BY_STATE.get(self.state, "idle"),
            "provider": self.provider,
            "cwd": self.cwd,
            "card_id": self.card_id,
            "initiator": self.initiator,
            "request_id": self.request_id,
            "pid": self.pid,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "exit_code": self.exit_code,
            "exit_reason": self.exit_reason,
            "idle_flagged": self.idle_flagged,
            "last_activity_at": self.last_activity_at,
            "last_output_seq": self.last_output_seq,
            "elapsed_s": self.elapsed_s(),
        }


class SessionManager:
    """The single PTY spawn authority + live session registry."""

    def __init__(
        self,
        *,
        paths: StatePaths,
        bus: EventBus,
        ceiling: int = HARD_CEILING_DEFAULT,
        adapter: PTYAdapter | None = None,
        idle_timeout_s: float = DEFAULT_IDLE_TIMEOUT_S,
        max_rss_bytes: int = DEFAULT_MAX_RSS_BYTES,
    ) -> None:
        self.paths = paths
        self.bus = bus
        self.ceiling = ceiling
        self.adapter = adapter or default_adapter()
        self.idle_timeout_s = idle_timeout_s
        self.max_rss_bytes = max_rss_bytes
        self.project = os.path.realpath(os.path.abspath(str(paths.project_path)))

        self._sessions: dict[str, _Session] = {}
        self._by_request: dict[str, str] = {}
        self._cap_regime = "auto"
        self._cap_value: int | None = None
        self._deferred: list[dict[str, Any]] = []
        self._lock = asyncio.Lock()
        self._idle_monitor: asyncio.Task | None = None
        #: Strong refs to eager-flush tasks so they are not GC'd mid-flight and
        #: their exceptions are observed (documented asyncio fire-and-forget pitfall).
        self._eager_flush_tasks: set[asyncio.Task] = set()

    # -- lifecycle ---------------------------------------------------------
    async def start(self) -> None:
        if self._idle_monitor is None:
            self._idle_monitor = asyncio.create_task(self._idle_loop())

    async def shutdown(self) -> None:
        if self._idle_monitor is not None:
            self._idle_monitor.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._idle_monitor
            self._idle_monitor = None
        for sid in list(self._sessions):
            with contextlib.suppress(Exception):
                await self.kill(sid, grace_ms=500)
        for task in list(self._eager_flush_tasks):
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        self._eager_flush_tasks.clear()

    # -- inspection --------------------------------------------------------
    def live_count(self) -> int:
        return sum(1 for s in self._sessions.values() if s.state in _LIVE_STATES)

    def _effective_limit(self) -> int:
        if self._cap_regime == "user" and self._cap_value is not None:
            return min(self._cap_value, self.ceiling)
        return self.ceiling

    def set_cap(self, regime: str, value: int | None) -> None:
        self._cap_regime = "user" if regime == "user" else "auto"
        self._cap_value = value if self._cap_regime == "user" else None

    def list_sessions(self) -> dict[str, Any]:
        return {
            "sessions": [s.to_dict() for s in self._sessions.values()],
            "count": self.live_count(),
            "ceiling": self.ceiling,
            "cap": {"regime": self._cap_regime, "value": self._cap_value},
        }

    def get(self, session_id: str) -> dict[str, Any] | None:
        s = self._sessions.get(session_id)
        return s.to_dict() if s else None

    def detail(self, session_id: str) -> dict[str, Any]:
        s = self._sessions.get(session_id)
        if s is None:
            raise ApiError("session_not_found", "Unknown session", details={"session_id": session_id})
        first = max(0, s.last_output_seq - 1) if s.last_output_seq else 0
        return {"session": s.to_dict(), "recent_output_seq_range": {"first": first, "last": s.last_output_seq}}

    # -- spawn -------------------------------------------------------------
    def _resolve_cwd(self, cwd: str | None) -> str:
        target = os.path.realpath(os.path.abspath(cwd)) if cwd else self.project
        if not (target == self.project or target.startswith(self.project + os.sep)):
            raise ApiError("path_escape", "cwd resolves outside the project directory", details={"cwd": cwd})
        return target

    def _admit(self) -> tuple[bool, str | None]:
        """Best-effort resource admission (REQ-BE-005). Allows when psutil absent."""
        try:
            import psutil  # type: ignore
        except Exception:  # noqa: BLE001
            return True, None
        try:
            vm = psutil.virtual_memory()
            if vm.available / vm.total < 0.15:
                return False, "insufficient_ram"
        except Exception:  # noqa: BLE001
            return True, None
        return True, None

    async def spawn(
        self,
        *,
        request_id: str | None = None,
        cwd: str | None = None,
        card_id: str | None = None,
        initiator: str = "user",
        prompt: str | None = None,
        cap: int | None = None,
    ) -> tuple[int, dict[str, Any]]:
        """Spawn a PTY session. Returns ``(http_status, body)``.

        Raises ``ApiError`` for ``cap_exceeded`` / ``ceiling_reached`` /
        ``path_escape``. Returns ``201`` with the session on success, or ``202``
        with a deferral when admission control queues it (REQ-BE-005).
        """
        async with self._lock:
            # Idempotency (REQ-ARCH-021): same request_id → original result.
            if request_id and request_id in self._by_request:
                existing = self._sessions.get(self._by_request[request_id])
                if existing is not None:
                    return 201, {"session": existing.to_dict()}

            resolved_cwd = self._resolve_cwd(cwd)

            # The hard ceiling is absolute and always checked first.
            live = self.live_count()
            if live >= self.ceiling:
                raise ApiError("ceiling_reached", f"Hard ceiling {self.ceiling} reached")
            # A per-call cap (REQ-BE-007) clamps THIS instruction only; it never
            # mutates the persistent default regime. Combine with any standing
            # user regime, always bounded by the ceiling.
            limit = self._effective_limit()
            if cap is not None:
                limit = min(limit, int(cap), self.ceiling)
            if live >= limit:
                raise ApiError("cap_exceeded", f"Session cap {limit} reached")

            admitted, reason = self._admit()
            if not admitted:
                queued_rid = request_id or new_ulid()
                self._deferred.append(
                    {
                        "request_id": queued_rid,
                        "cwd": resolved_cwd,
                        "card_id": card_id,
                        "initiator": initiator,
                        "prompt": prompt,
                    }
                )
                await self.bus.publish(
                    "policy_spawn_deferred",
                    {"deferred": True, "reason": reason, "queued_request_id": queued_rid},
                )
                return 202, {"deferred": True, "reason": reason, "queued_request_id": queued_rid}

            session = await self._launch(
                request_id=request_id,
                cwd=resolved_cwd,
                card_id=card_id,
                initiator=initiator,
                prompt=prompt,
            )
        return 201, {"session": session}

    async def _launch(
        self,
        *,
        request_id: str | None,
        cwd: str,
        card_id: str | None,
        initiator: str,
        prompt: str | None,
    ) -> dict[str, Any]:
        session_id = new_ulid()
        sess = _Session(
            session_id=session_id,
            state="requested",
            provider="claude_code",
            cwd=cwd,
            initiator=initiator,
            request_id=request_id,
            prompt=prompt,
            card_id=card_id,
        )
        self._sessions[session_id] = sess
        if request_id:
            self._by_request[request_id] = session_id

        argv = self.adapter.build_argv(prompt)
        env = self.adapter.build_env(dict(os.environ))

        master_fd, slave_fd = pty.openpty()
        sess.state = "spawning"
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                cwd=cwd,
                env=env,
                preexec_fn=_apply_rlimits(self.max_rss_bytes),
                close_fds=True,
            )
        except (OSError, ValueError) as exc:
            os.close(master_fd)
            os.close(slave_fd)
            sess.state = "failed"
            sess.exit_reason = "spawn_failed"
            sess.ended_at = now_iso()
            await self._emit_spawned(sess)
            await self._emit_state(sess)
            raise ApiError("orchestrator_error", f"Failed to spawn agent: {exc}") from exc

        os.close(slave_fd)  # parent keeps only the master side
        os.set_blocking(master_fd, False)
        sess.proc = proc
        sess.master_fd = master_fd
        sess.pid = proc.pid
        sess.state = "running"
        sess.started_at = now_iso()

        loop = asyncio.get_running_loop()
        loop.add_reader(master_fd, self._on_readable, session_id)
        sess.flusher = asyncio.create_task(self._flush_loop(session_id))
        sess.waiter = asyncio.create_task(self._wait_child(session_id))

        await self._emit_spawned(sess)
        await self._emit_state(sess)
        return sess.to_dict()

    # -- PTY read / coalesce / flush --------------------------------------
    def _on_readable(self, session_id: str) -> None:
        sess = self._sessions.get(session_id)
        if sess is None or sess.master_fd is None:
            return
        try:
            data = os.read(sess.master_fd, 65536)
        except BlockingIOError:
            return
        except OSError:
            data = b""  # EIO on child exit → EOF
        if not data:
            self._remove_reader(sess)
            return
        sess.buffer.extend(data)
        sess._last_activity_monotonic = time.monotonic()
        # Bound buffer: flush eagerly if it grows past the max chunk. Keep a strong
        # reference (and observe the result) so the task is not garbage-collected
        # mid-flight and its exceptions are never silently swallowed.
        if len(sess.buffer) >= MAX_CHUNK_BYTES:
            task = asyncio.create_task(self._flush(session_id))
            self._eager_flush_tasks.add(task)
            task.add_done_callback(self._on_eager_flush_done)

    def _on_eager_flush_done(self, task: asyncio.Task) -> None:
        self._eager_flush_tasks.discard(task)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            _log.warning("eager pty flush failed: %r", exc)

    async def _flush_loop(self, session_id: str) -> None:
        while True:
            await asyncio.sleep(COALESCE_S)
            sess = self._sessions.get(session_id)
            if sess is None or sess.finalized:
                return
            if sess.buffer:
                await self._flush(session_id)

    async def _flush(self, session_id: str) -> None:
        sess = self._sessions.get(session_id)
        if sess is None or not sess.buffer:
            return
        # Emit at most MAX_CHUNK_BYTES per frame; keep the remainder buffered.
        chunk = bytes(sess.buffer[:MAX_CHUNK_BYTES])
        del sess.buffer[: len(chunk)]
        sess.stream_seq += 1
        sess.last_activity_at = now_iso()
        env = await self.bus.publish(
            "pty_output",
            {
                "stream_seq": sess.stream_seq,
                "encoding": "base64",
                "bytes": base64.b64encode(chunk).decode("ascii"),
                "dropped": False,
                "dropped_bytes": 0,
            },
            session_id=session_id,
        )
        sess.last_output_seq = env["seq"]

    def _remove_reader(self, sess: _Session) -> None:
        if sess.master_fd is not None:
            with contextlib.suppress(Exception):
                asyncio.get_running_loop().remove_reader(sess.master_fd)

    async def _wait_child(self, session_id: str) -> None:
        sess = self._sessions.get(session_id)
        if sess is None or sess.proc is None:
            return
        rc = await sess.proc.wait()
        await self._finalize(session_id, rc)

    async def _finalize(self, session_id: str, returncode: int) -> None:
        sess = self._sessions.get(session_id)
        if sess is None or sess.finalized:
            return
        sess.finalized = True
        # Final flush of any buffered bytes before the terminal event.
        with contextlib.suppress(Exception):
            while sess.buffer:
                await self._flush(session_id)
        self._remove_reader(sess)
        if sess.master_fd is not None:
            with contextlib.suppress(OSError):
                os.close(sess.master_fd)
            sess.master_fd = None
        if sess.flusher is not None:
            sess.flusher.cancel()

        sess.exit_code = returncode
        sess.ended_at = now_iso()
        sess._ended_monotonic = time.monotonic()
        if sess.kill_requested:
            sess.state = "killed"
            sess.exit_reason = "killed"
        elif returncode == 0:
            sess.state = "completed"
            sess.exit_reason = "normal"
        else:
            sess.state = "failed"
            sess.exit_reason = "normal"
        await self._emit_state(sess)
        # Bound retained terminal-session metadata (never touches live sessions).
        self._compact_sessions()
        # A slot freed → try draining deferred spawns (REQ-BE-006).
        await self._drain_deferred()

    def _compact_sessions(self) -> None:
        """Drop the oldest-ended terminal sessions beyond ``MAX_TERMINAL_SESSIONS``.

        Synchronous (no await) so it runs atomically w.r.t. the spawn critical
        section. Live sessions are always retained; ``list_sessions`` continues to
        show the most-recent terminal sessions (contract-visible behavior).
        """
        terminal = [s for s in self._sessions.values() if s.state not in _LIVE_STATES]
        excess = len(terminal) - MAX_TERMINAL_SESSIONS
        if excess <= 0:
            return
        terminal.sort(key=lambda s: s._ended_monotonic if s._ended_monotonic is not None else 0.0)
        for sess in terminal[:excess]:
            self._sessions.pop(sess.session_id, None)
            if sess.request_id and self._by_request.get(sess.request_id) == sess.session_id:
                del self._by_request[sess.request_id]

    async def _drain_deferred(self) -> None:
        # Every admission decision + launch in ``spawn`` runs under ``self._lock``
        # (the single-spawn-authority invariant, REQ-BE-001/003/004). Draining a
        # deferred spawn must take the same lock and re-check ``live_count`` inside
        # it, so a concurrent ``spawn`` can never interleave its cap/ceiling check
        # with a drain's launch and admit one over the limit. ``_finalize`` (the
        # sole caller) never holds the lock, so this cannot deadlock.
        while True:
            async with self._lock:
                if not self._deferred or self.live_count() >= self._effective_limit():
                    return
                admitted, _reason = self._admit()
                if not admitted:
                    return
                params = self._deferred.pop(0)
                with contextlib.suppress(ApiError):
                    await self._launch(
                        request_id=params["request_id"],
                        cwd=params["cwd"],
                        card_id=params["card_id"],
                        initiator=params["initiator"],
                        prompt=params["prompt"],
                    )

    # -- kill / flag -------------------------------------------------------
    async def kill(self, session_id: str, *, grace_ms: int = DEFAULT_GRACE_MS, force: bool = True) -> dict[str, Any]:
        sess = self._sessions.get(session_id)
        if sess is None:
            raise ApiError("session_not_found", "Unknown session", details={"session_id": session_id})
        if sess.state not in _LIVE_STATES:
            # Already terminal — idempotent.
            return {"session_id": session_id, "state": sess.state, "accepted": True}
        sess.kill_requested = True
        proc = sess.proc
        if proc is not None and proc.returncode is None:
            with contextlib.suppress(ProcessLookupError, OSError):
                proc.send_signal(signal.SIGTERM)
            try:
                await asyncio.wait_for(asyncio.shield(_wait_rc(proc)), timeout=max(grace_ms, 0) / 1000)
            except asyncio.TimeoutError:
                if force:
                    with contextlib.suppress(ProcessLookupError, OSError):
                        proc.kill()
        return {"session_id": session_id, "state": "killed", "accepted": True}

    def flag_idle(self, session_id: str, *, flagged: bool = True) -> dict[str, Any]:
        sess = self._sessions.get(session_id)
        if sess is None:
            raise ApiError("session_not_found", "Unknown session", details={"session_id": session_id})
        sess.idle_flagged = bool(flagged)
        return {"session_id": session_id, "idle_flagged": sess.idle_flagged}

    async def _idle_loop(self) -> None:
        """Flag (never kill) sessions idle past the timeout (Q32)."""
        while True:
            await asyncio.sleep(min(self.idle_timeout_s, 60))
            now = time.monotonic()
            for sess in self._sessions.values():
                if (
                    sess.state == "running"
                    and not sess.idle_flagged
                    and now - sess._last_activity_monotonic > self.idle_timeout_s
                ):
                    sess.idle_flagged = True
                    with contextlib.suppress(Exception):
                        await self._emit_state(sess)

    # -- events ------------------------------------------------------------
    async def _emit_spawned(self, sess: _Session) -> None:
        await self.bus.publish("session_spawned", {"session": sess.to_dict()}, session_id=sess.session_id)

    async def _emit_state(self, sess: _Session) -> None:
        d = sess.to_dict()
        await self.bus.publish(
            "session_state",
            {
                "state": d["state"],
                "status": d["status"],
                "exit_code": d["exit_code"],
                "exit_reason": d["exit_reason"],
                "idle_flagged": d["idle_flagged"],
                "last_activity_at": d["last_activity_at"],
                "elapsed_s": d["elapsed_s"],
            },
            session_id=sess.session_id,
        )


def _apply_rlimits(max_rss_bytes: int):
    """Return a ``preexec_fn`` applying per-session rlimits (best-effort, REQ-BE-034)."""

    def _preexec() -> None:  # pragma: no cover - runs in the forked child
        with contextlib.suppress(Exception):
            import resource

            resource.setrlimit(resource.RLIMIT_NOFILE, (4096, 4096))
            # RLIMIT_AS is unreliable on macOS; guard it.
            with contextlib.suppress(Exception):
                resource.setrlimit(resource.RLIMIT_AS, (max_rss_bytes, max_rss_bytes))
        with contextlib.suppress(Exception):
            os.setsid()

    return _preexec


async def _wait_rc(proc: Any) -> int:
    return await proc.wait()


__all__ = ["SessionManager", "COALESCE_S", "MAX_CHUNK_BYTES"]
