"""Tests for the dynamic agent roster (task-derived workers, no fixed roles)."""

from __future__ import annotations

from orchestrator.dynamic_agents import (
    AgentSpec,
    build_adhoc_agents_json,
    derive_agents,
    route_to_agent,
)
from orchestrator.execution import Effort, ModelTier, TaskKind

POOL = [
    "swiftui-crafter",
    "react-crafter",
    "html-stylist",
    "design-system",
    "web-ui-designer",
    "swift-architect",
    "node-architect",
    "python-architect",
    "database-expert",
    "ml-engineer",
    "test-genius",
    "tech-writer",
    "marketing-strategist",
    "product-thinker",
    "monetization-expert",
    "claude-code-toolsmith",
    "prompt-craftsman",
    "cli-ux-master",
]


class TestDeriveAgents:
    def test_opaque_ids_no_fixed_roles(self) -> None:
        roster = derive_agents(
            "Build an iOS habit tracker UI with a backend API", available_subagents=POOL
        )
        ids = [a.id for a in roster]
        assert ids == [f"w{i}" for i in range(1, len(roster) + 1)]
        # No worker carries a fixed personality name.
        for a in roster:
            assert "craftsman" not in a.focus.lower()
            assert "skeptic" not in a.focus.lower()

    def test_roster_flexes_with_goal_ui(self) -> None:
        roster = derive_agents("Design a beautiful SwiftUI interface", available_subagents=POOL)
        lanes = {a.lane for a in roster}
        assert "ui" in lanes
        assert "code" in lanes  # always present

    def test_roster_includes_qa_by_default(self) -> None:
        roster = derive_agents("Implement an API", available_subagents=POOL)
        assert "qa" in {a.lane for a in roster}

    def test_qa_excluded_when_testing_disabled(self) -> None:
        roster = derive_agents("Implement an API", available_subagents=POOL, include_testing=False)
        assert "qa" not in {a.lane for a in roster}

    def test_max_agents_cap(self) -> None:
        roster = derive_agents(
            "ui ux backend database docs strategy pricing testing architecture",
            available_subagents=POOL,
            max_agents=3,
        )
        assert len(roster) == 3

    def test_small_cap_keeps_code_and_qa_backbone(self) -> None:
        # Regression: with a tiny roster and an arch+ui goal, the forced code/qa
        # backbone must survive the cap (not be sliced out by priority order).
        roster = derive_agents(
            "Build the system architecture and the UI", available_subagents=POOL, max_agents=2
        )
        lanes = {a.lane for a in roster}
        assert len(roster) == 2
        assert "code" in lanes and "qa" in lanes

    def test_cap_one_keeps_code(self) -> None:
        roster = derive_agents(
            "Build the architecture and UI", available_subagents=POOL, max_agents=1
        )
        assert len(roster) == 1
        assert roster[0].lane == "code"  # implementation backbone wins the single slot

    def test_subagents_selected_by_affinity(self) -> None:
        roster = derive_agents("Build a SwiftUI UI", available_subagents=POOL)
        ui = next(a for a in roster if a.lane == "ui")
        assert any("crafter" in s or "stylist" in s or "design" in s for s in ui.subagents)

    def test_tiering_applies_profiles(self) -> None:
        roster = derive_agents("Refactor architecture and write docs", available_subagents=POOL)
        arch = next((a for a in roster if a.lane == "architecture"), None)
        assert arch is not None
        assert arch.profile.model_tier is ModelTier.DEEP
        assert arch.profile.effort is Effort.XHIGH

    def test_tiering_off_inherits(self) -> None:
        roster = derive_agents("Refactor architecture", available_subagents=POOL, tiering=False)
        arch = next(a for a in roster if a.lane == "architecture")
        assert arch.profile.model_tier is ModelTier.INHERIT

    def test_pathological_goal_still_yields_worker(self) -> None:
        roster = derive_agents("xyzzy", available_subagents=POOL, include_testing=False)
        assert len(roster) >= 1

    def test_to_dict_has_badge(self) -> None:
        roster = derive_agents("Build architecture", available_subagents=POOL)
        d = roster[0].to_dict()
        assert "mode_badge" in d and "id" in d and "focus" in d


class TestSystemPrompt:
    def test_role_free_persona(self) -> None:
        spec = AgentSpec(id="w1", lane="ui", kind=TaskKind.UI, focus="interface design")
        prompt = spec.system_prompt()
        assert "worker w1" in prompt
        assert "no fixed role" in prompt
        assert "interface design" in prompt


class TestRouting:
    def test_routes_by_keyword(self) -> None:
        roster = derive_agents("Build UI and backend architecture", available_subagents=POOL)
        target = route_to_agent("Add a database migration and schema change", roster)
        spec = next(a for a in roster if a.id == target)
        assert spec.lane in ("architecture", "code")

    def test_fallback_when_no_match(self) -> None:
        roster = derive_agents("Build an API", available_subagents=POOL)
        target = route_to_agent("zzz qqq nothing matches", roster)
        assert target in {a.id for a in roster}


class TestConfigToleratesDynamicIds:
    def test_unknown_id_synthesizes_generic_config(self) -> None:
        from orchestrator.config import Config

        cfg = Config()
        c = cfg.get_terminal_config("w7")  # not in the fixed roster
        assert c.role == "dynamic"
        assert c.id == "w7"
        # runtime profile must not raise on a dynamic id
        rp = cfg.get_terminal_runtime_profile("w7")
        assert rp["specialization"]

    def test_legacy_id_still_resolves(self) -> None:
        from orchestrator.config import Config

        assert Config().get_terminal_config("t1").role == "UI/UX"


class TestAdhocAgentsJson:
    def test_build_adhoc(self) -> None:
        j = build_adhoc_agents_json(
            [
                {"name": "auditor", "description": "audits", "prompt": "You audit."},
            ]
        )
        assert j == {"auditor": {"description": "audits", "prompt": "You audit."}}
