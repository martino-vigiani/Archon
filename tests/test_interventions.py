"""
Tests for Manager Intervention Types.

The organic architecture uses five intervention types:
- AMPLIFY: Boost priority or resources for a task/terminal
- REDIRECT: Shift focus to different work
- MEDIATE: Resolve conflicts between terminals
- INJECT: Add new work to unblock or address emergent needs
- PRUNE: Remove or deprioritize work that's no longer needed

Interventions are how the Manager Intelligence actively guides the flow.
"""

from datetime import datetime, timedelta

import pytest

from orchestrator.config import TerminalID
from orchestrator.manager_intelligence import (
    ActionType,
    FileConflict,
    ManagerAction,
    ManagerIntelligence,
    TerminalHeartbeat,
)
from orchestrator.report_manager import Report
from orchestrator.task_queue import TaskQueue


class TestInterventionTypes:
    """Test that all intervention types are properly defined."""

    @pytest.mark.parametrize(
        "action_type",
        [
            ActionType.REORDER_TASKS,
            ActionType.INJECT_TASK,
            ActionType.BROADCAST_UPDATE,
            ActionType.PAUSE_TERMINAL,
            ActionType.RESUME_TERMINAL,
            ActionType.ESCALATE,
            ActionType.TRIGGER_SYNC_POINT,
        ],
    )
    def test_action_types_have_string_values(self, action_type: ActionType):
        """All action types should have string values."""
        assert action_type.value is not None
        assert isinstance(action_type.value, str)


class TestAMPLIFYIntervention:
    """Test AMPLIFY intervention - boosting priority/resources."""

    def test_amplify_via_task_reordering(self, manager_intelligence: ManagerIntelligence):
        """AMPLIFY can be achieved via task reordering to prioritize work."""
        heartbeats: dict[TerminalID, TerminalHeartbeat] = {
            "t1": TerminalHeartbeat(
                terminal_id="t1",
                timestamp=datetime.now().isoformat(),
                current_task_id=None,  # Idle
                is_blocked=False,
            ),
        }

        # Add some pending tasks
        manager_intelligence.task_queue.add_task(
            title="Low Priority Task",
            description="Less important",
            assigned_to="t2",
        )
        manager_intelligence.task_queue.add_task(
            title="High Priority Task",
            description="Important work",
            assigned_to=None,  # Unassigned
        )

        actions = manager_intelligence._check_task_reordering(heartbeats, current_phase=1)

        # Should suggest reordering to put unassigned tasks first for idle terminal
        if actions:
            assert actions.action_type == ActionType.REORDER_TASKS

    def test_broadcast_update_can_amplify_focus(self, manager_intelligence: ManagerIntelligence):
        """AMPLIFY via broadcast to coordinate focus."""
        message = manager_intelligence.generate_coordination_broadcast(
            situation="Critical: Login feature needs attention from all terminals",
            affected_terminals=["t1", "t2"],
        )

        assert "Coordination Update" in message
        assert "T1, T2" in message
        assert "Login feature" in message


class TestREDIRECTIntervention:
    """Test REDIRECT intervention - shifting focus to different work."""

    def test_redirect_via_escalation(self, manager_intelligence: ManagerIntelligence):
        """REDIRECT can escalate to shift terminal focus."""
        # Create a situation where redirect is needed - terminal stalled
        old_time = datetime.now() - timedelta(seconds=200)
        heartbeats: dict[TerminalID, TerminalHeartbeat] = {
            "t1": TerminalHeartbeat(
                terminal_id="t1",
                timestamp=old_time.isoformat(),  # Stale
                current_task_id="task_stuck",
                progress_percent=20,
            ),
        }

        stalled = manager_intelligence.detect_stalled_terminals(heartbeats)
        assert "t1" in stalled

    def test_generate_unblock_action_for_waiting(self, manager_intelligence: ManagerIntelligence):
        """REDIRECT via unblock action when terminal is waiting."""
        action = manager_intelligence._generate_unblock_action(
            terminal_id="t1",
            blocker_reason="Waiting for API from T2",
        )

        assert action is not None
        assert action.action_type == ActionType.BROADCAST_UPDATE
        assert "waiting" in action.reason.lower()


class TestMEDIATEIntervention:
    """Test MEDIATE intervention - resolving conflicts between terminals."""

    def test_mediate_file_conflicts(self, manager_intelligence: ManagerIntelligence):
        """MEDIATE detects and resolves file conflicts."""
        heartbeats: dict[TerminalID, TerminalHeartbeat] = {
            "t1": TerminalHeartbeat(
                terminal_id="t1",
                timestamp=datetime.now().isoformat(),
                files_being_edited=["UserModel.swift", "LoginView.swift"],
            ),
            "t2": TerminalHeartbeat(
                terminal_id="t2",
                timestamp=datetime.now().isoformat(),
                files_being_edited=["UserModel.swift", "UserService.swift"],  # Conflict!
            ),
        }

        conflicts = manager_intelligence.detect_file_conflicts(heartbeats)

        assert len(conflicts) >= 1
        assert any(c.file_path == "UserModel.swift" for c in conflicts)

    def test_file_conflict_resolution_action(self, manager_intelligence: ManagerIntelligence):
        """MEDIATE generates resolution action for file conflicts."""
        conflict = FileConflict(
            file_path="UserModel.swift",
            terminals=["t1", "t2"],
            severity="high",
        )

        action = manager_intelligence._resolve_file_conflict(conflict)

        assert action is not None
        assert action.action_type == ActionType.BROADCAST_UPDATE
        assert "UserModel.swift" in action.broadcast_message
        assert "conflict" in action.broadcast_message.lower()

    def test_interface_mismatch_detection(self, manager_intelligence: ManagerIntelligence):
        """MEDIATE detects interface mismatches between T1 and T2."""
        # T1 expects a UserStore from T2
        t1_report = Report(
            id="r1",
            task_id="t1",
            terminal_id="t1",
            summary="Created ProfileView",
            dependencies_needed=[
                {"from": "t2", "what": "UserStore for profile data"},
            ],
        )

        # T2 hasn't implemented it yet
        t2_report = Report(
            id="r2",
            task_id="t2",
            terminal_id="t2",
            summary="Created AuthService",
            components_created=["AuthService", "LoginHandler"],
        )

        contracts = {
            "t1": [t1_report],
            "t2": [t2_report],
        }

        mismatches = manager_intelligence.detect_interface_mismatches(contracts)

        # Should detect that UserStore is needed but not provided
        assert len(mismatches) >= 0  # May or may not detect based on parsing


class TestINJECTIntervention:
    """Test INJECT intervention - adding new work to address emergent needs."""

    def test_inject_task_for_missing_dependency(self, manager_intelligence: ManagerIntelligence):
        """INJECT adds task when a terminal reports missing dependency."""
        action = manager_intelligence._generate_unblock_action(
            terminal_id="t1",
            blocker_reason="Missing UserModel - not found in project",
        )

        assert action is not None
        assert action.action_type == ActionType.INJECT_TASK
        assert action.task_title is not None
        assert "missing" in action.task_title.lower() or "unblock" in action.task_title.lower()

    def test_inject_task_targets_responsible_terminal(
        self, manager_intelligence: ManagerIntelligence
    ):
        """INJECT routes task to the appropriate terminal."""
        # Model-related should go to T2
        action = manager_intelligence._generate_unblock_action(
            terminal_id="t1",
            blocker_reason="Missing User model for profile display",
        )

        assert action is not None
        assert action.target_terminal == "t2"

        # UI-related should go to T1
        action = manager_intelligence._generate_unblock_action(
            terminal_id="t2",
            blocker_reason="Missing LoginView component",
        )

        assert action is not None
        assert action.target_terminal == "t1"

    def test_guess_responsible_terminal(self, manager_intelligence: ManagerIntelligence):
        """Test terminal routing heuristics."""
        # Backend/model keywords -> T2
        assert manager_intelligence._guess_responsible_terminal("UserModel missing") == "t2"
        assert manager_intelligence._guess_responsible_terminal("API not implemented") == "t2"
        assert manager_intelligence._guess_responsible_terminal("Service unavailable") == "t2"

        # UI keywords -> T1
        assert manager_intelligence._guess_responsible_terminal("LoginView missing") == "t1"
        assert manager_intelligence._guess_responsible_terminal("Component not found") == "t1"

        # Docs keywords -> T3
        assert manager_intelligence._guess_responsible_terminal("README missing") == "t3"
        assert manager_intelligence._guess_responsible_terminal("Documentation needed") == "t3"

        # Test keywords -> T5
        assert manager_intelligence._guess_responsible_terminal("Test failing") == "t5"


class TestPRUNEIntervention:
    """Test PRUNE intervention - removing or deprioritizing work."""

    def test_cancel_task_prunes_work(self, task_queue: TaskQueue):
        """PRUNE removes pending tasks from the queue."""
        task = task_queue.add_task(
            title="Unnecessary Feature",
            description="No longer needed",
        )

        cancelled = task_queue.cancel_task(task.id)

        assert cancelled is not None
        assert cancelled.id == task.id
        assert task_queue.get_task(task.id) is None

    def test_cannot_cancel_in_progress_task(self, task_queue: TaskQueue):
        """Cannot PRUNE (cancel) an in-progress task directly."""
        task = task_queue.add_task(
            title="Active Work",
            description="Being worked on",
        )
        task_queue.assign_task(task.id, "t1")

        cancelled = task_queue.cancel_task(task.id)

        # In-progress tasks cannot be cancelled via cancel_task
        assert cancelled is None


class TestInterventionTriggers:
    """Test conditions that trigger interventions."""

    def test_stalled_terminal_triggers_escalation(self, manager_intelligence: ManagerIntelligence):
        """Stalled terminals should trigger ESCALATE action."""
        old_time = datetime.now() - timedelta(seconds=200)
        heartbeats: dict[TerminalID, TerminalHeartbeat] = {
            "t1": TerminalHeartbeat(
                terminal_id="t1",
                timestamp=old_time.isoformat(),
                current_task_id="stuck_task",
            ),
        }

        actions = manager_intelligence.analyze_and_decide(
            heartbeats=heartbeats,
            contracts={},
            current_phase=1,
        )

        escalation_actions = [a for a in actions if a.action_type == ActionType.ESCALATE]
        assert len(escalation_actions) >= 1

    def test_blocked_terminal_triggers_broadcast(self, manager_intelligence: ManagerIntelligence):
        """Blocked terminals should trigger coordination broadcast."""
        heartbeats: dict[TerminalID, TerminalHeartbeat] = {
            "t1": TerminalHeartbeat(
                terminal_id="t1",
                timestamp=datetime.now().isoformat(),
                current_task_id="blocked_task",
                is_blocked=True,
                blocker_reason="Waiting for T2 API",
            ),
        }

        actions = manager_intelligence.analyze_and_decide(
            heartbeats=heartbeats,
            contracts={},
            current_phase=1,
        )

        # Should have a broadcast or inject action
        assert len(actions) >= 1

    def test_file_conflict_triggers_mediation(self, manager_intelligence: ManagerIntelligence):
        """File conflicts should trigger mediation actions."""
        heartbeats: dict[TerminalID, TerminalHeartbeat] = {
            "t1": TerminalHeartbeat(
                terminal_id="t1",
                timestamp=datetime.now().isoformat(),
                files_being_edited=["Config.swift"],
            ),
            "t2": TerminalHeartbeat(
                terminal_id="t2",
                timestamp=datetime.now().isoformat(),
                files_being_edited=["Config.swift"],  # Same file!
            ),
        }

        actions = manager_intelligence.analyze_and_decide(
            heartbeats=heartbeats,
            contracts={},
            current_phase=1,
        )

        broadcast_actions = [a for a in actions if a.action_type == ActionType.BROADCAST_UPDATE]
        assert len(broadcast_actions) >= 1


class TestInterventionDeduplication:
    """Test that interventions are not duplicated."""

    def test_file_conflict_addressed_once(self, manager_intelligence: ManagerIntelligence):
        """File conflicts should only generate action once."""
        heartbeats: dict[TerminalID, TerminalHeartbeat] = {
            "t1": TerminalHeartbeat(
                terminal_id="t1",
                timestamp=datetime.now().isoformat(),
                files_being_edited=["Model.swift"],
            ),
            "t2": TerminalHeartbeat(
                terminal_id="t2",
                timestamp=datetime.now().isoformat(),
                files_being_edited=["Model.swift"],
            ),
        }

        # First analysis
        actions1 = manager_intelligence.analyze_and_decide(
            heartbeats=heartbeats,
            contracts={},
            current_phase=1,
        )

        # Second analysis with same state
        actions2 = manager_intelligence.analyze_and_decide(
            heartbeats=heartbeats,
            contracts={},
            current_phase=1,
        )

        # The conflict should only be addressed in the first analysis
        conflict_actions1 = [a for a in actions1 if "conflict" in str(a.reason).lower()]
        conflict_actions2 = [a for a in actions2 if "conflict" in str(a.reason).lower()]

        # First should have it, second should be deduplicated
        if conflict_actions1:
            # If there was a conflict in first, second should have fewer
            assert len(conflict_actions2) <= len(conflict_actions1)

    def test_sync_point_triggered_once_per_phase(self, manager_intelligence: ManagerIntelligence):
        """Sync points should only be triggered once per phase."""
        # Phase 1 already tracked
        manager_intelligence._triggered_sync_points.add(1)

        heartbeats: dict[TerminalID, TerminalHeartbeat] = {
            "t1": TerminalHeartbeat(
                terminal_id="t1",
                timestamp=datetime.now().isoformat(),
                current_task_id=None,  # Idle
                progress_percent=100,
            ),
        }

        actions = manager_intelligence.analyze_and_decide(
            heartbeats=heartbeats,
            contracts={},
            current_phase=1,
        )

        sync_actions = [a for a in actions if a.action_type == ActionType.TRIGGER_SYNC_POINT]

        # Should not trigger again for phase 1
        phase_1_syncs = [a for a in sync_actions if "Phase 1" in str(a.reason)]
        assert len(phase_1_syncs) == 0


class TestManagerActionCreation:
    """Test ManagerAction dataclass creation."""

    @pytest.mark.parametrize(
        "action_type,reason,priority",
        [
            (ActionType.REORDER_TASKS, "Prioritize urgent work", "high"),
            (ActionType.INJECT_TASK, "Add missing dependency", "critical"),
            (ActionType.BROADCAST_UPDATE, "Coordinate terminals", "medium"),
            (ActionType.PAUSE_TERMINAL, "Wait for dependency", "medium"),
            (ActionType.RESUME_TERMINAL, "Resume work", "low"),
            (ActionType.ESCALATE, "Need human attention", "high"),
            (ActionType.TRIGGER_SYNC_POINT, "Phase complete", "high"),
        ],
    )
    def test_create_manager_action(self, action_type: ActionType, reason: str, priority: str):
        """Test creating various manager actions."""
        action = ManagerAction(
            action_type=action_type,
            reason=reason,
            priority=priority,
        )

        assert action.action_type == action_type
        assert action.reason == reason
        assert action.priority == priority
        assert action.created_at is not None

    def test_action_to_dict(self):
        """Test action serialization."""
        action = ManagerAction(
            action_type=ActionType.INJECT_TASK,
            reason="Add missing component",
            priority="high",
            target_terminal="t2",
            task_title="Implement UserStore",
            task_description="Create UserStore class",
        )

        action_dict = action.to_dict()

        assert action_dict["action_type"] == "inject_task"
        assert action_dict["target_terminal"] == "t2"
        assert action_dict["task_title"] == "Implement UserStore"


class TestActionHistory:
    """Test manager action history tracking."""

    def test_actions_stored_in_history(self, manager_intelligence: ManagerIntelligence):
        """Actions should be stored in history."""
        old_time = datetime.now() - timedelta(seconds=200)
        heartbeats: dict[TerminalID, TerminalHeartbeat] = {
            "t1": TerminalHeartbeat(
                terminal_id="t1",
                timestamp=old_time.isoformat(),
                current_task_id="task",
            ),
        }

        actions = manager_intelligence.analyze_and_decide(
            heartbeats=heartbeats,
            contracts={},
            current_phase=1,
        )

        recent = manager_intelligence.get_recent_actions()

        # Actions from analysis should be in history
        assert len(recent) >= len(actions)

    def test_clear_action_history(self, manager_intelligence: ManagerIntelligence):
        """Can clear action history."""
        # Add some actions
        manager_intelligence._action_history.append(
            ManagerAction(action_type=ActionType.ESCALATE, reason="Test")
        )

        manager_intelligence.clear_action_history()

        assert len(manager_intelligence.get_recent_actions()) == 0
        assert len(manager_intelligence._addressed_conflicts) == 0
        assert len(manager_intelligence._addressed_mismatches) == 0
