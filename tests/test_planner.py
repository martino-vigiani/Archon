"""
Tests for the Task Planner system.

The Planner supports two models:
- Legacy: Phase-gated parallel execution (0-3)
- Organic: Intent-based broadcasting (v2.0)

Both models use subprocess calls to Claude CLI (mocked).

Critical tests:
- Fallback plan when Claude unavailable
- JSON extraction from mixed output
- Organic model creates intents, not rigid tasks
- Subagent suggestion logic
- T5 tasks excluded when testing disabled
"""

import json
import pytest
from unittest.mock import patch, MagicMock

from orchestrator.config import Config
from orchestrator.planner import (
    Intent,
    PlannedTask,
    Planner,
    TaskPlan,
)


class TestPlannedTaskDataclass:
    """Test PlannedTask creation."""

    def test_default_fields(self) -> None:
        """PlannedTask should have correct defaults."""
        task = PlannedTask(
            title="Build UI",
            description="Create the login screen",
            terminal="t1",
            priority="high",
            dependencies=[],
            phase=1,
        )
        assert task.intent is None
        assert task.quality_target == 1.0
        assert task.required_subagents == []

    def test_organic_fields(self) -> None:
        """PlannedTask with organic fields."""
        task = PlannedTask(
            title="Build UI",
            description="Create UI",
            terminal="t1",
            priority="critical",
            dependencies=[],
            phase=1,
            intent="Create beautiful interface",
            quality_target=0.8,
            required_subagents=["swiftui-crafter"],
        )
        assert task.intent == "Create beautiful interface"
        assert task.quality_target == 0.8


class TestIntentDataclass:
    """Test Intent creation."""

    def test_intent_defaults(self) -> None:
        """Intent should have sensible defaults."""
        intent = Intent(
            goal="Build the app",
            context="Habit tracking",
            suggested_terminals=["t1", "t2"],
        )
        assert intent.priority == "medium"
        assert intent.quality_threshold == 0.8


class TestTaskPlanDataclass:
    """Test TaskPlan creation."""

    def test_task_plan_defaults(self) -> None:
        """TaskPlan should default to legacy mode."""
        plan = TaskPlan(
            original_task="Build app",
            summary="Plan",
            tasks=[],
            execution_order=[],
        )
        assert plan.planning_mode == "legacy"
        assert plan.intents == []


class TestExtractJson:
    """Test JSON extraction from Claude output."""

    def test_clean_json(self, config: Config) -> None:
        """Should parse clean JSON."""
        planner = Planner(config)
        result = planner._extract_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_json_with_markdown_fences(self, config: Config) -> None:
        """Should strip markdown code fences."""
        planner = Planner(config)
        text = '```json\n{"tasks": []}\n```'
        result = planner._extract_json(text)
        assert result == {"tasks": []}

    def test_json_embedded_in_prose(self, config: Config) -> None:
        """Should extract JSON from surrounding prose."""
        planner = Planner(config)
        text = 'Here is the plan:\n{"summary": "Build it"}\nDone.'
        result = planner._extract_json(text)
        assert result is not None
        assert result["summary"] == "Build it"

    def test_no_json(self, config: Config) -> None:
        """No JSON in text should return None."""
        planner = Planner(config)
        assert planner._extract_json("Just plain text") is None

    def test_empty_string(self, config: Config) -> None:
        """Empty string should return None."""
        planner = Planner(config)
        assert planner._extract_json("") is None

    def test_invalid_json(self, config: Config) -> None:
        """Malformed JSON should return None."""
        planner = Planner(config)
        assert planner._extract_json("{not: valid: json}") is None


class TestFallbackPlan:
    """Test the parallel fallback plan (no Claude needed)."""

    def test_fallback_creates_tasks_for_all_terminals(self, config: Config) -> None:
        """Fallback should create tasks for t1-t5."""
        planner = Planner(config)
        plan = planner._parallel_fallback_plan("Build a habit tracker app")

        terminal_ids = {t.terminal for t in plan.tasks}
        assert "t1" in terminal_ids
        assert "t2" in terminal_ids
        assert "t3" in terminal_ids
        assert "t4" in terminal_ids
        assert "t5" in terminal_ids

    def test_fallback_has_all_phases(self, config: Config) -> None:
        """Fallback should include phases 0, 1, 2, 3."""
        planner = Planner(config)
        plan = planner._parallel_fallback_plan("Build app")

        phases = {t.phase for t in plan.tasks}
        assert phases == {0, 1, 2, 3}

    def test_fallback_phase0_has_no_deps(self, config: Config) -> None:
        """Phase 0 tasks should have no dependencies."""
        planner = Planner(config)
        plan = planner._parallel_fallback_plan("Build app")

        phase0 = [t for t in plan.tasks if t.phase == 0]
        for task in phase0:
            assert task.dependencies == [], f"{task.title} should have no deps"

    def test_fallback_phase1_has_no_deps(self, config: Config) -> None:
        """Phase 1 tasks should have no dependencies (parallel start)."""
        planner = Planner(config)
        plan = planner._parallel_fallback_plan("Build app")

        phase1 = [t for t in plan.tasks if t.phase == 1]
        for task in phase1:
            assert task.dependencies == [], f"{task.title} should have no deps"

    def test_fallback_suggests_subagents(self, config: Config) -> None:
        """Fallback tasks should suggest appropriate subagents."""
        planner = Planner(config)
        plan = planner._parallel_fallback_plan("Build an iOS app")

        t1_tasks = [t for t in plan.tasks if t.terminal == "t1"]
        assert any("swiftui-crafter" in t.required_subagents for t in t1_tasks)

    def test_fallback_no_testing_skips_t5(self, config: Config) -> None:
        """When disable_testing=True, T5 tasks should be excluded."""
        config.disable_testing = True
        planner = Planner(config)
        plan = planner._parallel_fallback_plan("Build app")

        t5_tasks = [t for t in plan.tasks if t.terminal == "t5"]
        assert len(t5_tasks) == 0

    def test_fallback_detects_mobile(self, config: Config) -> None:
        """iOS keywords should trigger mobile-specific subagent suggestions."""
        planner = Planner(config)
        plan = planner._parallel_fallback_plan("Build an iOS meditation app")

        t2_tasks = [t for t in plan.tasks if t.terminal == "t2"]
        assert any("swift-architect" in t.required_subagents for t in t2_tasks)


class TestOrganicPlanning:
    """Test the organic flow planning model."""

    def test_organic_creates_intents(self, config: Config) -> None:
        """Organic model should create Intent objects."""
        planner = Planner(config, use_organic_model=True)
        plan = planner.plan("Build a habit tracker")

        assert plan.planning_mode == "organic"
        assert len(plan.intents) >= 4  # t1-t4 at minimum

    def test_organic_tasks_have_quality_targets(self, config: Config) -> None:
        """Organic tasks should have quality targets."""
        planner = Planner(config, use_organic_model=True)
        plan = planner.plan("Build an app")

        for task in plan.tasks:
            assert 0.0 < task.quality_target <= 1.0

    def test_organic_all_phase_1(self, config: Config) -> None:
        """All organic tasks should be phase 1 (flow state)."""
        planner = Planner(config, use_organic_model=True)
        plan = planner.plan("Build app")

        for task in plan.tasks:
            assert task.phase == 1

    def test_organic_no_dependencies(self, config: Config) -> None:
        """Organic tasks should have no rigid dependencies."""
        planner = Planner(config, use_organic_model=True)
        plan = planner.plan("Build app")

        for task in plan.tasks:
            assert task.dependencies == []

    def test_organic_no_testing_skips_t5(self, config: Config) -> None:
        """Disable testing should exclude T5 intent."""
        config.disable_testing = True
        planner = Planner(config, use_organic_model=True)
        plan = planner.plan("Build app")

        t5_tasks = [t for t in plan.tasks if t.terminal == "t5"]
        assert len(t5_tasks) == 0

    def test_organic_suggests_subagents(self, config: Config) -> None:
        """Organic tasks should suggest relevant subagents."""
        planner = Planner(config, use_organic_model=True)
        plan = planner.plan("Build an iOS app")

        t1_tasks = [t for t in plan.tasks if t.terminal == "t1"]
        assert any("swiftui-crafter" in t.required_subagents for t in t1_tasks)


class TestSubagentSuggestions:
    """Test subagent suggestion logic."""

    @pytest.mark.parametrize(
        "goal,is_mobile,expected",
        [
            ("Create user interface", True, "swiftui-crafter"),
            ("Create user interface", False, "react-crafter"),
            ("Design the architecture and backend", True, "swift-architect"),
            ("Design the architecture and backend", False, "node-architect"),
            ("Document the project", False, "tech-writer"),
            ("Establish direction and scope", False, "product-thinker"),
            ("Validate quality and test coverage", False, "test-genius"),
        ],
    )
    def test_suggest_correct_subagent(
        self, config: Config, goal: str, is_mobile: bool, expected: str
    ) -> None:
        """Should suggest the right subagent for the goal."""
        planner = Planner(config)
        suggestions = planner._suggest_subagents(goal, is_mobile)
        assert expected in suggestions

    def test_no_suggestion_for_generic(self, config: Config) -> None:
        """Generic goals should return empty suggestions."""
        planner = Planner(config)
        suggestions = planner._suggest_subagents("Do something unrelated", False)
        assert suggestions == []


class TestLegacyPlanning:
    """Test legacy Claude-based planning with mocked subprocess."""

    def test_successful_planning(self, config: Config) -> None:
        """Successfully parsed Claude output should create sorted tasks."""
        planner = Planner(config)
        plan_json = json.dumps({
            "summary": "Build app plan",
            "tasks": [
                {"title": "Build UI", "terminal": "t1", "priority": "critical", "phase": 1},
                {"title": "Build API", "terminal": "t2", "priority": "high", "phase": 1},
                {"title": "Write docs", "terminal": "t3", "priority": "medium", "phase": 1},
            ],
            "execution_order": ["Build UI", "Build API", "Write docs"],
        })

        mock_result = MagicMock()
        mock_result.stdout = plan_json
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            plan = planner.plan("Build an app")

        assert len(plan.tasks) == 3
        assert plan.summary == "Build app plan"

    def test_timeout_falls_back(self, config: Config) -> None:
        """Claude timeout should produce fallback plan."""
        import subprocess as sp
        planner = Planner(config)

        with patch("subprocess.run", side_effect=sp.TimeoutExpired("claude", 120)):
            plan = planner.plan("Build app")

        assert len(plan.tasks) > 0  # Fallback produces tasks

    def test_missing_claude_falls_back(self, config: Config) -> None:
        """Missing Claude CLI should produce fallback plan."""
        planner = Planner(config)

        with patch("subprocess.run", side_effect=FileNotFoundError):
            plan = planner.plan("Build app")

        assert len(plan.tasks) > 0

    def test_unparseable_output_falls_back(self, config: Config) -> None:
        """Non-JSON output should produce fallback plan."""
        planner = Planner(config)

        mock_result = MagicMock()
        mock_result.stdout = "This is not JSON at all"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            plan = planner.plan("Build app")

        assert len(plan.tasks) > 0

    def test_invalid_terminal_defaults_to_t2(self, config: Config) -> None:
        """Unknown terminal in plan data should default to t2."""
        planner = Planner(config)
        plan_json = json.dumps({
            "summary": "Plan",
            "tasks": [
                {"title": "Task", "terminal": "t99", "priority": "medium", "phase": 1},
            ],
        })

        mock_result = MagicMock()
        mock_result.stdout = plan_json
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            plan = planner.plan("Build app")

        assert plan.tasks[0].terminal == "t2"

    def test_t5_tasks_skipped_when_disabled(self, config: Config) -> None:
        """T5 tasks should be excluded when testing disabled."""
        config.disable_testing = True
        planner = Planner(config)
        plan_json = json.dumps({
            "summary": "Plan",
            "tasks": [
                {"title": "Build", "terminal": "t1", "priority": "high", "phase": 1},
                {"title": "Test", "terminal": "t5", "priority": "high", "phase": 3},
            ],
        })

        mock_result = MagicMock()
        mock_result.stdout = plan_json
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            plan = planner.plan("Build app")

        assert not any(t.terminal == "t5" for t in plan.tasks)

    def test_tasks_sorted_by_phase_then_priority(self, config: Config) -> None:
        """Tasks should be sorted by phase first, then priority."""
        planner = Planner(config)
        plan_json = json.dumps({
            "summary": "Plan",
            "tasks": [
                {"title": "Low Phase 2", "terminal": "t1", "priority": "low", "phase": 2},
                {"title": "Critical Phase 1", "terminal": "t2", "priority": "critical", "phase": 1},
                {"title": "High Phase 1", "terminal": "t3", "priority": "high", "phase": 1},
            ],
        })

        mock_result = MagicMock()
        mock_result.stdout = plan_json
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            plan = planner.plan("Build app")

        assert plan.tasks[0].title == "Critical Phase 1"
        assert plan.tasks[1].title == "High Phase 1"
        assert plan.tasks[2].title == "Low Phase 2"
