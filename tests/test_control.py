"""Tests for the dashboard -> orchestrator control plane (file-based command bus)."""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.config import Config
from orchestrator.control import ControlChannel
from orchestrator.orchestrator import Orchestrator


class TestControlChannel:
    def test_submit_then_drain(self, tmp_path: Path) -> None:
        ch = ControlChannel(tmp_path)
        ch.submit({"type": "pause"})
        ch.submit({"type": "resume"})
        assert ch.drain() == [{"type": "pause"}, {"type": "resume"}]

    def test_drain_is_once(self, tmp_path: Path) -> None:
        ch = ControlChannel(tmp_path)
        ch.submit({"type": "pause"})
        assert ch.drain() == [{"type": "pause"}]
        assert ch.drain() == []  # already consumed

    def test_offset_persists_across_instances(self, tmp_path: Path) -> None:
        ch = ControlChannel(tmp_path)
        ch.submit({"type": "a"})
        ch.drain()
        ch.submit({"type": "b"})
        # A fresh reader (e.g. orchestrator restart) sees only the unread command.
        ch2 = ControlChannel(tmp_path)
        assert ch2.drain() == [{"type": "b"}]

    def test_reset_clears_and_restarts(self, tmp_path: Path) -> None:
        ch = ControlChannel(tmp_path)
        ch.submit({"type": "a"})
        ch.drain()
        ch.reset()
        ch.submit({"type": "fresh"})
        assert ch.drain() == [{"type": "fresh"}]

    def test_malformed_lines_skipped(self, tmp_path: Path) -> None:
        ch = ControlChannel(tmp_path)
        ch._ensure()
        ch.commands_file.write_text('not json\n{"type":"ok"}\n{"no":"type"}\n')
        assert ch.drain() == [{"type": "ok"}]

    def test_drain_empty_when_no_file(self, tmp_path: Path) -> None:
        assert ControlChannel(tmp_path).drain() == []

    def test_external_shrink_reprocesses_from_start(self, tmp_path: Path) -> None:
        # Regression: if the commands file is externally truncated/cleared below the
        # stored offset, drain must restart from the beginning (not silently drop).
        ch = ControlChannel(tmp_path)
        ch.submit({"type": "a"})
        ch.submit({"type": "b"})
        ch.drain()  # offset now past 'a','b'
        # External truncate to a smaller file (NOT via reset, which would also zero offset).
        ch.commands_file.write_text('{"type":"c"}\n')
        assert ch.drain() == [{"type": "c"}]


class TestProfileDictMapping:
    def test_build_profile_dict(self) -> None:
        from orchestrator.dashboard import _build_profile_dict

        assert _build_profile_dict({}) is None
        assert _build_profile_dict({"effort": "max"}) == {"effort": "max"}
        assert _build_profile_dict({"plan": True})["permission_mode"] == "plan"
        d = _build_profile_dict({"model_tier": "deep", "effort": "xhigh"})
        assert d == {"model_tier": "deep", "effort": "xhigh"}
        # 'inherit' is conveyed by simply omitting the key upstream; if passed empty
        # values they are dropped.
        assert _build_profile_dict({"effort": "", "model_tier": ""}) is None


class TestWebsocketStateHash:
    def test_hash_ignores_timestamps(self) -> None:
        # Regression: the WS change-detection hash must NOT change just because the
        # wall-clock timestamps changed, otherwise every tick re-sends the full payload.
        from orchestrator.dashboard import _state_hash

        a = {
            "timestamp": "2026-06-06T10:00:00.111",
            "status": {"timestamp": "2026-06-06T10:00:00.111", "state": "running"},
            "tasks": {"pending_count": 3},
        }
        b = {
            "timestamp": "2026-06-06T10:00:02.999",
            "status": {"timestamp": "2026-06-06T10:00:02.999", "state": "running"},
            "tasks": {"pending_count": 3},
        }
        assert _state_hash(a) == _state_hash(b)

    def test_hash_changes_on_real_change(self) -> None:
        from orchestrator.dashboard import _state_hash

        a = {"timestamp": "t1", "status": {"state": "running"}, "tasks": {"pending_count": 3}}
        b = {"timestamp": "t1", "status": {"state": "running"}, "tasks": {"pending_count": 2}}
        assert _state_hash(a) != _state_hash(b)


def _make_orchestrator(tmp_path: Path) -> Orchestrator:
    cfg = Config(
        base_dir=tmp_path,
        orchestra_dir=tmp_path / ".orchestra",
        apps_dir=tmp_path / "Apps",
    )
    cfg.ensure_dirs()
    orch = Orchestrator(config=cfg, verbose=False, use_colors=False, use_progress_bar=False)
    return orch


class TestOrchestratorControlApplication:
    @pytest.mark.asyncio
    async def test_set_config_toggles(self, tmp_path: Path) -> None:
        orch = _make_orchestrator(tmp_path)
        assert orch.config.model_tiering is False
        orch.control.submit({"type": "set_config", "model_tiering": True, "dynamic_agents": True})
        await orch._apply_control_commands()
        assert orch.config.model_tiering is True
        assert orch.config.dynamic_agents is True

    @pytest.mark.asyncio
    async def test_set_mode_stores_override(self, tmp_path: Path) -> None:
        orch = _make_orchestrator(tmp_path)
        orch.control.submit(
            {"type": "set_mode", "target": "t2", "profile": {"effort": "max", "model_tier": "deep"}}
        )
        await orch._apply_control_commands()
        assert orch._mode_overrides["t2"] == {"effort": "max", "model_tier": "deep"}
        # And it flows into the per-task profile for that worker.
        from orchestrator.task_queue import Task

        task = Task(id="x", title="t", description="d")
        profile = orch._build_task_profile(task, "t2")
        assert profile.effort.value == "max"

    @pytest.mark.asyncio
    async def test_inject_adds_task(self, tmp_path: Path) -> None:
        orch = _make_orchestrator(tmp_path)
        orch.control.submit(
            {"type": "inject", "title": "Add login screen", "description": "ui work"}
        )
        await orch._apply_control_commands()
        pending = orch.task_queue.pending
        assert any(t.title == "Add login screen" for t in pending)

    @pytest.mark.asyncio
    async def test_inject_with_profile_override(self, tmp_path: Path) -> None:
        orch = _make_orchestrator(tmp_path)
        orch.control.submit(
            {
                "type": "inject",
                "title": "Critical refactor",
                "description": "architecture",
                "target": "t2",
                "profile": {"effort": "max", "permission_mode": "plan"},
            }
        )
        await orch._apply_control_commands()
        task = next(t for t in orch.task_queue.pending if t.title == "Critical refactor")
        assert task.metadata.get("profile", {}).get("effort") == "max"
        profile = orch._build_task_profile(task, "t2")
        assert profile.permission_mode.value == "plan"

    @pytest.mark.asyncio
    async def test_set_mode_clear_removes_override(self, tmp_path: Path) -> None:
        orch = _make_orchestrator(tmp_path)
        orch.control.submit({"type": "set_mode", "target": "t2", "profile": {"effort": "max"}})
        await orch._apply_control_commands()
        assert "t2" in orch._mode_overrides
        orch.control.submit({"type": "set_mode", "target": "t2", "clear": True})
        await orch._apply_control_commands()
        assert "t2" not in orch._mode_overrides  # override cleared, back to lane/auto

    @pytest.mark.asyncio
    async def test_set_mode_non_dict_profile_ignored(self, tmp_path: Path) -> None:
        # A malformed non-dict profile must not be stored (and must not later crash).
        orch = _make_orchestrator(tmp_path)
        orch.control.submit({"type": "set_mode", "target": "t2", "profile": "plan"})
        await orch._apply_control_commands()
        assert "t2" not in orch._mode_overrides

    @pytest.mark.asyncio
    async def test_pause_resume(self, tmp_path: Path) -> None:
        orch = _make_orchestrator(tmp_path)
        assert orch._paused.is_set()  # not paused initially
        orch.control.submit({"type": "pause"})
        await orch._apply_control_commands()
        assert not orch._paused.is_set()
        orch.control.submit({"type": "resume"})
        await orch._apply_control_commands()
        assert orch._paused.is_set()

    @pytest.mark.asyncio
    async def test_bad_command_does_not_crash(self, tmp_path: Path) -> None:
        orch = _make_orchestrator(tmp_path)
        orch.control.submit({"type": "set_mode"})  # missing target/profile
        orch.control.submit({"type": "unknown_type"})
        await orch._apply_control_commands()  # must not raise
