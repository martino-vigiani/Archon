"""Tests for Codex-ready runtime configuration and prompt compaction."""

from pathlib import Path

from orchestrator.config import Config


def _make_config(tmp_path: Path) -> Config:
    """Create an isolated config rooted in tmp_path."""
    return Config(
        base_dir=tmp_path,
        orchestra_dir=tmp_path / ".orchestra",
        templates_dir=tmp_path / "templates" / "terminal_prompts",
        compact_templates_dir=tmp_path / "templates" / "terminal_prompts_compact",
        agents_dir=tmp_path / ".claude" / "agents",
        apps_dir=tmp_path / "Apps",
    )


def test_post_init_sets_compact_dir_with_custom_templates(tmp_path: Path) -> None:
    cfg = Config(
        base_dir=tmp_path,
        templates_dir=tmp_path / "templates" / "terminal_prompts",
    )
    assert cfg.compact_templates_dir == tmp_path / "templates" / "terminal_prompts_compact"


def test_get_terminal_system_prompt_path_prefers_compact(tmp_path: Path) -> None:
    cfg = _make_config(tmp_path)
    cfg.ensure_dirs()
    prompt_name = cfg.get_terminal_config("t1").prompt_file
    (cfg.templates_dir / prompt_name).write_text("full prompt")
    compact = cfg.compact_templates_dir / prompt_name
    compact.write_text("compact prompt")

    assert cfg.get_terminal_system_prompt_path("t1") == compact


def test_load_system_prompt_includes_runtime_header(tmp_path: Path) -> None:
    cfg = _make_config(tmp_path)
    cfg.ensure_dirs()
    cfg.llm_provider = "codex"
    cfg.llm_model = "gpt-5.3-codex"

    prompt_name = cfg.get_terminal_config("t2").prompt_file
    (cfg.compact_templates_dir / prompt_name).write_text("T2 compact prompt body")

    loaded = cfg.load_system_prompt("t2")
    assert loaded is not None
    assert "Runtime Profile" in loaded
    assert "Provider target: codex" in loaded
    assert "Model target: gpt-5.3-codex" in loaded
    assert "Reasoning profile: xhigh" in loaded
    assert "T2 compact prompt body" in loaded


def test_load_system_prompt_truncates(tmp_path: Path) -> None:
    cfg = _make_config(tmp_path)
    cfg.ensure_dirs()
    cfg.max_system_prompt_chars = 40

    prompt_name = cfg.get_terminal_config("t1").prompt_file
    (cfg.compact_templates_dir / prompt_name).write_text("x" * 100)
    loaded = cfg.load_system_prompt("t1")
    assert loaded is not None
    assert "Prompt truncated to reduce token usage" in loaded


def test_build_llm_command_claude_default() -> None:
    cfg = Config()
    cmd = cfg.build_llm_command("hello world", allow_unsafe=True)

    assert cmd[0] == "claude"
    assert "--print" in cmd
    assert "--dangerously-skip-permissions" in cmd
    assert cmd[-2:] == ["-p", "hello world"]


def test_build_llm_command_codex() -> None:
    cfg = Config()
    cfg.llm_provider = "codex"
    cfg.llm_command = "codex"
    cfg.llm_model = "gpt-5.3-codex"

    cmd = cfg.build_llm_command("implement feature", allow_unsafe=True)

    assert cmd[:2] == ["codex", "exec"]
    assert "--dangerously-bypass-approvals-and-sandbox" in cmd
    assert "-m" in cmd
    assert "gpt-5.3-codex" in cmd
    assert cmd[-1] == "implement feature"


def test_get_all_subagents_merges_local_agent_defs(tmp_path: Path) -> None:
    cfg = _make_config(tmp_path)
    cfg.ensure_dirs()
    (cfg.agents_dir / "creative-researcher.md").write_text("# Creative Researcher")

    subagents = cfg.get_all_subagents()
    assert "creative-researcher" in subagents
    assert "swiftui-crafter" in subagents
    assert "test-genius" in subagents
