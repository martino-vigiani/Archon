"""PTY session manager tests: lifecycle, streaming, caps, kill, idempotency."""

from __future__ import annotations

import asyncio
import sys

import pytest

from orchestrator.v3.adapters import EchoAdapter
from orchestrator.v3.errors import ApiError
from orchestrator.v3.events import EventBus
from orchestrator.v3.session_manager import SessionManager
from orchestrator.v3.storage import resolve_paths
from tests._v3_util import new_project, new_support


class SleepAdapter:
    """Generic adapter that sleeps, keeping a session live for concurrency tests."""

    name = "sleep"

    def build_argv(self, prompt):
        return [sys.executable, "-c", "import time; time.sleep(30)"]

    def build_env(self, base_env=None):
        import os

        return dict(base_env or os.environ)


def _manager(tmp_path, *, adapter=None, ceiling=8):
    proj = new_project(tmp_path)
    paths = resolve_paths(str(proj), support=new_support(tmp_path))
    paths.ensure()
    bus = EventBus()
    mgr = SessionManager(paths=paths, bus=bus, ceiling=ceiling, adapter=adapter or EchoAdapter(lines=2))
    return mgr, bus, proj


async def _await_terminal(mgr, sid, timeout=8.0):
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        d = mgr.get(sid)
        if d and d["state"] in ("completed", "failed", "killed"):
            return d
        await asyncio.sleep(0.05)
    return mgr.get(sid)


async def test_spawn_streams_and_completes(tmp_path):
    mgr, bus, _ = _manager(tmp_path)
    sub = bus.register()
    status, body = await mgr.spawn(request_id="r1", prompt="do", initiator="user")
    assert status == 201
    sid = body["session"]["session_id"]
    d = await _await_terminal(mgr, sid)
    assert d["state"] == "completed" and d["status"] == "done"
    assert d["last_output_seq"] > 0  # pty_output was emitted
    # Stream carried session_spawned, pty_output, and a terminal session_state.
    types = set()
    while not sub.empty():
        types.add(sub.get_nowait()["type"])
    assert {"session_spawned", "pty_output", "session_state"} <= types
    await mgr.shutdown()


async def test_spawn_idempotency(tmp_path):
    mgr, _, _ = _manager(tmp_path)
    _, b1 = await mgr.spawn(request_id="same", prompt="x")
    _, b2 = await mgr.spawn(request_id="same", prompt="x")
    assert b1["session"]["session_id"] == b2["session"]["session_id"]
    await mgr.shutdown()


async def test_ceiling_reached(tmp_path):
    mgr, _, _ = _manager(tmp_path, adapter=SleepAdapter(), ceiling=2)
    try:
        await mgr.spawn(prompt="a")
        await mgr.spawn(prompt="b")
        assert mgr.live_count() == 2
        with pytest.raises(ApiError) as ei:
            await mgr.spawn(prompt="c")
        assert ei.value.code == "ceiling_reached"
    finally:
        await mgr.shutdown()


async def test_per_call_cap_does_not_mutate_default(tmp_path):
    mgr, _, _ = _manager(tmp_path, adapter=SleepAdapter(), ceiling=8)
    try:
        await mgr.spawn(prompt="a", cap=1)  # live -> 1
        # A second capped-at-1 spawn is rejected while one is alive...
        with pytest.raises(ApiError) as ei:
            await mgr.spawn(prompt="b", cap=1)
        assert ei.value.code == "cap_exceeded"
        # ...but an uncapped spawn still succeeds (default regime unchanged).
        status, _ = await mgr.spawn(prompt="c")
        assert status == 201
        assert mgr.list_sessions()["cap"]["regime"] == "auto"
    finally:
        await mgr.shutdown()


async def test_cwd_path_escape(tmp_path):
    mgr, _, proj = _manager(tmp_path)
    with pytest.raises(ApiError) as ei:
        await mgr.spawn(prompt="x", cwd=str(proj.parent))
    assert ei.value.code == "path_escape"
    await mgr.shutdown()


async def test_kill_is_idempotent(tmp_path):
    mgr, _, _ = _manager(tmp_path, adapter=SleepAdapter())
    _, body = await mgr.spawn(prompt="long")
    sid = body["session"]["session_id"]
    r1 = await mgr.kill(sid, grace_ms=200)
    assert r1["accepted"] is True
    d = await _await_terminal(mgr, sid)
    assert d["state"] == "killed"
    # Killing again is a no-op accept.
    r2 = await mgr.kill(sid, grace_ms=200)
    assert r2["accepted"] is True and r2["state"] == "killed"
    await mgr.shutdown()


async def test_flag_idle_and_not_found(tmp_path):
    mgr, _, _ = _manager(tmp_path, adapter=SleepAdapter())
    _, body = await mgr.spawn(prompt="x")
    sid = body["session"]["session_id"]
    assert mgr.flag_idle(sid, flagged=True)["idle_flagged"] is True
    assert mgr.flag_idle(sid, flagged=False)["idle_flagged"] is False
    with pytest.raises(ApiError) as ei:
        mgr.detail("nope")
    assert ei.value.code == "session_not_found"
    with pytest.raises(ApiError):
        mgr.flag_idle("nope")
    await mgr.shutdown()


async def test_list_snapshot_shape(tmp_path):
    mgr, _, _ = _manager(tmp_path, adapter=SleepAdapter())
    await mgr.spawn(prompt="x")
    snap = mgr.list_sessions()
    assert snap["ceiling"] == 8 and "cap" in snap and snap["count"] >= 1
    assert snap["sessions"][0]["provider"] == "claude_code"
    await mgr.shutdown()
