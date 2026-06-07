"""Tests for the multi-session dashboard features (F1, F1a, F3, F9, F12, F13, F14).

Covers the new endpoints added to ``orchestrator.dashboard``:

* ``GET  /api/sessions``            — registry listing (empty + populated).
* ``GET  /api/dirs``                — sandboxed directory picker.
* ``GET  /api/preview-roster``      — pure pre-run roster derivation.
* ``POST /api/runs``                — mints a session, spawns (mocked), registers.
* ``GET  /api/metrics``             — metrics block shape on an empty session.
* ``GET  /api/files``               — file-event provenance shape.
* ``GET  /api/workspace-graph``     — graph shape.

These use ``fastapi.testclient.TestClient`` against the live ``app``. To isolate
the filesystem, each test points the module-level ``config`` at a temp base dir
and clears the per-session resolution caches so ``resolve_config`` re-derives
paths under the temp tree.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from orchestrator import dashboard, sessions
from orchestrator.config import Config


@pytest.fixture
def temp_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point the dashboard's module-level config at a temp base dir.

    Resets the per-session config/control caches and the shared WS-state cache so
    nothing leaks between tests, then restores the originals on teardown.
    """
    temp_config = Config(base_dir=tmp_path, orchestra_dir=tmp_path / ".orchestra")
    temp_config.ensure_dirs()

    original_config = dashboard.config
    original_control = dashboard.control
    monkeypatch.setattr(dashboard, "config", temp_config)
    monkeypatch.setattr(dashboard, "control", dashboard.ControlChannel(temp_config.orchestra_dir))

    dashboard._config_cache.clear()
    dashboard._control_cache.clear()
    dashboard._shared_state.clear()

    yield tmp_path

    dashboard._config_cache.clear()
    dashboard._control_cache.clear()
    dashboard._shared_state.clear()
    dashboard.config = original_config
    dashboard.control = original_control


@pytest.fixture
def client(temp_base: Path) -> Iterator[TestClient]:  # noqa: ARG001 - activates temp_base
    """A TestClient bound to the app with the temp base dir active."""
    with TestClient(dashboard.app) as c:
        yield c


# ---------------------------------------------------------------------------
# GET /api/sessions
# ---------------------------------------------------------------------------
class TestSessionsEndpoint:
    def test_empty_registry_returns_empty_list(self, client: TestClient) -> None:
        resp = client.get("/api/sessions")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_after_register_lists_session(self, client: TestClient, temp_base: Path) -> None:
        sessions.register_session(
            temp_base,
            {"session_id": "20260606-101010-demo", "goal": "demo goal", "status": "running"},
        )
        resp = client.get("/api/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["session_id"] == "20260606-101010-demo"
        assert data[0]["goal"] == "demo goal"

    def test_single_session_lookup(self, client: TestClient, temp_base: Path) -> None:
        sessions.register_session(
            temp_base,
            {"session_id": "20260606-101010-demo", "goal": "demo", "status": "running"},
        )
        resp = client.get("/api/sessions/20260606-101010-demo")
        assert resp.status_code == 200
        assert resp.json()["session_id"] == "20260606-101010-demo"

    def test_missing_session_returns_404(self, client: TestClient) -> None:
        resp = client.get("/api/sessions/does-not-exist")
        assert resp.status_code == 404

    def test_traversal_session_id_returns_404(self, client: TestClient) -> None:
        resp = client.get("/api/sessions/..%2f..%2fetc")
        assert resp.status_code in (404, 422)


# ---------------------------------------------------------------------------
# GET /api/dirs (sandboxed)
# ---------------------------------------------------------------------------
class TestDirsEndpoint:
    def test_default_lists_home(self, client: TestClient) -> None:
        resp = client.get("/api/dirs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["path"] == str(Path.home().resolve())
        assert data["parent"] is None  # at the sandbox root
        assert isinstance(data["dirs"], list)

    def test_traversal_etc_is_clamped_to_home(self, client: TestClient) -> None:
        resp = client.get("/api/dirs", params={"path": "/etc"})
        assert resp.status_code == 200
        data = resp.json()
        # Never escapes the home sandbox.
        assert data["path"] == str(Path.home().resolve())

    def test_dotdot_traversal_is_clamped(self, client: TestClient) -> None:
        resp = client.get("/api/dirs", params={"path": "../.."})
        assert resp.status_code == 200
        data = resp.json()
        home = str(Path.home().resolve())
        # Resolved path stays within (or at) the home root.
        assert data["path"] == home or data["path"].startswith(home)

    def test_lists_a_real_subdir(self, client: TestClient) -> None:
        # Create a real child directory under home and confirm it shows up.
        home = Path.home().resolve()
        child = home / ".archon_test_dir_picker"
        child.mkdir(exist_ok=True)
        try:
            resp = client.get("/api/dirs", params={"path": str(home)})
            assert resp.status_code == 200
            names = [d["name"] for d in resp.json()["dirs"]]
            # Hidden dirs (leading dot) are intentionally skipped, so this dotted
            # name should NOT appear; create a non-hidden one to assert listing.
            assert ".archon_test_dir_picker" not in names
        finally:
            child.rmdir()

        visible = home / "archon_test_visible_dir"
        visible.mkdir(exist_ok=True)
        try:
            resp = client.get("/api/dirs", params={"path": str(home)})
            names = [d["name"] for d in resp.json()["dirs"]]
            assert "archon_test_visible_dir" in names
        finally:
            visible.rmdir()


# ---------------------------------------------------------------------------
# GET /api/preview-roster
# ---------------------------------------------------------------------------
class TestPreviewRoster:
    def test_returns_nonempty_roster(self, client: TestClient) -> None:
        resp = client.get(
            "/api/preview-roster",
            params={"goal": "Build a SwiftUI app with a REST backend and tests"},
        )
        assert resp.status_code == 200
        roster = resp.json()
        assert isinstance(roster, list)
        assert len(roster) >= 1
        first = roster[0]
        # AgentSpec.to_dict shape.
        for key in ("id", "lane", "kind", "focus", "subagents", "profile"):
            assert key in first

    def test_agent_count_caps_roster(self, client: TestClient) -> None:
        resp = client.get(
            "/api/preview-roster",
            params={"goal": "ui backend docs strategy testing", "agent_count": 2},
        )
        assert resp.status_code == 200
        assert len(resp.json()) <= 2

    def test_empty_goal_does_not_500(self, client: TestClient) -> None:
        resp = client.get("/api/preview-roster", params={"goal": ""})
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


# ---------------------------------------------------------------------------
# POST /api/runs (subprocess.Popen monkeypatched — no real process spawns)
# ---------------------------------------------------------------------------
class _FakeProc:
    def __init__(self) -> None:
        self.pid = 424242


class TestCreateRun:
    def test_mints_session_and_spawns(
        self, client: TestClient, temp_base: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: dict[str, object] = {}

        def fake_popen(cmd, **kwargs):  # type: ignore[no-untyped-def]
            calls["cmd"] = cmd
            calls["kwargs"] = kwargs
            return _FakeProc()

        monkeypatch.setattr(dashboard.subprocess, "Popen", fake_popen)

        resp = client.post(
            "/api/runs",
            json={
                "goal": "Create a habit tracker app",
                "dynamic_agents": True,
                "model_tiering": True,
                "effort_dial": False,
                "no_testing": True,
                "agent_count": 3,
                "instructions": "Use MVVM and write tests.",
                "roster_overrides": {"w1": {"effort": "high"}},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "starting"
        assert data["pid"] == 424242
        sid = data["session_id"]
        assert sid

        # Popen was called with the expected command + env (NO real process).
        cmd = calls["cmd"]
        assert cmd[0] == dashboard.sys.executable
        assert cmd[1:3] == ["-m", "orchestrator"]
        assert "Create a habit tracker app" in cmd
        assert "--session-id" in cmd and sid in cmd
        assert "--dynamic-agents" in cmd
        assert "--model-tiering" in cmd
        assert "--no-effort-dial" in cmd
        assert "--no-testing" in cmd
        assert "--agent-count" in cmd and "3" in cmd
        kwargs = calls["kwargs"]
        assert kwargs["start_new_session"] is True
        assert kwargs["env"]["ARCHON_SESSION_ID"] == sid

        # Session was registered.
        listing = client.get("/api/sessions").json()
        assert any(entry["session_id"] == sid for entry in listing)
        assert listing[0]["pid"] == 424242

        # Session dir pre-created with overrides + instructions persisted.
        session_path = sessions.session_dir(temp_base, sid)
        assert session_path.is_dir()
        overrides = json.loads((session_path / "roster_overrides.json").read_text())
        assert overrides == {"w1": {"effort": "high"}}
        assert (session_path / "instructions.txt").read_text() == "Use MVVM and write tests."

    def test_missing_goal_returns_400(self, client: TestClient) -> None:
        resp = client.post("/api/runs", json={})
        assert resp.status_code == 400

    def test_invalid_agent_count_returns_400(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(dashboard.subprocess, "Popen", lambda *_a, **_k: _FakeProc())
        resp = client.post("/api/runs", json={"goal": "x", "agent_count": -1})
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/metrics, /api/files, /api/workspace-graph on an empty session
# ---------------------------------------------------------------------------
class TestEmptySessionShapes:
    def test_metrics_shape(self, client: TestClient) -> None:
        resp = client.get("/api/metrics")
        assert resp.status_code == 200
        data = resp.json()
        for key in (
            "completion_pct",
            "in_progress",
            "pending",
            "completed",
            "failed",
            "throughput_per_min",
            "elapsed_sec",
            "per_worker",
        ):
            assert key in data
        assert isinstance(data["per_worker"], dict)

    def test_files_shape(self, client: TestClient) -> None:
        resp = client.get("/api/files")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_workspace_graph_shape(self, client: TestClient) -> None:
        resp = client.get("/api/workspace-graph")
        assert resp.status_code == 200
        data = resp.json()
        assert data == {"nodes": [], "edges": []}

    def test_metrics_for_explicit_session(self, client: TestClient, temp_base: Path) -> None:
        sessions.register_session(
            temp_base,
            {"session_id": "20260606-120000-mx", "goal": "metrics", "status": "running"},
        )
        resp = client.get("/api/metrics", params={"session": "20260606-120000-mx"})
        assert resp.status_code == 200
        assert "completion_pct" in resp.json()


# ---------------------------------------------------------------------------
# Session-scoped read endpoints fall back cleanly for unknown sessions
# ---------------------------------------------------------------------------
class TestSessionScopedReads:
    def test_status_with_unknown_session_is_idle(self, client: TestClient) -> None:
        resp = client.get("/api/status", params={"session": "20260101-000000-ghost"})
        assert resp.status_code == 200
        assert resp.json()["state"] in ("idle", "error")

    def test_terminal_prompt_empty(self, client: TestClient) -> None:
        resp = client.get("/api/terminal-prompt/w1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["worker_id"] == "w1"
        assert data["prompts"] == []

    def test_chat_replies_empty(self, client: TestClient) -> None:
        resp = client.get("/api/chat/replies", params={"chat_session_id": "abc"})
        assert resp.status_code == 200
        assert resp.json()["replies"] == []

    def test_control_spawn_requires_focus_or_lane(self, client: TestClient) -> None:
        resp = client.post("/api/control/spawn", json={})
        assert resp.status_code == 400

    def test_control_chat_requires_text(self, client: TestClient) -> None:
        resp = client.post("/api/control/chat", json={"chat_session_id": "x"})
        assert resp.status_code == 400
