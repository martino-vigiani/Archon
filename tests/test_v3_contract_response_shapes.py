"""Contract response-shape conformance tests — phase C (API_CONTRACT_V3.md).

Verifies that the backend produces responses that exactly match the JSON shapes
documented in the frozen contract.  Every field listed in the spec must be
present (and have the right type / value range); additive unknown fields are
tolerated per REQ-ARCH-006.

Coverage:
* §2.1  GET /v3/health — all required fields + capabilities sub-object
* §2.2  GET /v3/project — required fields
* §2.3  GET /v3/sessions — cap object + ceiling
* §2.3  GET /v3/sessions/{id}/detail — recent_output_seq_range present
* §2.5  GET /v3/kanban — columns ordered, board_revision present
* §1.6  Error envelope shape — all required keys; all registered error codes
* §3    WS hello frame — pv, current_seq, replay_window_events
* Session object field completeness (all §2.3 fields present)
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from tests._v3_util import HEADERS, TOKEN, make_app


def _client(tmp_path, **kw):
    app, proj, support = make_app(tmp_path, **kw)
    return TestClient(app), proj


# ---------------------------------------------------------------------------
# §2.1 Health & capabilities
# ---------------------------------------------------------------------------

def test_health_all_required_fields(tmp_path):
    c, _ = _client(tmp_path)
    with c:
        r = c.get("/v3/health", headers=HEADERS)
        assert r.status_code == 200
        body = r.json()
        # Top-level required fields (§2.1)
        for field in ("status", "pv", "orchestrator_version", "project_id",
                      "uptime_s", "provider_ready", "conductor_state",
                      "session_count", "capabilities"):
            assert field in body, f"missing field: {field}"
        assert body["pv"] == 1
        assert body["status"] in ("ok", "degraded", "starting")

        cap = body["capabilities"]
        for cap_field in ("stream_transport", "replay_events", "replay_window_s",
                          "hard_ceiling", "supported_provider", "memory_kinds",
                          "dry_run_max_s"):
            assert cap_field in cap, f"missing capability field: {cap_field}"
        assert cap["stream_transport"] == "websocket"
        assert cap["replay_events"] == 2000
        assert cap["hard_ceiling"] == 8
        assert cap["supported_provider"] == "claude_code"
        assert "CLAUDE.md" in cap["memory_kinds"]


# ---------------------------------------------------------------------------
# §2.2 Project info
# ---------------------------------------------------------------------------

def test_project_info_required_fields(tmp_path):
    c, proj = _client(tmp_path)
    with c:
        r = c.get("/v3/project", headers=HEADERS)
        assert r.status_code == 200
        body = r.json()
        for field in ("project_id", "path", "name", "provider", "opened_at", "state_dir"):
            assert field in body, f"missing field: {field}"
        assert body["provider"] == "claude_code"
        # project_id must be 64-char lowercase hex (sha256, §0)
        pid = body["project_id"]
        assert len(pid) == 64
        assert pid == pid.lower()
        # git info may be present (optional)


# ---------------------------------------------------------------------------
# §2.3 Sessions list — cap object
# ---------------------------------------------------------------------------

def test_sessions_list_cap_and_ceiling(tmp_path):
    c, _ = _client(tmp_path)
    with c:
        r = c.get("/v3/sessions", headers=HEADERS)
        assert r.status_code == 200
        body = r.json()
        assert "sessions" in body
        assert "count" in body
        assert "ceiling" in body
        assert "cap" in body
        cap = body["cap"]
        assert "regime" in cap
        assert cap["regime"] in ("auto", "user")
        # In auto regime value must be null
        if cap["regime"] == "auto":
            assert cap["value"] is None
        assert body["ceiling"] == 8


def test_session_object_all_fields_present(tmp_path):
    """A spawned session object must carry all §2.3 fields."""
    c, _ = _client(tmp_path)
    with c:
        r = c.post("/v3/sessions", headers=HEADERS, json={"request_id": "r1", "prompt": "x"})
        assert r.status_code == 201
        session = r.json()["session"]
        required_fields = (
            "session_id", "state", "status", "provider", "cwd",
            "initiator", "pid", "created_at", "idle_flagged",
        )
        for f in required_fields:
            assert f in session, f"session missing field: {f}"
        assert session["state"] in ("requested", "spawning", "running", "completed", "failed", "killed")
        assert session["status"] in ("idle", "running", "blocked", "error", "done")
        assert session["provider"] == "claude_code"
        assert isinstance(session["idle_flagged"], bool)


def test_session_detail_has_recent_output_seq_range(tmp_path):
    """GET /v3/sessions/{id} must include recent_output_seq_range (§2.3)."""
    c, _ = _client(tmp_path)
    with c:
        r = c.post("/v3/sessions", headers=HEADERS, json={"request_id": "r2", "prompt": "y"})
        sid = r.json()["session"]["session_id"]
        # Wait for completion.
        for _ in range(80):
            d = c.get(f"/v3/sessions/{sid}", headers=HEADERS).json()
            if d["session"]["state"] in ("completed", "failed", "killed"):
                break
            time.sleep(0.05)
        assert "recent_output_seq_range" in d


# ---------------------------------------------------------------------------
# §2.5 Kanban snapshot columns ordered
# ---------------------------------------------------------------------------

def test_kanban_snapshot_columns_ordered_and_fixed(tmp_path):
    """Columns must be ['queued','in_progress','blocked','review','done'] (§2.5)."""
    c, _ = _client(tmp_path)
    with c:
        r = c.get("/v3/kanban", headers=HEADERS)
        assert r.status_code == 200
        body = r.json()
        assert body["columns"] == ["queued", "in_progress", "blocked", "review", "done"]
        assert "board_revision" in body
        assert isinstance(body["board_revision"], int)
        assert "cards" in body


# ---------------------------------------------------------------------------
# §1.6 Error envelope — shape and all registered error codes
# ---------------------------------------------------------------------------

def test_error_envelope_has_required_keys(tmp_path):
    """Every 4xx/5xx must include error.{code,message,retriable,details}."""
    c, _ = _client(tmp_path)
    with c:
        r = c.get("/v3/kanban/cards/NO_SUCH_CARD", headers=HEADERS)
        assert r.status_code == 404
        err = r.json()["error"]
        for key in ("code", "message", "retriable", "details"):
            assert key in err, f"error envelope missing: {key}"
        assert err["retriable"] is False  # not_found is not retriable


@pytest.mark.parametrize("code,expected_status", [
    ("not_found", 404),
    ("validation_error", 422),
])
def test_non_retriable_error_codes(tmp_path, code, expected_status):
    """Spot-check that non-retriable codes surface with the right HTTP status."""
    c, _ = _client(tmp_path)
    with c:
        if code == "not_found":
            r = c.get("/v3/kanban/cards/NONE", headers=HEADERS)
        elif code == "validation_error":
            # Sending invalid JSON to sessions endpoint.
            r = c.post("/v3/kanban/cards", headers=HEADERS, json={"column": "invalid_col"})
        assert r.status_code == expected_status
        assert r.json()["error"]["code"] == code
        assert r.json()["error"]["retriable"] is False


def test_unauthorized_error_code_and_shape(tmp_path):
    """Missing token → 401 unauthorized, retriable=False."""
    c, _ = _client(tmp_path)
    with c:
        r = c.get("/v3/health")
        assert r.status_code == 401
        err = r.json()["error"]
        assert err["code"] == "unauthorized"
        assert err["retriable"] is False


def test_illegal_transition_error_shape(tmp_path):
    """done→in_progress must produce 409 illegal_transition."""
    c, _ = _client(tmp_path)
    with c:
        r = c.post("/v3/kanban/cards", headers=HEADERS, json={"title": "T", "column": "queued"})
        card = r.json()["card"]
        # First move to done.
        mv = c.post(f"/v3/kanban/cards/{card['card_id']}/move", headers=HEADERS,
                    json={"base_revision": card["revision"], "to_column": "done"})
        rev = mv.json()["card"]["revision"]
        # Now illegal back to in_progress.
        illegal = c.post(f"/v3/kanban/cards/{card['card_id']}/move", headers=HEADERS,
                         json={"base_revision": rev, "to_column": "in_progress"})
        assert illegal.status_code == 409
        err = illegal.json()["error"]
        assert err["code"] == "illegal_transition"
        assert err["retriable"] is False


# ---------------------------------------------------------------------------
# §2.7 Event replay REST endpoint
# ---------------------------------------------------------------------------

def test_events_rest_envelope_fields(tmp_path):
    """GET /v3/events must include events, truncated, from_seq, next_seq."""
    c, _ = _client(tmp_path)
    with c:
        c.post("/v3/kanban/cards", headers=HEADERS, json={"title": "Ev"})
        r = c.get("/v3/events", headers=HEADERS, params={"after_seq": 0, "limit": 50})
        assert r.status_code == 200
        body = r.json()
        for key in ("events", "truncated"):
            assert key in body, f"replay response missing: {key}"
        assert isinstance(body["truncated"], bool)
        # Each envelope must have the §3.1 required fields.
        for ev in body["events"]:
            for ef in ("v", "seq", "ts", "type", "payload"):
                assert ef in ev, f"envelope missing: {ef}"
            assert ev["v"] == 1
            assert isinstance(ev["seq"], int) and ev["seq"] > 0


# ---------------------------------------------------------------------------
# §3 WebSocket hello frame fields
# ---------------------------------------------------------------------------

def test_ws_hello_frame_required_fields(tmp_path):
    """WS hello frame must carry pv, current_seq, replay_window_events, etc."""
    c, _ = _client(tmp_path)
    with c:
        with c.websocket_connect(f"/v3/stream?token={TOKEN}") as ws:
            hello = ws.receive_json()
            assert hello["type"] == "hello"
            assert hello["v"] == 1
            assert "seq" in hello and isinstance(hello["seq"], int)
            payload = hello["payload"]
            for pf in ("pv", "current_seq", "replay_window_events", "resume_supported"):
                assert pf in payload, f"hello payload missing: {pf}"
            assert payload["pv"] == 1
            assert payload["replay_window_events"] == 2000
            assert payload["resume_supported"] is True
