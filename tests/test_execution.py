"""Tests for the per-task ExecutionProfile system and CLI command composition."""

from __future__ import annotations

from orchestrator.config import Config
from orchestrator.execution import (
    Effort,
    ExecutionProfile,
    ModelTier,
    PermissionMode,
    TaskKind,
    agents_json_str,
    classify_task,
    profile_for_kind,
    utility_profile,
)


class TestExecutionProfile:
    def test_empty_profile_inherits(self) -> None:
        p = ExecutionProfile()
        assert p.model_tier is ModelTier.INHERIT
        assert p.effort is Effort.INHERIT
        assert p.resolved_model() is None
        assert p.resolved_model("opus") == "opus"

    def test_resolved_model_tier(self) -> None:
        assert ExecutionProfile(model_tier=ModelTier.CHEAP).resolved_model() == "haiku"
        assert ExecutionProfile(model_tier=ModelTier.STANDARD).resolved_model() == "sonnet"
        assert ExecutionProfile(model_tier=ModelTier.DEEP).resolved_model() == "opus"

    def test_model_override_wins_over_tier(self) -> None:
        p = ExecutionProfile(model_tier=ModelTier.CHEAP, model_override="claude-opus-4-8")
        assert p.resolved_model() == "claude-opus-4-8"

    def test_roundtrip_serialization(self) -> None:
        p = ExecutionProfile(
            model_tier=ModelTier.DEEP,
            effort=Effort.MAX,
            permission_mode=PermissionMode.PLAN,
            agents={"reviewer": {"description": "x", "prompt": "y"}},
            allowed_tools=["Edit", "Bash"],
            bare=True,
            max_turns=12,
        )
        restored = ExecutionProfile.from_dict(p.to_dict())
        assert restored == p

    def test_from_dict_tolerates_garbage(self) -> None:
        p = ExecutionProfile.from_dict({"model_tier": "nonsense", "effort": None})
        assert p.model_tier is ModelTier.INHERIT
        assert p.effort is Effort.INHERIT

    def test_from_dict_none(self) -> None:
        assert ExecutionProfile.from_dict(None) == ExecutionProfile()

    def test_from_dict_non_dict_is_safe(self) -> None:
        # Control channel may deliver a non-dict 'profile' (e.g. a string); from_dict
        # must not raise AttributeError — it should fall back to a default profile.
        assert ExecutionProfile.from_dict("plan") == ExecutionProfile()
        assert ExecutionProfile.from_dict(["x"]) == ExecutionProfile()
        assert ExecutionProfile.from_dict(5) == ExecutionProfile()

    def test_merged_is_immutable(self) -> None:
        p = ExecutionProfile(effort=Effort.LOW)
        q = p.merged(effort=Effort.MAX)
        assert p.effort is Effort.LOW  # original unchanged
        assert q.effort is Effort.MAX

    def test_badge(self) -> None:
        p = ExecutionProfile(
            model_tier=ModelTier.DEEP,
            effort=Effort.MAX,
            permission_mode=PermissionMode.PLAN,
            agents={"a": {}, "b": {}},
        )
        badge = p.badge()
        assert "deep" in badge and "max" in badge and "plan" in badge and "2 agents" in badge
        assert ExecutionProfile().badge() == "default"


class TestClassification:
    def test_classify_ui(self) -> None:
        assert classify_task("Build the login UI screen", "swiftui view") is TaskKind.UI

    def test_classify_docs(self) -> None:
        assert classify_task("Write the README documentation guide") is TaskKind.DOCS

    def test_classify_architecture(self) -> None:
        assert classify_task("Refactor the database schema and migration") is TaskKind.ARCHITECTURE

    def test_classify_qa(self) -> None:
        assert classify_task("Add unit tests and verify coverage") is TaskKind.QA

    def test_classify_generic_fallback(self) -> None:
        assert classify_task("zzz qqq") is TaskKind.GENERIC


class TestProfilePolicy:
    def test_tiering_assigns_cheap_to_docs(self) -> None:
        p = profile_for_kind(TaskKind.DOCS)
        assert p.model_tier is ModelTier.CHEAP
        assert p.effort is Effort.LOW

    def test_tiering_assigns_deep_to_architecture(self) -> None:
        p = profile_for_kind(TaskKind.ARCHITECTURE)
        assert p.model_tier is ModelTier.DEEP
        assert p.effort is Effort.XHIGH

    def test_tiering_disabled_inherits(self) -> None:
        p = profile_for_kind(TaskKind.ARCHITECTURE, tiering=False)
        assert p.model_tier is ModelTier.INHERIT
        assert p.effort is Effort.INHERIT

    def test_plan_first(self) -> None:
        p = profile_for_kind(TaskKind.CODE, plan_first=True)
        assert p.permission_mode is PermissionMode.PLAN

    def test_overrides(self) -> None:
        p = profile_for_kind(TaskKind.DOCS, max_turns=3)
        assert p.max_turns == 3

    def test_utility_profile_is_cheap_and_oauth_safe(self) -> None:
        # bare MUST be False to preserve OAuth/subscription auth.
        p = utility_profile()
        assert p.model_tier is ModelTier.CHEAP
        assert p.bare is False
        assert p.cache_friendly is True


class TestAgentsJson:
    def test_none_when_empty(self) -> None:
        assert agents_json_str(ExecutionProfile()) is None

    def test_compact_json(self) -> None:
        p = ExecutionProfile(agents={"r": {"description": "d", "prompt": "p"}})
        s = agents_json_str(p)
        assert s is not None
        assert " " not in s  # compact separators
        assert '"r"' in s


class TestBuildLLMCommandLegacy:
    """The legacy (profile=None) path must be byte-for-byte unchanged."""

    def test_legacy_plain(self) -> None:
        cmd = Config().build_llm_command("hi")
        assert cmd == ["claude", "--print", "-p", "hi"]

    def test_legacy_unsafe(self) -> None:
        cmd = Config().build_llm_command("hi", allow_unsafe=True)
        assert cmd == ["claude", "--print", "--dangerously-skip-permissions", "-p", "hi"]

    def test_legacy_with_global_model(self) -> None:
        cmd = Config(llm_model="opus").build_llm_command("hi")
        assert cmd == ["claude", "--print", "--model", "opus", "-p", "hi"]


class TestBuildLLMCommandProfile:
    def test_model_tier_and_effort(self) -> None:
        p = ExecutionProfile(model_tier=ModelTier.DEEP, effort=Effort.MAX)
        cmd = Config().build_llm_command("hi", profile=p)
        assert "--model" in cmd and cmd[cmd.index("--model") + 1] == "opus"
        assert "--effort" in cmd and cmd[cmd.index("--effort") + 1] == "max"

    def test_bypass_adds_skip_permissions(self) -> None:
        p = ExecutionProfile(permission_mode=PermissionMode.BYPASS)
        cmd = Config().build_llm_command("hi", profile=p)
        assert "--dangerously-skip-permissions" in cmd
        assert "--permission-mode" not in cmd

    def test_plan_mode(self) -> None:
        p = ExecutionProfile(permission_mode=PermissionMode.PLAN)
        cmd = Config().build_llm_command("hi", profile=p)
        assert "--permission-mode" in cmd
        assert cmd[cmd.index("--permission-mode") + 1] == "plan"
        assert "--dangerously-skip-permissions" not in cmd

    def test_dynamic_agents(self) -> None:
        p = ExecutionProfile(agents={"rev": {"description": "d", "prompt": "p"}})
        cmd = Config().build_llm_command("hi", profile=p)
        assert "--agents" in cmd
        assert '"rev"' in cmd[cmd.index("--agents") + 1]

    def test_tools_and_dirs(self) -> None:
        p = ExecutionProfile(
            allowed_tools=["Edit", "Bash"],
            disallowed_tools=["WebFetch"],
            add_dirs=["/tmp/x"],
        )
        cmd = Config().build_llm_command("hi", profile=p)
        ai = cmd.index("--allowedTools")
        assert cmd[ai + 1 : ai + 3] == ["Edit", "Bash"]
        assert cmd[cmd.index("--disallowedTools") + 1] == "WebFetch"
        assert cmd[cmd.index("--add-dir") + 1] == "/tmp/x"

    def test_token_savers(self) -> None:
        p = ExecutionProfile(bare=True, cache_friendly=True, max_turns=5, fallback_model="sonnet")
        cmd = Config().build_llm_command("hi", profile=p)
        assert "--bare" in cmd
        assert "--exclude-dynamic-system-prompt-sections" in cmd
        assert cmd[cmd.index("--max-turns") + 1] == "5"
        assert cmd[cmd.index("--fallback-model") + 1] == "sonnet"

    def test_system_prompt_appended(self) -> None:
        cmd = Config().build_llm_command("task", system_prompt="persona")
        assert "--append-system-prompt" in cmd
        assert cmd[cmd.index("--append-system-prompt") + 1] == "persona"
        # task stays in -p
        assert cmd[cmd.index("-p") + 1] == "task"

    def test_system_prompt_and_profile_append_combined(self) -> None:
        p = ExecutionProfile(append_system_prompt="extra mode directive")
        cmd = Config().build_llm_command("task", profile=p, system_prompt="persona")
        val = cmd[cmd.index("--append-system-prompt") + 1]
        assert "persona" in val and "extra mode directive" in val

    def test_prompt_is_last(self) -> None:
        p = profile_for_kind(TaskKind.ARCHITECTURE)
        cmd = Config().build_llm_command("the task", profile=p, system_prompt="x")
        assert cmd[-2] == "-p"
        assert cmd[-1] == "the task"


class TestGateProfile:
    def test_tiering_off_drops_model_tier(self) -> None:
        cfg = Config(model_tiering=False, effort_dial=True)
        gated = cfg.gate_profile(ExecutionProfile(model_tier=ModelTier.DEEP, effort=Effort.MAX))
        assert gated.model_tier is ModelTier.INHERIT
        assert gated.effort is Effort.MAX  # effort kept

    def test_effort_dial_off_drops_effort(self) -> None:
        cfg = Config(model_tiering=True, effort_dial=False)
        gated = cfg.gate_profile(ExecutionProfile(model_tier=ModelTier.DEEP, effort=Effort.MAX))
        assert gated.effort is Effort.INHERIT
        assert gated.model_tier is ModelTier.DEEP  # model kept

    def test_both_on_keeps_both(self) -> None:
        cfg = Config(model_tiering=True, effort_dial=True)
        gated = cfg.gate_profile(ExecutionProfile(model_tier=ModelTier.CHEAP, effort=Effort.LOW))
        assert gated.model_tier is ModelTier.CHEAP and gated.effort is Effort.LOW

    def test_no_effort_dial_strips_effort_from_utility_profile(self) -> None:
        # Regression: --no-effort-dial must suppress --effort on utility calls too.
        cfg = Config(effort_dial=False, model_tiering=False)
        gated = cfg.gate_profile(utility_profile())
        cmd = cfg.build_llm_command("hi", profile=gated)
        assert "--effort" not in cmd


class TestBuildLLMCommandCodex:
    def test_codex_legacy(self) -> None:
        cfg = Config(llm_provider="codex", llm_command="codex")
        cmd = cfg.build_llm_command("hi", allow_unsafe=True)
        assert cmd[:2] == ["codex", "exec"]
        assert "--dangerously-bypass-approvals-and-sandbox" in cmd
        assert cmd[-1] == "hi"

    def test_codex_ignores_claude_tier_aliases(self) -> None:
        cfg = Config(llm_provider="codex", llm_command="codex")
        p = ExecutionProfile(model_tier=ModelTier.CHEAP)  # haiku alias is claude-only
        cmd = cfg.build_llm_command("hi", profile=p)
        # Should fall back to codex default model, never 'haiku'.
        assert "haiku" not in cmd
        assert cfg.codex_default_model in cmd

    def test_codex_honors_explicit_override(self) -> None:
        cfg = Config(llm_provider="codex", llm_command="codex")
        p = ExecutionProfile(model_override="gpt-5.3-codex-mini")
        cmd = cfg.build_llm_command("hi", profile=p)
        assert "gpt-5.3-codex-mini" in cmd

    def test_codex_plan_mode_does_not_bypass(self) -> None:
        cfg = Config(llm_provider="codex", llm_command="codex")
        p = ExecutionProfile(permission_mode=PermissionMode.PLAN)
        cmd = cfg.build_llm_command("hi", profile=p)
        assert "--dangerously-bypass-approvals-and-sandbox" not in cmd

    def test_codex_inlines_system_prompt(self) -> None:
        # Regression: codex has no --append-system-prompt, so the persona must be
        # inlined into the prompt body, not dropped.
        cfg = Config(llm_provider="codex", llm_command="codex")
        cmd = cfg.build_llm_command("do the task", system_prompt="You are worker w1.")
        assert "--append-system-prompt" not in cmd  # codex doesn't support it
        body = cmd[-1]
        assert "You are worker w1." in body and "do the task" in body

    def test_codex_inlines_profile_append_system_prompt(self) -> None:
        cfg = Config(llm_provider="codex", llm_command="codex")
        p = ExecutionProfile(append_system_prompt="MODE: plan")
        cmd = cfg.build_llm_command("task", profile=p, system_prompt="persona")
        body = cmd[-1]
        assert "persona" in body and "MODE: plan" in body and "task" in body
