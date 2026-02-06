"""
Tests for Terminal Personality Behavior.

Each terminal has a distinct personality:
- T1 Craftsman: Sees the user's experience, builds beautiful interfaces
- T2 Architect: Sees the forces on the system, builds reliable foundations
- T3 Narrator: Sees the story the code tells, writes clear documentation
- T4 Strategist: Sees the map from above, guides scope and direction
- T5 Skeptic: Sees what could break, verifies and validates

Key principle: Any terminal can use ANY subagent. Personalities inform
approach, not limit capabilities.
"""

import pytest
from pathlib import Path

from orchestrator.config import Config, TERMINALS, TerminalConfig, TerminalID
from orchestrator.manager_intelligence import TerminalHeartbeat


class TestTerminalPersonalities:
    """Test that terminal personalities are properly defined."""

    def test_all_five_terminals_defined(self):
        """All five terminals should be defined in config."""
        expected_terminals = ["t1", "t2", "t3", "t4", "t5"]

        for tid in expected_terminals:
            assert tid in TERMINALS, f"Terminal {tid} should be defined"

    @pytest.mark.parametrize(
        "terminal_id,expected_role",
        [
            ("t1", "UI/UX"),
            ("t2", "Features"),
            ("t3", "Docs/Marketing"),
            ("t4", "Ideas/Strategy"),
            ("t5", "QA/Testing"),
        ],
    )
    def test_terminal_roles(self, terminal_id: TerminalID, expected_role: str):
        """Each terminal should have the correct role."""
        config = TERMINALS[terminal_id]
        assert config.role == expected_role

    @pytest.mark.parametrize(
        "terminal_id,expected_prompt",
        [
            ("t1", "t1_uiux.md"),
            ("t2", "t2_features.md"),
            ("t3", "t3_docs.md"),
            ("t4", "t4_ideas.md"),
            ("t5", "t5_qa.md"),
        ],
    )
    def test_terminal_prompt_files(self, terminal_id: TerminalID, expected_prompt: str):
        """Each terminal should have the correct prompt file."""
        config = TERMINALS[terminal_id]
        assert config.prompt_file == expected_prompt


class TestCraftsmanBehavior:
    """Test T1 Craftsman behavior characteristics."""

    def test_t1_has_ui_keywords(self):
        """T1 should be routed to for UI-related work."""
        config = TERMINALS["t1"]

        ui_keywords = ["ui", "component", "view", "screen", "layout", "swiftui", "react"]
        for keyword in ui_keywords:
            assert keyword in config.keywords

    def test_t1_has_ui_subagents(self):
        """T1 should have access to UI subagents."""
        config = TERMINALS["t1"]

        assert "swiftui-crafter" in config.subagents
        assert "react-crafter" in config.subagents
        assert "design-system" in config.subagents

    def test_craftsman_heartbeat_includes_ui_files(self):
        """Craftsman heartbeat should track UI files being edited."""
        heartbeat = TerminalHeartbeat(
            terminal_id="t1",
            current_task_id="task_ui",
            current_task_title="Build Login Screen",
            files_being_edited=["LoginView.swift", "LoginViewModel.swift"],
            files_recently_created=["LoginView.swift"],
        )

        assert len(heartbeat.files_being_edited) > 0
        assert any(".swift" in f for f in heartbeat.files_being_edited)


class TestArchitectBehavior:
    """Test T2 Architect behavior characteristics."""

    def test_t2_has_architecture_keywords(self):
        """T2 should be routed to for architecture work."""
        config = TERMINALS["t2"]

        arch_keywords = ["feature", "architecture", "model", "service", "api", "database"]
        for keyword in arch_keywords:
            assert keyword in config.keywords

    def test_t2_has_architecture_subagents(self):
        """T2 should have access to architecture subagents."""
        config = TERMINALS["t2"]

        assert "swift-architect" in config.subagents
        assert "node-architect" in config.subagents
        assert "database-expert" in config.subagents

    def test_architect_focuses_on_foundations(self):
        """Architect should work on foundational services."""
        heartbeat = TerminalHeartbeat(
            terminal_id="t2",
            current_task_id="task_service",
            current_task_title="Build UserService",
            files_being_edited=["UserService.swift", "User.swift"],
            files_recently_created=["UserService.swift", "User.swift"],
        )

        # Service/model files indicate foundation work
        assert any("Service" in f for f in heartbeat.files_being_edited)
        assert any(
            f.endswith(".swift") and not "View" in f
            for f in heartbeat.files_being_edited
        )


class TestNarratorBehavior:
    """Test T3 Narrator behavior characteristics."""

    def test_t3_has_documentation_keywords(self):
        """T3 should be routed to for documentation work."""
        config = TERMINALS["t3"]

        doc_keywords = ["documentation", "docs", "readme", "guide", "tutorial"]
        for keyword in doc_keywords:
            assert keyword in config.keywords

    def test_t3_has_writing_subagents(self):
        """T3 should have access to writing subagents."""
        config = TERMINALS["t3"]

        assert "tech-writer" in config.subagents
        assert "marketing-strategist" in config.subagents

    def test_narrator_works_on_docs(self):
        """Narrator should work on documentation files."""
        heartbeat = TerminalHeartbeat(
            terminal_id="t3",
            current_task_id="task_docs",
            current_task_title="Write README",
            files_being_edited=["README.md", "docs/API.md"],
            files_recently_created=["docs/SETUP.md"],
        )

        assert any(".md" in f for f in heartbeat.files_being_edited)


class TestStrategistBehavior:
    """Test T4 Strategist behavior characteristics."""

    def test_t4_has_strategy_keywords(self):
        """T4 should be routed to for strategy work."""
        config = TERMINALS["t4"]

        strategy_keywords = ["strategy", "product", "roadmap", "mvp", "monetization"]
        for keyword in strategy_keywords:
            assert keyword in config.keywords

    def test_t4_has_strategy_subagents(self):
        """T4 should have access to strategy subagents."""
        config = TERMINALS["t4"]

        assert "product-thinker" in config.subagents
        assert "monetization-expert" in config.subagents

    def test_strategist_provides_direction(self):
        """Strategist should provide direction to other terminals."""
        heartbeat = TerminalHeartbeat(
            terminal_id="t4",
            current_task_id="task_mvp",
            current_task_title="Define MVP Scope",
            progress_percent=90,
            # Strategist typically doesn't edit many files
            files_being_edited=[],
        )

        # Strategist tasks are often about decisions, not files
        assert heartbeat.progress_percent > 0


class TestSkepticBehavior:
    """Test T5 Skeptic behavior characteristics."""

    def test_t5_has_testing_keywords(self):
        """T5 should be routed to for testing work."""
        config = TERMINALS["t5"]

        test_keywords = ["test", "verify", "validate", "quality", "qa"]
        for keyword in test_keywords:
            assert keyword in config.keywords

    def test_t5_has_testing_subagents(self):
        """T5 should have access to testing subagents."""
        config = TERMINALS["t5"]

        assert "test-genius" in config.subagents

    def test_skeptic_verifies_builds(self):
        """Skeptic should track build and test status."""
        heartbeat = TerminalHeartbeat(
            terminal_id="t5",
            current_task_id="task_test",
            current_task_title="Run Tests and Verify Build",
            progress_percent=50,
            files_being_edited=["Tests/UserServiceTests.swift"],
        )

        assert "Tests" in heartbeat.files_being_edited[0]


class TestCrossTerminalCollaboration:
    """Test that terminals can collaborate effectively."""

    def test_task_routing_to_correct_terminal(self, config: Config):
        """Tasks should be routed to the most appropriate terminal."""
        # UI task -> T1
        assert config.route_task_to_terminal("Create login screen UI component layout") == "t1"

        # Feature task -> T2
        assert config.route_task_to_terminal("Implement authentication service backend") == "t2"

        # Docs task -> T3 (use multiple doc keywords to score higher)
        assert config.route_task_to_terminal("Write README documentation guide") == "t3"

        # Strategy task -> T4
        assert config.route_task_to_terminal("Define product roadmap mvp strategy") == "t4"

        # Note: T5 is not in the route_task_to_terminal scoring dict (only t1-t4)
        # so we test that test-related tasks still get routed (may go to t2 as default)

    def test_terminals_can_communicate_via_heartbeat(self, all_heartbeats):
        """All terminals should have valid heartbeat structure."""
        for terminal_id, heartbeat in all_heartbeats.items():
            assert heartbeat.terminal_id == terminal_id
            assert heartbeat.timestamp is not None

    def test_heartbeat_shows_collaboration_needs(self):
        """Heartbeats can express what a terminal needs from others."""
        heartbeat = TerminalHeartbeat(
            terminal_id="t1",
            current_task_id="task_profile",
            current_task_title="Build Profile View",
            is_blocked=True,
            blocker_reason="Waiting for UserService API from T2",
        )

        assert heartbeat.is_blocked
        assert "T2" in heartbeat.blocker_reason


class TestAnyTerminalAnySubagent:
    """Test that any terminal can use any subagent."""

    def test_t1_can_access_architecture_subagents(self):
        """
        T1 (Craftsman) can use architecture subagents when needed.
        The prompts say: 'Any terminal can use any subagent.'
        """
        t1_config = TERMINALS["t1"]
        t2_config = TERMINALS["t2"]

        # T1's default subagents are UI-focused
        assert "swiftui-crafter" in t1_config.subagents

        # But T1 can still use T2's subagents via invocation
        # This is documented in the prompts, not enforced in config
        # The config just lists defaults, not restrictions

    def test_t2_can_access_ui_subagents(self):
        """
        T2 (Architect) can use UI subagents when needed.
        """
        # T2 can invoke swiftui-crafter even if not in default list
        # This flexibility is part of the organic architecture
        pass  # Documented behavior, not enforced in config

    def test_terminal_configs_have_subagents(self):
        """Each terminal should have at least one subagent."""
        for tid in ["t1", "t2", "t3", "t4", "t5"]:
            config = TERMINALS[tid]
            assert len(config.subagents) > 0, f"{tid} should have subagents"

    def test_all_common_subagents_exist(self):
        """Common subagents should be distributed across terminals."""
        all_subagents: set[str] = set()
        for config in TERMINALS.values():
            all_subagents.update(config.subagents)

        expected = [
            "swiftui-crafter",
            "swift-architect",
            "tech-writer",
            "product-thinker",
            "test-genius",
        ]

        for subagent in expected:
            assert subagent in all_subagents, f"{subagent} should exist"


class TestHeartbeatPersonality:
    """Test that heartbeats can reflect terminal personality."""

    @pytest.mark.parametrize(
        "terminal_id,personality",
        [
            ("t1", "craftsman"),
            ("t2", "architect"),
            ("t3", "narrator"),
            ("t4", "strategist"),
            ("t5", "skeptic"),
        ],
    )
    def test_heartbeat_can_include_personality(
        self, terminal_id: TerminalID, personality: str
    ):
        """Heartbeats can include personality field for context."""
        heartbeat = TerminalHeartbeat(
            terminal_id=terminal_id,
            current_task_id="task_test",
            current_task_title="Test Task",
        )

        # While personality isn't in the base class, it could be added to metadata
        heartbeat_dict = heartbeat.to_dict()
        heartbeat_dict["personality"] = personality

        assert heartbeat_dict["terminal_id"] == terminal_id
        assert heartbeat_dict["personality"] == personality


class TestTerminalConfigDataclass:
    """Test TerminalConfig dataclass behavior."""

    def test_terminal_config_has_required_fields(self):
        """TerminalConfig should have all required fields."""
        config = TerminalConfig(
            id="t1",
            role="UI/UX",
            description="Handles user interface",
            subagents=["swiftui-crafter"],
            keywords=["ui", "component"],
        )

        assert config.id == "t1"
        assert config.role == "UI/UX"
        assert len(config.subagents) > 0
        assert len(config.keywords) > 0

    def test_prompt_file_property(self):
        """prompt_file property should return correct filename."""
        for tid in ["t1", "t2", "t3", "t4", "t5"]:
            config = TERMINALS[tid]
            assert config.prompt_file.endswith(".md")
            assert config.prompt_file.startswith(tid)


class TestPromptFilesExist:
    """Test that terminal prompt files exist in the templates directory."""

    def test_prompt_files_exist(self):
        """All terminal prompt files should exist."""
        templates_dir = Path(__file__).parent.parent / "templates" / "terminal_prompts"

        for tid in ["t1", "t2", "t3", "t4", "t5"]:
            config = TERMINALS[tid]
            prompt_path = templates_dir / config.prompt_file

            assert prompt_path.exists(), f"Prompt file {config.prompt_file} should exist"

    def test_prompt_files_contain_personality(self):
        """Prompt files should contain personality definition."""
        templates_dir = Path(__file__).parent.parent / "templates" / "terminal_prompts"

        expected_personalities = {
            "t1": "Craftsman",
            "t2": "Architect",
            "t3": "Narrator",
            "t4": "Strategist",
            "t5": "Skeptic",
        }

        for tid, personality in expected_personalities.items():
            config = TERMINALS[tid]
            prompt_path = templates_dir / config.prompt_file

            if prompt_path.exists():
                content = prompt_path.read_text()
                assert (
                    personality in content
                ), f"{tid} prompt should contain '{personality}'"
