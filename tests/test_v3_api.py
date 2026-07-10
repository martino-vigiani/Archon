"""HTTP + WebSocket contract tests for the V3 app (auth, endpoints, stream)."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from tests._v3_util import HEADERS, TOKEN, make_app


def _client(tmp_path, **kw):
    app, proj, support = make_app(tmp_path, **kw)
    return TestClient(app), proj


# -- auth / versioning -----------------------------------------------------
def test_health_requires_token(tmp_path):
    c, _ = _client(tmp_path)
    with c:
        assert c.get("/v3/health").status_code == 401
        r = c.get("/v3/health", headers=HEADERS)
        assert r.status_code == 200
        body = r.json()
        assert body["pv"] == 1 and body["capabilities"]["stream_transport"] == "websocket"
        assert body["capabilities"]["supported_provider"] == "claude_code"


def test_health_ok_on_version_mismatch_but_project_409(tmp_path):
    c, _ = _client(tmp_path)
    with c:
        h = c.get("/v3/health", headers={**HEADERS, "Archon-Protocol-Version": "2"})
        assert h.status_code == 200  # so the client can read pv
        p = c.get("/v3/project", headers={**HEADERS, "Archon-Protocol-Version": "2"})
        assert p.status_code == 409 and p.json()["error"]["code"] == "incompatible_version"


def test_error_envelope_shape(tmp_path):
    c, _ = _client(tmp_path)
    with c:
        r = c.get("/v3/kanban/cards/missing", headers=HEADERS)
        assert r.status_code == 404
        err = r.json()["error"]
        assert set(err) == {"code", "message", "retriable", "details"}
        assert err["code"] == "not_found" and err["retriable"] is False


def test_project_binding(tmp_path):
    c, proj = _client(tmp_path)
    with c:
        r = c.get("/v3/project", headers=HEADERS).json()
        import os
        assert r["path"] == os.path.realpath(str(proj))
        assert r["provider"] == "claude_code"
        assert "state_dir" in r
        # No project-selection endpoint exists (single-project, Q3).
        assert c.post("/v3/project", headers=HEADERS).status_code in (404, 405)


# -- sessions --------------------------------------------------------------
def test_session_lifecycle_http(tmp_path):
    c, _ = _client(tmp_path)
    with c:
        sp = c.post("/v3/sessions", headers=HEADERS, json={"request_id": "r1", "prompt": "go"})
        assert sp.status_code == 201
        sid = sp.json()["session"]["session_id"]
        assert c.post("/v3/sessions", headers=HEADERS, json={"request_id": "r1", "prompt": "go"}).json()["session"]["session_id"] == sid
        for _ in range(80):
            d = c.get(f"/v3/sessions/{sid}", headers=HEADERS).json()["session"]
            if d["state"] in ("completed", "failed", "killed"):
                break
            time.sleep(0.05)
        assert d["state"] == "completed"
        lst = c.get("/v3/sessions", headers=HEADERS).json()
        assert lst["ceiling"] == 8 and "cap" in lst
        assert c.get("/v3/sessions/NOPE", headers=HEADERS).status_code == 404


# -- kanban ----------------------------------------------------------------
def test_kanban_http_flow(tmp_path):
    c, _ = _client(tmp_path)
    with c:
        r = c.post("/v3/kanban/cards", headers=HEADERS, json={"title": "A", "column": "queued"})
        assert r.status_code == 201
        card = r.json()["card"]
        mv = c.post(f"/v3/kanban/cards/{card['card_id']}/move", headers=HEADERS,
                    json={"base_revision": card["revision"], "to_column": "done", "to_ordinal": 0})
        assert mv.status_code == 200
        rev = mv.json()["card"]["revision"]
        il = c.post(f"/v3/kanban/cards/{card['card_id']}/move", headers=HEADERS,
                    json={"base_revision": rev, "to_column": "in_progress"})
        assert il.status_code == 409 and il.json()["error"]["code"] == "illegal_transition"
        dl = c.request("DELETE", f"/v3/kanban/cards/{card['card_id']}", headers=HEADERS,
                       json={"base_revision": rev})
        assert dl.status_code == 200 and dl.json()["deleted"] is True


# -- memory ----------------------------------------------------------------
def test_memory_http_writeguard(tmp_path):
    c, proj = _client(tmp_path)
    with c:
        (proj / "CLAUDE.md").write_text("# seed\n")
        forb = c.put("/v3/memory/file", headers=HEADERS,
                     json={"scope_dir": str(proj), "filename": "CLAUDE.md", "content": "# x", "initiator": "conductor"})
        assert forb.status_code == 403 and forb.json()["error"]["code"] == "conductor_write_forbidden"
        rd = c.get("/v3/memory/file", headers=HEADERS, params={"scope_dir": str(proj), "filename": "CLAUDE.md"}).json()
        w = c.put("/v3/memory/file", headers=HEADERS,
                  json={"scope_dir": str(proj), "filename": "CLAUDE.md", "content": "# new\n",
                        "base_checksum": rd["file"]["checksum"], "initiator": "user"})
        assert w.status_code == 200
        esc = c.put("/v3/memory/file", headers=HEADERS,
                    json={"scope_dir": str(proj), "filename": "../x", "content": "y", "initiator": "user"})
        assert esc.status_code == 400 and esc.json()["error"]["code"] == "path_escape"


# -- conductor -------------------------------------------------------------
def test_conductor_http_flow(tmp_path):
    c, proj = _client(tmp_path)
    with c:
        msg = c.post("/v3/conductor/message", headers=HEADERS,
                     json={"text": "Refactor", "source": "voice_transcript", "context": {"active_dir": str(proj), "cap": 2}})
        assert msg.status_code == 200
        pid = msg.json()["plan"]["plan_id"]
        cf = c.post(f"/v3/conductor/plans/{pid}/confirm", headers=HEADERS, json={"cap": 2})
        assert cf.status_code == 200 and cf.json()["status"] in ("executing", "partial")
        cn = c.post(f"/v3/conductor/plans/{pid}/cancel", headers=HEADERS)
        assert cn.status_code == 200 and cn.json()["status"] == "cancelled"


# -- events + websocket ----------------------------------------------------
def test_events_rest(tmp_path):
    c, _ = _client(tmp_path)
    with c:
        c.post("/v3/kanban/cards", headers=HEADERS, json={"title": "A"})
        ev = c.get("/v3/events", headers=HEADERS, params={"after_seq": 0, "limit": 50}).json()
        assert "events" in ev and ev["truncated"] is False
        assert any(e["type"] == "kanban_updated" for e in ev["events"])


def test_ws_bad_token_closed(tmp_path):
    c, _ = _client(tmp_path)
    with c:
        with pytest.raises(Exception):
            with c.websocket_connect("/v3/stream") as ws:
                ws.receive_json()


def test_ws_hello_ping_and_live_event(tmp_path):
    c, _ = _client(tmp_path)
    with c:
        with c.websocket_connect(f"/v3/stream?token={TOKEN}") as ws:
            hello = ws.receive_json()
            assert hello["type"] == "hello" and hello["payload"]["pv"] == 1
            ws.send_json({"type": "ping", "id": "p1"})
            hb = ws.receive_json()
            assert hb["type"] == "heartbeat" and hb["payload"]["pong"] == "p1"
            # subscribe to kanban only, then produce a kanban event.
            ws.send_json({"type": "subscribe", "topics": ["kanban"]})
            c.post("/v3/kanban/cards", headers=HEADERS, json={"title": "WS"})
            saw = False
            for _ in range(20):
                m = ws.receive_json()
                if m["type"] == "kanban_updated":
                    saw = True
                    break
            assert saw


def test_ws_resume_after_seq(tmp_path):
    c, _ = _client(tmp_path)
    with c:
        # Generate some events first.
        for _ in range(3):
            c.post("/v3/kanban/cards", headers=HEADERS, json={"title": "x"})
        with c.websocket_connect(f"/v3/stream?token={TOKEN}") as ws:
            hello = ws.receive_json()
            assert hello["type"] == "hello"
            ws.send_json({"type": "resume", "after_seq": 0})
            # First replayed event has seq 1.
            m = ws.receive_json()
            assert m["seq"] == 1


def test_ws_origin_guard(tmp_path):
    c, _ = _client(tmp_path)
    with c:
        with pytest.raises(Exception):
            with c.websocket_connect(f"/v3/stream?token={TOKEN}", headers={"origin": "http://evil.example"}) as ws:
                ws.receive_json()
