"""Replay ring boundary tests — phase C coverage (REQ-BE-043 / Q12).

Tests for the exact 2000-event ring (contract §2.7 + §3.5):
* Exactly 2000 events fills the ring without truncation.
* The 2001st event wraps: the oldest is replaced; asking for it → truncated.
* after_seq boundary arithmetic (oldest-1 is NOT truncated, oldest-2 IS).
* after_seq beyond current_seq → empty result, not truncated.
* limit parameter is respected.
* Empty bus → not truncated for any after_seq.
"""

from __future__ import annotations

import pytest

from orchestrator.v3.events import EventBus, REPLAY_MAX_EVENTS


RING_SIZE = REPLAY_MAX_EVENTS  # normative 2000


# ---------------------------------------------------------------------------
# Exact ring capacity
# ---------------------------------------------------------------------------

async def test_ring_at_exactly_max_events_not_truncated():
    """Publishing exactly REPLAY_MAX_EVENTS events keeps all of them; no truncation."""
    bus = EventBus()
    for i in range(RING_SIZE):
        await bus.publish("kanban_updated", {"i": i})

    # after_seq=0: oldest seq is 1, so after_seq < oldest-1 means 0 < 0 → False → not truncated.
    # Pass limit=RING_SIZE to retrieve all events (default limit=500 would cap the count).
    evs, truncated = bus.snapshot_since(0, limit=RING_SIZE)
    assert truncated is False
    assert len(evs) == RING_SIZE
    # Seqs must be contiguous 1…2000.
    assert [e["seq"] for e in evs] == list(range(1, RING_SIZE + 1))


async def test_ring_wraparound_after_one_extra_event():
    """2001st event drops the oldest (seq=1); after_seq=0 → truncated."""
    bus = EventBus()
    for i in range(RING_SIZE + 1):
        await bus.publish("kanban_updated", {"i": i})

    # Pass limit=RING_SIZE+1 so we see the full ring content, not just 500.
    evs, truncated = bus.snapshot_since(0, limit=RING_SIZE + 1)
    assert truncated is True
    # The ring contains seqs 2…2001.
    assert evs[0]["seq"] == 2
    assert evs[-1]["seq"] == RING_SIZE + 1
    assert len(evs) == RING_SIZE


async def test_oldest_minus_one_is_not_truncated():
    """after_seq = oldest_seq - 1 → NOT truncated (contract: all events available)."""
    bus = EventBus(replay_max_events=10)
    for i in range(15):
        await bus.publish("session_state", {"i": i})
    # Ring holds seqs 6…15; oldest = 6.
    evs_full, _ = bus.snapshot_since(0)
    oldest = evs_full[0]["seq"]  # should be 6
    assert oldest == 6

    # after_seq = oldest - 1 = 5 → all 10 ring entries available → not truncated.
    evs, truncated = bus.snapshot_since(oldest - 1)
    assert truncated is False
    assert len(evs) == 10


async def test_oldest_minus_two_is_truncated():
    """after_seq = oldest_seq - 2 → truncated (events lost before buffer horizon)."""
    bus = EventBus(replay_max_events=10)
    for i in range(15):
        await bus.publish("conductor_state", {"i": i})
    evs_full, _ = bus.snapshot_since(0)
    oldest = evs_full[0]["seq"]  # 6

    # after_seq = oldest - 2 = 4 → seq 5 was evicted → truncated.
    _, truncated = bus.snapshot_since(oldest - 2)
    assert truncated is True


# ---------------------------------------------------------------------------
# after_seq beyond current_seq
# ---------------------------------------------------------------------------

async def test_after_seq_beyond_current_seq_empty_not_truncated():
    """after_seq > current_seq returns empty events and is NOT truncated."""
    bus = EventBus()
    await bus.publish("heartbeat", {"current_seq": 1})
    current = bus.current_seq()

    evs, truncated = bus.snapshot_since(current + 1_000)
    assert evs == []
    assert truncated is False


async def test_after_seq_equals_current_seq_empty_not_truncated():
    """after_seq == current_seq → empty (nothing newer) and not truncated."""
    bus = EventBus()
    for _ in range(5):
        await bus.publish("heartbeat", {"x": 1})
    current = bus.current_seq()
    evs, truncated = bus.snapshot_since(current)
    assert evs == []
    assert truncated is False


# ---------------------------------------------------------------------------
# limit parameter
# ---------------------------------------------------------------------------

async def test_limit_parameter_is_respected():
    """snapshot_since with a limit smaller than ring size returns at most limit events."""
    bus = EventBus()
    for i in range(50):
        await bus.publish("pty_output", {"bytes": "x"})
    evs, _ = bus.snapshot_since(0, limit=10)
    assert len(evs) == 10
    # Must be the FIRST 10 (lowest seqs).
    assert evs[0]["seq"] == 1
    assert evs[9]["seq"] == 10


# ---------------------------------------------------------------------------
# Empty bus
# ---------------------------------------------------------------------------

async def test_empty_bus_not_truncated():
    """An empty bus never returns truncated for any after_seq."""
    bus = EventBus()
    evs, truncated = bus.snapshot_since(0)
    assert evs == []
    assert truncated is False

    evs, truncated = bus.snapshot_since(999)
    assert evs == []
    assert truncated is False


# ---------------------------------------------------------------------------
# Replay ordering guaranteed
# ---------------------------------------------------------------------------

async def test_replay_ordering_is_ascending():
    """Events returned by snapshot_since are always in ascending seq order."""
    bus = EventBus(replay_max_events=20)
    for i in range(25):
        await bus.publish("kanban_updated", {"i": i})
    evs, _ = bus.snapshot_since(0)
    seqs = [e["seq"] for e in evs]
    assert seqs == sorted(seqs)
    assert seqs == list(range(seqs[0], seqs[0] + len(seqs)))


# ---------------------------------------------------------------------------
# current_seq counter
# ---------------------------------------------------------------------------

async def test_current_seq_matches_last_published():
    """current_seq() always equals the highest seq published."""
    bus = EventBus()
    for i in range(7):
        env = await bus.publish("heartbeat", {"x": i})
        assert bus.current_seq() == env["seq"]
