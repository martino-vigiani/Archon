"""Kanban revision-race and edge-case tests — phase C coverage.

Gaps not covered by test_v3_kanban.py:
* Stale DELETE after a concurrent move (revision mismatch on delete).
* Stale PATCH after a concurrent move.
* update_card with body field only (no title change).
* move then update on correct revised revision succeeds.
* Provenance is preserved through create / move / update round-trip.
* get_card on deleted card → not_found.
"""

from __future__ import annotations

import pytest

from orchestrator.v3.errors import ApiError
from orchestrator.v3.kanban import KanbanStore
from orchestrator.v3.events import EventBus
from tests._v3_util import bare_services


# ---------------------------------------------------------------------------
# Stale delete after concurrent move
# ---------------------------------------------------------------------------

async def test_stale_delete_after_move_conflicts(tmp_path):
    """delete_card with a pre-move base_revision after the card has moved → revision_conflict."""
    k: KanbanStore = bare_services(tmp_path)["kanban"]
    c = (await k.create_card(title="A", column="queued", provenance="user"))["card"]
    stale_rev = c["revision"]
    # Move increments the revision.
    moved = await k.move_card(c["card_id"], base_revision=stale_rev, to_column="in_progress", provenance="user")
    assert moved["card"]["revision"] > stale_rev

    # Delete using the stale (pre-move) revision → conflict.
    with pytest.raises(ApiError) as ei:
        await k.delete_card(c["card_id"], base_revision=stale_rev, provenance="user")
    assert ei.value.code == "revision_conflict"


# ---------------------------------------------------------------------------
# Stale PATCH after a concurrent move
# ---------------------------------------------------------------------------

async def test_stale_patch_after_move_conflicts(tmp_path):
    """update_card with a pre-move base_revision → revision_conflict."""
    k = bare_services(tmp_path)["kanban"]
    c = (await k.create_card(title="Orig", column="queued", provenance="user"))["card"]
    stale_rev = c["revision"]

    await k.move_card(c["card_id"], base_revision=stale_rev, to_column="review", provenance="user")

    with pytest.raises(ApiError) as ei:
        await k.update_card(c["card_id"], base_revision=stale_rev, title="New", provenance="user")
    assert ei.value.code == "revision_conflict"
    assert ei.value.details.get("expected_revision", 0) > stale_rev


# ---------------------------------------------------------------------------
# update_card with body field only
# ---------------------------------------------------------------------------

async def test_update_body_only_increments_revision(tmp_path):
    """Updating only the body field increments the revision and preserves title."""
    k = bare_services(tmp_path)["kanban"]
    c = (await k.create_card(title="MyCard", column="queued", provenance="user"))["card"]
    updated = await k.update_card(c["card_id"], base_revision=c["revision"], body="New body", provenance="user")
    assert updated["card"]["title"] == "MyCard"  # title unchanged
    assert updated["card"]["body"] == "New body"
    assert updated["card"]["revision"] == c["revision"] + 1


async def test_update_priority_only(tmp_path):
    """Updating only the priority field works and increments revision."""
    k = bare_services(tmp_path)["kanban"]
    c = (await k.create_card(title="T", column="queued", priority="normal", provenance="user"))["card"]
    updated = await k.update_card(c["card_id"], base_revision=c["revision"], priority="high", provenance="user")
    assert updated["card"]["priority"] == "high"
    assert updated["card"]["revision"] == c["revision"] + 1


# ---------------------------------------------------------------------------
# Move then update on correct (new) revision succeeds
# ---------------------------------------------------------------------------

async def test_move_then_update_with_correct_revision(tmp_path):
    """Using the post-move revision for an update succeeds (no stale conflict)."""
    k = bare_services(tmp_path)["kanban"]
    c = (await k.create_card(title="X", column="queued", provenance="user"))["card"]
    moved = await k.move_card(c["card_id"], base_revision=c["revision"], to_column="in_progress", provenance="user")
    new_rev = moved["card"]["revision"]

    updated = await k.update_card(c["card_id"], base_revision=new_rev, title="X Updated", provenance="user")
    assert updated["card"]["title"] == "X Updated"
    assert updated["card"]["revision"] == new_rev + 1


# ---------------------------------------------------------------------------
# Provenance round-trip
# ---------------------------------------------------------------------------

async def test_conductor_provenance_preserved(tmp_path):
    """Cards created with conductor provenance keep it through updates."""
    k = bare_services(tmp_path)["kanban"]
    c = (await k.create_card(title="C", column="queued", provenance="conductor"))["card"]
    assert c["provenance"] == "conductor"

    updated = await k.update_card(c["card_id"], base_revision=c["revision"], title="C2", provenance="conductor")
    assert updated["card"]["provenance"] == "conductor"


# ---------------------------------------------------------------------------
# get_card after delete
# ---------------------------------------------------------------------------

async def test_get_card_after_delete_is_not_found(tmp_path):
    """get_card on a deleted card raises not_found (not revision_conflict)."""
    k = bare_services(tmp_path)["kanban"]
    c = (await k.create_card(title="Delete me", provenance="user"))["card"]
    await k.delete_card(c["card_id"], base_revision=c["revision"], provenance="user")

    with pytest.raises(ApiError) as ei:
        k.get_card(c["card_id"])
    assert ei.value.code == "not_found"


# ---------------------------------------------------------------------------
# Repeated stale delete → same error each time (no state corruption)
# ---------------------------------------------------------------------------

async def test_repeated_stale_delete_does_not_corrupt(tmp_path):
    """Multiple failed stale deletes leave the card intact and readable."""
    k = bare_services(tmp_path)["kanban"]
    c = (await k.create_card(title="Stable", provenance="user"))["card"]
    stale_rev = c["revision"] - 1  # always stale

    for _ in range(3):
        with pytest.raises(ApiError) as ei:
            await k.delete_card(c["card_id"], base_revision=stale_rev, provenance="user")
        assert ei.value.code == "revision_conflict"

    # Card is still intact.
    still_there = k.get_card(c["card_id"])["card"]
    assert still_there["title"] == "Stable"


# ---------------------------------------------------------------------------
# Board revision monotonically increases across mixed operations
# ---------------------------------------------------------------------------

async def test_board_revision_monotonically_increases(tmp_path):
    """board_revision increments with each mutation (create, move, delete)."""
    k = bare_services(tmp_path)["kanban"]
    s0 = (await k.snapshot())["board_revision"]

    c = (await k.create_card(title="A", provenance="user"))["card"]
    s1 = (await k.snapshot())["board_revision"]
    assert s1 > s0

    moved = await k.move_card(c["card_id"], base_revision=c["revision"], to_column="review", provenance="user")
    s2 = moved["board_revision"]
    assert s2 > s1

    await k.delete_card(c["card_id"], base_revision=moved["card"]["revision"], provenance="user")
    s3 = (await k.snapshot())["board_revision"]
    assert s3 > s2
