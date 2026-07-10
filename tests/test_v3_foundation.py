"""Foundation tests: IDs, storage/runtime handshake, event bus + replay ring."""

from __future__ import annotations

import os
import stat

import pytest

from orchestrator.v3.events import EventBus, Subscriber
from orchestrator.v3.ids import is_ulid, new_ulid, project_id_for, canonical_project_path
from orchestrator.v3.storage import (
    append_audit,
    delete_runtime_file,
    read_runtime_file,
    resolve_paths,
    write_runtime_file,
)
from tests._v3_util import new_project, new_support


# -- IDs -------------------------------------------------------------------
def test_ulid_is_monotonic_and_sortable():
    ids = [new_ulid() for _ in range(5000)]
    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)
    assert all(is_ulid(x) and len(x) == 26 for x in ids)


def test_project_id_is_deterministic_and_canonical():
    a = project_id_for("/tmp/../tmp/proj")
    b = project_id_for("/tmp/proj")
    assert a == b
    assert len(a) == 64 and all(c in "0123456789abcdef" for c in a)
    assert canonical_project_path("/tmp/../tmp/proj").endswith("/tmp/proj")


# -- storage / runtime handshake ------------------------------------------
def test_runtime_file_is_0600_and_roundtrips(tmp_path):
    paths = resolve_paths(str(new_project(tmp_path)), support=new_support(tmp_path))
    p = write_runtime_file(paths, port=51423, pid=4242, token="a" * 64)
    assert (os.stat(p).st_mode & 0o777) == 0o600
    data = read_runtime_file(p)
    assert data["port"] == 51423 and data["pid"] == 4242 and data["pv"] == 1
    assert data["project_id"] == paths.project_id
    delete_runtime_file(p)
    assert not p.exists()


def test_runtime_file_refuses_group_readable(tmp_path):
    paths = resolve_paths(str(new_project(tmp_path)), support=new_support(tmp_path))
    p = write_runtime_file(paths, port=1, pid=1, token="t" * 64)
    os.chmod(p, 0o640)
    with pytest.raises(PermissionError):
        read_runtime_file(p)


def test_state_dir_is_outside_project(tmp_path):
    proj = new_project(tmp_path)
    paths = resolve_paths(str(proj), support=new_support(tmp_path))
    # State dir must never be inside the project tree (zero-footprint).
    assert paths.project_id in str(paths.state_dir)
    assert not str(paths.state_dir).startswith(str(proj) + os.sep)
    paths.ensure()
    assert (os.stat(paths.state_dir).st_mode & 0o077) == 0


def test_audit_append_is_owner_only(tmp_path):
    paths = resolve_paths(str(new_project(tmp_path)), support=new_support(tmp_path))
    paths.ensure()
    append_audit(paths, {"event": "x"})
    assert paths.audit_log.is_file()
    assert (os.stat(paths.audit_log).st_mode & stat.S_IRWXO) == 0


# -- event bus / seq / replay ---------------------------------------------
async def test_seq_is_global_monotonic_gap_free():
    bus = EventBus()
    for i in range(10):
        env = await bus.publish("session_state", {"i": i}, session_id="S")
        assert env["seq"] == i + 1
        assert env["v"] == 1 and "ts" in env
    assert bus.current_seq() == 10


async def test_snapshot_since_and_truncation():
    bus = EventBus(replay_max_events=5)
    for i in range(8):
        await bus.publish("kanban_updated", {"i": i})
    # Ring holds only the last 5 (seq 4..8). Asking after_seq=1 → truncated.
    evs, truncated = bus.snapshot_since(1)
    assert truncated is True
    # Asking after a retained seq → not truncated, contiguous.
    evs, truncated = bus.snapshot_since(6)
    assert [e["seq"] for e in evs] == [7, 8]
    assert truncated is False


async def test_replay_into_subscriber():
    bus = EventBus()
    for _ in range(5):
        await bus.publish("conductor_state", {"state": "thinking"})
    sub = bus.register()
    truncated = bus.replay_into(sub, after_seq=2)
    assert truncated is False
    got = []
    while not sub.empty():
        got.append(sub.get_nowait()["seq"])
    assert got == [3, 4, 5]


async def test_pty_output_backpressure_drop_marker():
    bus = EventBus()
    sub = Subscriber(maxsize=2)
    # Fill the queue, then overflow with pty_output → coalesced to a marker.
    for _ in range(2):
        sub.offer({"type": "pty_output", "session_id": "S", "payload": {"bytes": "AAAA"}})
    sub.offer({"type": "pty_output", "session_id": "S", "payload": {"bytes": "BBBB"}})
    markers = sub.take_drop_markers()
    assert len(markers) == 1
    assert markers[0]["payload"]["dropped"] is True
    assert markers[0]["payload"]["dropped_bytes"] > 0


async def test_never_drop_topic_forces_disconnect():
    sub = Subscriber(maxsize=1)
    sub.offer({"type": "kanban_updated", "payload": {"op": "created"}})
    sub.offer({"type": "kanban_updated", "payload": {"op": "moved"}})  # overflow
    assert sub.must_disconnect is True
    assert sub.disconnect_reason == "rate_limited"


async def test_subscriber_topic_filter():
    sub = Subscriber(maxsize=10, topics=frozenset({"kanban"}))
    sub.offer({"type": "pty_output", "session_id": "S", "payload": {}})
    sub.offer({"type": "kanban_updated", "payload": {"op": "created"}})
    assert not sub.empty()
    assert sub.get_nowait()["type"] == "kanban_updated"
    assert sub.empty()
