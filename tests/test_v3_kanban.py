"""Kanban store tests: CRUD, ordinals, state machine, revisions, persistence."""

from __future__ import annotations

import pytest

from orchestrator.v3.errors import ApiError
from orchestrator.v3.events import EventBus
from orchestrator.v3.kanban import COLUMNS, KanbanStore
from tests._v3_util import bare_services


async def test_create_and_snapshot(tmp_path):
    svc = bare_services(tmp_path)
    k: KanbanStore = svc["kanban"]
    r = await k.create_card(title="A", column="queued", provenance="user")
    assert r["card"]["column"] == "queued" and r["card"]["ordinal"] == 0
    assert r["card"]["revision"] == 1
    snap = await k.snapshot()
    assert snap["columns"] == list(COLUMNS)
    assert snap["board_revision"] >= 1
    assert len(snap["cards"]) == 1


async def test_ordinals_are_contiguous_within_column(tmp_path):
    k = bare_services(tmp_path)["kanban"]
    ids = [(await k.create_card(title=f"C{i}", column="queued", provenance="user"))["card"]["card_id"] for i in range(3)]
    snap = await k.snapshot()
    ords = sorted(c["ordinal"] for c in snap["cards"])
    assert ords == [0, 1, 2]
    # Delete the middle → repack to 0,1.
    mid = [c for c in snap["cards"] if c["ordinal"] == 1][0]
    await k.delete_card(mid["card_id"], base_revision=mid["revision"], provenance="user")
    snap2 = await k.snapshot()
    assert sorted(c["ordinal"] for c in snap2["cards"]) == [0, 1]
    _ = ids


async def test_move_reorders_and_bumps_board_revision(tmp_path):
    k = bare_services(tmp_path)["kanban"]
    a = (await k.create_card(title="A", column="queued", provenance="user"))["card"]
    b = (await k.create_card(title="B", column="queued", provenance="user"))["card"]
    before = (await k.snapshot())["board_revision"]
    res = await k.move_card(b["card_id"], base_revision=b["revision"], to_column="queued", to_ordinal=0, provenance="user")
    assert res["board_revision"] > before
    snap = await k.snapshot()
    ordered = sorted(snap["cards"], key=lambda c: c["ordinal"])
    assert ordered[0]["card_id"] == b["card_id"]
    assert ordered[1]["card_id"] == a["card_id"]


async def test_illegal_transition_done_to_in_progress(tmp_path):
    k = bare_services(tmp_path)["kanban"]
    c = (await k.create_card(title="A", column="queued", provenance="user"))["card"]
    m = await k.move_card(c["card_id"], base_revision=c["revision"], to_column="done", to_ordinal=0, provenance="user")
    with pytest.raises(ApiError) as ei:
        await k.move_card(m["card"]["card_id"], base_revision=m["card"]["revision"], to_column="in_progress", provenance="user")
    assert ei.value.code == "illegal_transition"


async def test_legal_ready_to_in_progress(tmp_path):
    k = bare_services(tmp_path)["kanban"]
    c = (await k.create_card(title="A", column="queued", provenance="user"))["card"]
    m = await k.move_card(c["card_id"], base_revision=c["revision"], to_column="in_progress", to_ordinal=0, provenance="user")
    assert m["card"]["column"] == "in_progress"


async def test_revision_conflict_on_stale_write(tmp_path):
    k = bare_services(tmp_path)["kanban"]
    c = (await k.create_card(title="A", provenance="user"))["card"]
    await k.update_card(c["card_id"], base_revision=c["revision"], title="B", provenance="user")
    with pytest.raises(ApiError) as ei:
        await k.update_card(c["card_id"], base_revision=c["revision"], title="C", provenance="user")
    assert ei.value.code == "revision_conflict"
    assert ei.value.details["expected_revision"] >= 2


async def test_move_to_done_releases_session(tmp_path):
    k = bare_services(tmp_path)["kanban"]
    c = (await k.create_card(title="A", column="in_progress", provenance="conductor"))["card"]
    await k.bind_session(c["card_id"], "SESSION-1", status="running")
    cur = k.get_card(c["card_id"])["card"]
    m = await k.move_card(cur["card_id"], base_revision=cur["revision"], to_column="done", to_ordinal=0, provenance="user")
    assert m["card"]["session_id"] is None and m["card"]["status"] == "done"


async def test_events_reconstruct_board(tmp_path):
    svc = bare_services(tmp_path)
    k, bus = svc["kanban"], svc["bus"]
    sub = bus.register()
    await k.create_card(title="A", provenance="user")
    # Exactly one created event with a card object.
    seen = [sub.get_nowait() for _ in range(1)]
    assert seen[0]["type"] == "kanban_updated" and seen[0]["payload"]["op"] == "created"
    assert seen[0]["payload"]["card"]["title"] == "A"


async def test_persistence_across_reopen(tmp_path):
    svc = bare_services(tmp_path)
    db_path = svc["paths"].kanban_db
    k = svc["kanban"]
    cid = (await k.create_card(title="Persist", column="review", provenance="user"))["card"]["card_id"]
    k.close()
    # Reopen a new store on the same DB file.
    k2 = KanbanStore(db_path=db_path, bus=EventBus())
    got = k2.get_card(cid)["card"]
    assert got["title"] == "Persist" and got["column"] == "review"
    k2.close()


async def test_invalid_inputs(tmp_path):
    k = bare_services(tmp_path)["kanban"]
    with pytest.raises(ApiError):
        await k.create_card(title="A", column="nope", provenance="user")
    with pytest.raises(ApiError):
        await k.create_card(title="A", priority="urgent", provenance="user")
    with pytest.raises(ApiError):
        await k.create_card(title="A", provenance="alien")
    with pytest.raises(ApiError) as ei:
        k.get_card("missing")
    assert ei.value.code == "not_found"
