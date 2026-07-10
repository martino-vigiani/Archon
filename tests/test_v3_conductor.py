"""Conductor tests: plan generation, dry-run, confirm/execute, errors, cancel."""

from __future__ import annotations

import pytest

from orchestrator.v3.conductor import Conductor
from orchestrator.v3.errors import ApiError
from orchestrator.v3.events import EventBus
from orchestrator.v3.kanban import KanbanStore
from orchestrator.v3.memory import MemoryService
from orchestrator.v3.provider import FallbackProvider, ProviderError, ProviderPlan
from orchestrator.v3.session_manager import SessionManager
from orchestrator.v3.storage import resolve_paths
from orchestrator.v3.writeguard import WriteGuard
from tests._v3_util import new_project, new_support
from tests.test_v3_sessions import SleepAdapter


def _conductor(tmp_path, *, provider=None, adapter=None, ceiling=8):
    proj = new_project(tmp_path)
    paths = resolve_paths(str(proj), support=new_support(tmp_path))
    paths.ensure()
    bus = EventBus()
    guard = WriteGuard(paths=paths)
    memory = MemoryService(paths=paths, bus=bus, guard=guard)
    kanban = KanbanStore(db_path=paths.kanban_db, bus=bus)
    sessions = SessionManager(paths=paths, bus=bus, ceiling=ceiling, adapter=adapter or SleepAdapter())
    cond = Conductor(paths=paths, bus=bus, sessions=sessions, kanban=kanban, memory=memory,
                     provider=provider or FallbackProvider(), ceiling=ceiling)
    return cond, sessions, kanban, bus, proj


class FailingProvider:
    ready = True

    async def plan(self, *, text, context, ceiling):
        raise ProviderError("529 overloaded")


class CountProvider:
    """Returns a plan proposing N sessions to exercise cap reduction."""

    ready = True

    def __init__(self, n):
        self.n = n

    async def plan(self, *, text, context, ceiling):
        actions = [{"kind": "spawn_session", "cwd": context.get("active_dir"), "prompt": f"t{i}"} for i in range(self.n)]
        return ProviderPlan(summary="multi", proposed_session_count=self.n, actions=actions,
                            estimated_tokens=1000, estimated_duration_s=60)


async def test_message_returns_plan_and_dry_run(tmp_path):
    cond, sessions, *_ , proj = _conductor(tmp_path)
    body = await cond.message(request_id="i1", text="Refactor checkout", context={"active_dir": str(proj), "cap": 4})
    assert body["plan"]["plan_id"] and body["plan"]["actions"]
    assert body["dry_run"]["estimate_ready"] is True
    assert body["dry_run"]["estimated_session_count"] >= 1
    assert "expires_at" in body
    await sessions.shutdown()


async def test_message_idempotent(tmp_path):
    cond, sessions, *_ = _conductor(tmp_path)
    b1 = await cond.message(request_id="dup", text="x", context={})
    b2 = await cond.message(request_id="dup", text="x", context={})
    assert b1["plan"]["plan_id"] == b2["plan"]["plan_id"]
    await sessions.shutdown()


async def test_cap_reduction_reason(tmp_path):
    cond, sessions, *_ , proj = _conductor(tmp_path, provider=CountProvider(5), ceiling=8)
    body = await cond.message(text="big", context={"active_dir": str(proj), "cap": 2})
    assert body["plan"]["proposed_session_count"] == 5
    assert body["plan"]["final_count"] == 2
    assert body["plan"]["reduction_reason"] == "user_cap"
    await sessions.shutdown()


async def test_ceiling_reduction_reason(tmp_path):
    cond, sessions, *_ , proj = _conductor(tmp_path, provider=CountProvider(20), ceiling=8)
    body = await cond.message(text="huge", context={"active_dir": str(proj)})
    assert body["plan"]["final_count"] == 8
    assert body["plan"]["reduction_reason"] == "ceiling"
    await sessions.shutdown()


async def test_confirm_executes_spawns_and_cards(tmp_path):
    proj = new_project(tmp_path)
    paths = resolve_paths(str(proj), support=new_support(tmp_path))
    paths.ensure()
    from orchestrator.v3.adapters import EchoAdapter
    bus = EventBus()
    guard = WriteGuard(paths=paths)
    memory = MemoryService(paths=paths, bus=bus, guard=guard)
    kanban = KanbanStore(db_path=paths.kanban_db, bus=bus)
    sessions = SessionManager(paths=paths, bus=bus, ceiling=8, adapter=EchoAdapter(lines=1))
    cond = Conductor(paths=paths, bus=bus, sessions=sessions, kanban=kanban, memory=memory,
                     provider=FallbackProvider(), ceiling=8)
    body = await cond.message(text="Add tests", context={"active_dir": str(proj), "cap": 2})
    res = await cond.confirm(body["plan"]["plan_id"], cap=2)
    assert res["status"] in ("executing", "partial")
    assert len(res["created_session_ids"]) >= 1
    assert len(res["created_card_ids"]) >= 1
    # The spawned session was bound to the created card.
    snap = await kanban.snapshot()
    assert any(c["session_id"] for c in snap["cards"])
    await sessions.shutdown()


async def test_confirm_unknown_and_expired(tmp_path):
    cond, sessions, *_ = _conductor(tmp_path)
    with pytest.raises(ApiError) as ei:
        await cond.confirm("does-not-exist")
    assert ei.value.code == "not_found"
    body = await cond.message(text="x", context={})
    plan_id = body["plan"]["plan_id"]
    # Force expiry.
    cond._plans[plan_id].expires_at_monotonic = 0.0
    with pytest.raises(ApiError) as ei2:
        await cond.confirm(plan_id)
    assert ei2.value.code == "plan_expired"
    await sessions.shutdown()


async def test_provider_error_surfaces_and_sets_error_state(tmp_path):
    cond, sessions, kanban, bus, proj = _conductor(tmp_path, provider=FailingProvider())
    sub = bus.register()
    with pytest.raises(ApiError) as ei:
        await cond.message(text="x", context={})
    assert ei.value.code == "provider_error"
    # An error event + conductor error state were emitted; running terminals unaffected.
    types = []
    while not sub.empty():
        types.append(sub.get_nowait())
    assert any(e["type"] == "error" for e in types)
    assert any(e["type"] == "conductor_state" and e["payload"]["state"] == "error" for e in types)
    assert cond.current_state() == "error"
    await sessions.shutdown()


async def test_cancel_plan(tmp_path):
    cond, sessions, *_ = _conductor(tmp_path)
    body = await cond.message(text="x", context={})
    res = await cond.cancel(body["plan"]["plan_id"])
    assert res["status"] == "cancelled"
    await sessions.shutdown()


async def test_memory_edit_is_proposal_never_write(tmp_path):
    proj = new_project(tmp_path)
    paths = resolve_paths(str(proj), support=new_support(tmp_path))
    paths.ensure()
    bus = EventBus()
    guard = WriteGuard(paths=paths)
    memory = MemoryService(paths=paths, bus=bus, guard=guard)
    kanban = KanbanStore(db_path=paths.kanban_db, bus=bus)
    sessions = SessionManager(paths=paths, bus=bus, ceiling=8, adapter=SleepAdapter())

    class MemProvider:
        ready = True

        async def plan(self, *, text, context, ceiling):
            return ProviderPlan(
                summary="edit",
                proposed_session_count=1,
                actions=[{"kind": "propose_memory_edit", "scope_dir": str(proj),
                          "filename": "CLAUDE.md", "proposed_content": "# proposed\n"}],
                estimated_tokens=100, estimated_duration_s=10,
            )

    cond = Conductor(paths=paths, bus=bus, sessions=sessions, kanban=kanban, memory=memory,
                     provider=MemProvider(), ceiling=8)
    body = await cond.message(text="update memory", context={"active_dir": str(proj)})
    await cond.confirm(body["plan"]["plan_id"])
    # The Conductor NEVER writes to the project (Addendum §A3).
    assert not (proj / "CLAUDE.md").exists()
    await sessions.shutdown()
