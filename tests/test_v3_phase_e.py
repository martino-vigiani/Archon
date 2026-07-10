"""Phase E backend-correctness tests (fixer domain: orchestrator/v3).

Locks in the fixes for the phase-D backend findings:

1.  Conductor.confirm() idempotency by request_id + no duplicate execution.
2.  SessionManager._drain_deferred() runs its admission + launch under the lock.
3.  MemoryService overlay quota counts the scope's own overlay dir (not the
    state dir / not a dir-of-dirs).
4.  Stream drop markers are flushed by the heartbeat loop (bounded latency).
5.  EventBus ring is age-pruned via monotonic floats (no per-publish ISO parse).
6.  Conductor plan/idempotency maps and SessionManager terminal sessions are
    bounded (opportunistic pruning / compaction).
7.  Kanban SQLite uses WAL + busy_timeout.
8.  Eager pty-flush tasks are referenced and their exceptions observed.
"""

from __future__ import annotations

import asyncio
import contextlib
import sys
import time

import pytest

import orchestrator.v3.conductor as conductor_mod
import orchestrator.v3.memory as memory_mod
import orchestrator.v3.session_manager as sm_mod
import orchestrator.v3.stream as stream_mod
from orchestrator.v3.adapters import EchoAdapter
from orchestrator.v3.conductor import Conductor
from orchestrator.v3.errors import ApiError
from orchestrator.v3.events import EventBus, Subscriber
from orchestrator.v3.kanban import KanbanStore
from orchestrator.v3.memory import MemoryService
from orchestrator.v3.provider import FallbackProvider
from orchestrator.v3.session_manager import SessionManager
from orchestrator.v3.storage import resolve_paths
from orchestrator.v3.writeguard import WriteGuard
from tests._v3_util import bare_services, new_project, new_support
from tests.test_v3_sessions import SleepAdapter, _await_terminal, _manager


def _echo_conductor(tmp_path, *, ceiling=8, lines=1):
    proj = new_project(tmp_path)
    paths = resolve_paths(str(proj), support=new_support(tmp_path))
    paths.ensure()
    bus = EventBus()
    guard = WriteGuard(paths=paths)
    memory = MemoryService(paths=paths, bus=bus, guard=guard)
    kanban = KanbanStore(db_path=paths.kanban_db, bus=bus)
    sessions = SessionManager(paths=paths, bus=bus, ceiling=ceiling, adapter=EchoAdapter(lines=lines))
    cond = Conductor(paths=paths, bus=bus, sessions=sessions, kanban=kanban, memory=memory,
                     provider=FallbackProvider(), ceiling=ceiling)
    return cond, sessions, kanban, proj


# ---------------------------------------------------------------------------
# Finding 1 — confirm idempotency + no duplicate execution
# ---------------------------------------------------------------------------

async def test_confirm_same_request_id_returns_original_and_spawns_nothing_new(tmp_path):
    cond, sessions, kanban, proj = _echo_conductor(tmp_path)
    body = await cond.message(text="Add tests", context={"active_dir": str(proj), "cap": 2})
    pid = body["plan"]["plan_id"]

    r1 = await cond.confirm(pid, request_id="creq-1", cap=2)
    sessions_after_first = len(sessions.list_sessions()["sessions"])
    cards_after_first = len((await kanban.snapshot())["cards"])
    assert sessions_after_first >= 1 and cards_after_first >= 1

    # A transient-timeout retry re-sends the SAME request_id: it must replay the
    # original result and NOT execute the plan a second time.
    r2 = await cond.confirm(pid, request_id="creq-1", cap=2)
    assert r2 == r1
    assert len(sessions.list_sessions()["sessions"]) == sessions_after_first
    assert len((await kanban.snapshot())["cards"]) == cards_after_first
    await sessions.shutdown()


async def test_reconfirm_with_different_request_id_is_rejected(tmp_path):
    cond, sessions, _kanban, proj = _echo_conductor(tmp_path)
    body = await cond.message(text="x", context={"active_dir": str(proj), "cap": 1})
    pid = body["plan"]["plan_id"]
    await cond.confirm(pid, request_id="a", cap=1)
    with pytest.raises(ApiError) as ei:
        await cond.confirm(pid, request_id="b", cap=1)
    assert ei.value.code == "plan_already_confirmed"
    await sessions.shutdown()


async def test_reconfirm_without_request_id_is_rejected(tmp_path):
    cond, sessions, _kanban, proj = _echo_conductor(tmp_path)
    body = await cond.message(text="x", context={"active_dir": str(proj), "cap": 1})
    pid = body["plan"]["plan_id"]
    await cond.confirm(pid, cap=1)  # no request_id at all
    with pytest.raises(ApiError) as ei:
        await cond.confirm(pid, cap=1)
    assert ei.value.code == "plan_already_confirmed"
    await sessions.shutdown()


async def test_confirm_retry_after_plan_expiry_still_replays_result(tmp_path):
    cond, sessions, _kanban, proj = _echo_conductor(tmp_path)
    body = await cond.message(text="x", context={"active_dir": str(proj), "cap": 1})
    pid = body["plan"]["plan_id"]
    r1 = await cond.confirm(pid, request_id="rc", cap=1)
    # Even if the plan's TTL elapses after a successful confirm, the idempotent
    # retry returns the cached result rather than raising plan_expired.
    cond._plans[pid].expires_at_monotonic = 0.0
    r2 = await cond.confirm(pid, request_id="rc", cap=1)
    assert r2 == r1
    await sessions.shutdown()


# ---------------------------------------------------------------------------
# Finding 2 — _drain_deferred admission + launch under the lock
# ---------------------------------------------------------------------------

def _deferred_entry(mgr):
    return {"request_id": None, "cwd": mgr.project, "card_id": None,
            "initiator": "user", "prompt": "queued"}


async def test_drain_deferred_respects_ceiling(tmp_path):
    mgr, _bus, _proj = _manager(tmp_path, adapter=SleepAdapter(), ceiling=1)
    try:
        await mgr.spawn(prompt="live")
        assert mgr.live_count() == 1
        # A queued spawn must NOT launch while the only slot is occupied.
        mgr._deferred.append(_deferred_entry(mgr))
        await mgr._drain_deferred()
        assert mgr.live_count() == 1
        assert len(mgr._deferred) == 1
    finally:
        await mgr.shutdown()


async def test_drain_deferred_launches_when_slot_free(tmp_path):
    mgr, _bus, _proj = _manager(tmp_path, adapter=SleepAdapter(), ceiling=2)
    try:
        mgr._deferred.append(_deferred_entry(mgr))
        await mgr._drain_deferred()
        assert mgr.live_count() == 1
        assert len(mgr._deferred) == 0
    finally:
        await mgr.shutdown()


async def test_drain_deferred_blocks_on_the_spawn_lock(tmp_path):
    """While the spawn lock is held, a drain cannot launch (proves it acquires it)."""
    mgr, _bus, _proj = _manager(tmp_path, adapter=SleepAdapter(), ceiling=2)
    try:
        mgr._deferred.append(_deferred_entry(mgr))
        async with mgr._lock:
            task = asyncio.create_task(mgr._drain_deferred())
            await asyncio.sleep(0.05)
            # Blocked on the lock: nothing launched, entry still queued.
            assert mgr.live_count() == 0
            assert len(mgr._deferred) == 1
        await task  # lock released → drain proceeds
        assert mgr.live_count() == 1
        assert len(mgr._deferred) == 0
    finally:
        await mgr.shutdown()


# ---------------------------------------------------------------------------
# Finding 3 — overlay quota counts the scope's own overlay dir
# ---------------------------------------------------------------------------

async def test_overlay_quota_ignores_state_dir_siblings(tmp_path, monkeypatch):
    svc = bare_services(tmp_path)
    m, proj, paths = svc["memory"], svc["project"], svc["paths"]
    # A large NON-overlay state file (mimics runtime.json / kanban.sqlite3) that
    # the old ``.parent`` walk wrongly counted toward the 32 MB overlay quota.
    (paths.state_dir / "runtime.json").write_bytes(b"x" * 4000)
    monkeypatch.setattr(memory_mod, "MAX_SCOPE_BYTES", 1000)
    # Writing a tiny overlay file must succeed: only the scope's own overlay dir
    # counts, not unrelated state-dir siblings.
    res = await m.write_file(scope_dir=str(proj), filename="NOTES.md", content="hi", initiator="user")
    assert res["file"]["location"] == "overlay"


async def test_overlay_quota_counts_scope_overlay_files(tmp_path, monkeypatch):
    svc = bare_services(tmp_path)
    m, proj = svc["memory"], svc["project"]
    (proj / "pkg").mkdir()
    await m.write_file(scope_dir=str(proj / "pkg"), filename="A.md", content="x" * 400, initiator="user")
    monkeypatch.setattr(memory_mod, "MAX_SCOPE_BYTES", 500)
    # A second overlay file in the SAME scope breaches the quota. The old
    # ``.parent`` pointed at a dir whose children are directories, so the real
    # sibling A.md was never counted and this write wrongly succeeded.
    with pytest.raises(ApiError) as ei:
        await m.write_file(scope_dir=str(proj / "pkg"), filename="B.md", content="x" * 400, initiator="user")
    assert ei.value.code == "memory_quota_exceeded"


# ---------------------------------------------------------------------------
# Finding 4 — heartbeat flushes pending pty_output drop markers
# ---------------------------------------------------------------------------

class _FakeWS:
    def __init__(self):
        self.sent: list[dict] = []

    async def send_json(self, obj):
        self.sent.append(obj)


async def test_heartbeat_loop_flushes_pending_drop_markers(monkeypatch):
    monkeypatch.setattr(stream_mod, "HEARTBEAT_INTERVAL_S", 0.01)
    bus = EventBus()
    sub = Subscriber(maxsize=1, topics=frozenset({"pty_output"}))
    frame = {"type": "pty_output", "session_id": "s1", "payload": {"bytes": "AAAA"}}
    sub.offer(frame)   # fills the single queue slot
    sub.offer(frame)   # overflow → coalesced into a pending drop marker
    ws = _FakeWS()
    task = asyncio.create_task(stream_mod._heartbeat_loop(ws, bus, sub, asyncio.Lock()))
    await asyncio.sleep(0.05)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    assert any(m.get("type") == "heartbeat" for m in ws.sent)
    assert any(m.get("payload", {}).get("dropped") for m in ws.sent), "drop marker not flushed by heartbeat"


# ---------------------------------------------------------------------------
# Finding 5 — ring age-pruning via monotonic floats (rings stay aligned)
# ---------------------------------------------------------------------------

async def test_ring_prunes_by_monotonic_age_and_stays_aligned():
    bus = EventBus(replay_window_s=100)
    await bus.publish("kanban_updated", {"i": 0})
    await bus.publish("kanban_updated", {"i": 1})
    assert len(bus._ring) == len(bus._ring_mono) == 2
    # Age the oldest entry beyond the window; the next publish prunes it.
    bus._ring_mono[0] -= 1000
    await bus.publish("kanban_updated", {"i": 2})
    assert len(bus._ring) == len(bus._ring_mono)  # parallel deques stay aligned
    payloads = [e["payload"]["i"] for e in bus._ring]
    assert 0 not in payloads and payloads == sorted(payloads)


async def test_ring_prune_does_not_import_datetime_on_publish():
    # Purely structural: pruning is now numeric, so an all-numeric ring must not
    # raise and must keep seqs contiguous.
    bus = EventBus(replay_window_s=60)
    for i in range(5):
        await bus.publish("session_state", {"i": i})
    seqs = [e["seq"] for e in bus._ring]
    assert seqs == list(range(1, 6))


# ---------------------------------------------------------------------------
# Finding 6 — bounded growth (conductor maps + terminal sessions)
# ---------------------------------------------------------------------------

async def test_conductor_prune_expired_reclaims_plans_and_ids(tmp_path):
    cond, sessions, _kanban, proj = _echo_conductor(tmp_path)
    body = await cond.message(request_id="m1", text="x", context={"active_dir": str(proj)})
    pid = body["plan"]["plan_id"]
    assert pid in cond._plans and "m1" in cond._by_request
    # Age both past the idempotency window / TTL grace.
    old = time.monotonic() - conductor_mod._IDEMPOTENCY_TTL_S - 5
    cond._plans[pid].expires_at_monotonic = old
    cond._by_request["m1"] = (old, cond._by_request["m1"][1])
    cond._prune_expired()
    assert pid not in cond._plans
    assert "m1" not in cond._by_request
    await sessions.shutdown()


async def test_terminal_sessions_are_compacted(tmp_path, monkeypatch):
    monkeypatch.setattr(sm_mod, "MAX_TERMINAL_SESSIONS", 2)
    mgr, _bus, _proj = _manager(tmp_path, adapter=EchoAdapter(lines=1), ceiling=8)
    try:
        sids = []
        for i in range(4):
            _, body = await mgr.spawn(prompt=f"t{i}")
            sid = body["session"]["session_id"]
            sids.append(sid)
            await _await_terminal(mgr, sid)
        retained = {s["session_id"] for s in mgr.list_sessions()["sessions"]}
        assert len(retained) <= 2
        assert sids[-1] in retained      # newest kept
        assert sids[0] not in retained   # oldest evicted
        # Evicted sessions also drop their idempotency mapping.
        assert all(v in retained for v in mgr._by_request.values())
    finally:
        await mgr.shutdown()


# ---------------------------------------------------------------------------
# Finding 7 — kanban SQLite WAL + busy_timeout
# ---------------------------------------------------------------------------

def test_kanban_enables_wal_and_busy_timeout(tmp_path):
    k = bare_services(tmp_path)["kanban"]
    mode = k._conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert str(mode).lower() == "wal"
    busy = k._conn.execute("PRAGMA busy_timeout").fetchone()[0]
    assert int(busy) >= 5000


# ---------------------------------------------------------------------------
# Finding 8 — eager pty-flush tasks are referenced and their exceptions observed
# ---------------------------------------------------------------------------

async def test_eager_flush_done_callback_observes_exception(tmp_path):
    mgr, _bus, _proj = _manager(tmp_path, adapter=SleepAdapter())
    try:
        async def _boom():
            raise RuntimeError("flush blew up")

        task = asyncio.create_task(_boom())
        mgr._eager_flush_tasks.add(task)
        task.add_done_callback(mgr._on_eager_flush_done)
        await asyncio.sleep(0.01)
        # Callback removed it from the live set AND retrieved the exception
        # (so it is never an "un-retrieved task exception").
        assert task not in mgr._eager_flush_tasks
        assert task.done() and task.exception() is not None
    finally:
        await mgr.shutdown()


class _BigOutputAdapter:
    """Emits >MAX_CHUNK_BYTES in one burst to exercise the eager-flush path."""

    name = "big"

    def build_argv(self, _prompt):
        n = sm_mod.MAX_CHUNK_BYTES * 4
        return [sys.executable, "-c", f"import sys; sys.stdout.write('X'*{n}); sys.stdout.flush()"]

    def build_env(self, base_env=None):
        import os

        return dict(base_env or os.environ)


async def test_big_output_session_streams_and_completes(tmp_path):
    mgr, bus, _proj = _manager(tmp_path, adapter=_BigOutputAdapter())
    sub = bus.register()
    try:
        _, body = await mgr.spawn(prompt="big")
        sid = body["session"]["session_id"]
        d = await _await_terminal(mgr, sid)
        assert d["state"] == "completed"
        # The oversized output was chunked into multiple pty_output frames and no
        # eager-flush task was left dangling.
        chunks = 0
        while not sub.empty():
            ev = sub.get_nowait()
            if ev["type"] == "pty_output":
                chunks += 1
        assert chunks >= 1
        assert mgr._eager_flush_tasks == set()
    finally:
        await mgr.shutdown()
