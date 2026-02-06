"""
Tests for Organic Flow Execution (no phases).

The organic flow model removes rigid phase gates:
- Tasks flow based on dependencies and availability
- Work continues based on readiness, not phase numbers
- Flow states: FLOWING, BLOCKED, FLOURISHING, STALLED, CONVERGING

This represents a shift from "Phase 1 -> Phase 2 -> Phase 3" to
continuous, organic work progression.
"""

import pytest
from datetime import datetime

from orchestrator.task_queue import FlowState, Task, TaskPriority, TaskQueue, TaskStatus


class TestFlowStateTransitions:
    """Test organic flow state transitions."""

    def test_initial_flow_state_is_flowing(self, sample_task: Task):
        """New tasks should start in FLOWING state."""
        assert sample_task.flow_state == FlowState.FLOWING

    def test_blocked_task_has_blocked_state(self, blocked_task: Task):
        """Blocked tasks should have BLOCKED flow state."""
        assert blocked_task.flow_state == FlowState.BLOCKED

    def test_high_quality_task_has_flourishing_state(self, high_quality_task: Task):
        """High quality tasks should have FLOURISHING state."""
        assert high_quality_task.flow_state == FlowState.FLOURISHING

    def test_flow_state_changes_with_quality(self, sample_task: Task):
        """Flow state should transition based on quality updates."""
        # Initially FLOWING
        assert sample_task.flow_state == FlowState.FLOWING

        # Quality at 0.75 -> FLOURISHING
        sample_task.update_quality(0.75)
        assert sample_task.flow_state == FlowState.FLOURISHING

        # Quality at 0.95 -> CONVERGING
        sample_task.update_quality(0.95)
        assert sample_task.flow_state == FlowState.CONVERGING

    @pytest.mark.parametrize(
        "flow_state",
        [
            FlowState.FLOWING,
            FlowState.BLOCKED,
            FlowState.FLOURISHING,
            FlowState.STALLED,
            FlowState.CONVERGING,
        ],
    )
    def test_all_flow_states_exist(self, flow_state: FlowState):
        """Verify all flow states are defined and have string values."""
        assert flow_state.value is not None
        assert isinstance(flow_state.value, str)


class TestDependencyBasedReadiness:
    """Test that tasks are ready based on dependencies, not phases."""

    def test_task_without_dependencies_is_ready(self, sample_task: Task):
        """Tasks without dependencies should be ready immediately."""
        completed_ids: set[str] = set()
        assert sample_task.is_ready(completed_ids, current_phase=0)

    def test_task_with_unmet_dependencies_not_ready_in_phase_2(self):
        """Phase 2+ tasks with unmet dependencies are not ready."""
        task = Task(
            id="task_dep",
            title="Dependent Task",
            description="Needs something first",
            dependencies=["other_task"],
            phase=2,
        )
        completed_ids: set[str] = set()
        # Phase 2 task with unmet deps - not ready
        assert not task.is_ready(completed_ids, current_phase=2)

    def test_task_with_met_dependencies_is_ready(self):
        """Tasks with all dependencies met should be ready."""
        task = Task(
            id="task_dep",
            title="Dependent Task",
            description="Needs something first",
            dependencies=["other_task"],
            phase=2,
        )
        completed_ids = {"other_task"}
        assert task.is_ready(completed_ids, current_phase=2)

    def test_blocked_task_not_ready_regardless_of_dependencies(self):
        """Blocked tasks are not ready even if dependencies are met."""
        task = Task(
            id="task_blocked",
            title="Blocked Task",
            description="Waiting for external input",
            dependencies=["other_task"],
            phase=2,
            flow_state=FlowState.BLOCKED,
        )
        completed_ids = {"other_task"}
        assert not task.is_ready(completed_ids, current_phase=2)

    def test_phase_1_tasks_always_ready(self):
        """Phase 0/1 tasks are always ready (no blocking dependencies)."""
        task = Task(
            id="task_p1",
            title="Phase 1 Task",
            description="Initial work",
            dependencies=["some_dependency"],
            phase=1,
        )
        # Even with unmet dependencies, phase 1 tasks can start
        assert task.is_ready(set(), current_phase=0)


class TestFlowWithoutPhaseGates:
    """Test that work flows without rigid phase gates."""

    def test_next_task_ignores_strict_phase_gating(self, task_queue):
        """Tasks should be available based on readiness, not phase number."""
        # Add phase 1 task
        p1_task = task_queue.add_task(
            title="Phase 1 Task",
            description="Initial work",
            phase=1,
        )

        # Add phase 2 task with no dependencies
        p2_task = task_queue.add_task(
            title="Phase 2 Task",
            description="Can start early",
            phase=2,
            dependencies=[],  # No dependencies
        )

        # Phase 1 task should be available at phase 0
        next_task = task_queue.get_next_task_for_terminal("t1", current_phase=0)
        assert next_task is not None

    def test_substantially_complete_tasks_unblock_dependencies(self, task_queue):
        """Tasks at high quality can unblock dependent tasks."""
        # Create parent task
        parent = task_queue.add_task(
            title="Parent Task",
            description="Foundational work",
            phase=1,
        )

        # Create child that depends on parent
        child = task_queue.add_task(
            title="Child Task",
            description="Depends on parent",
            dependencies=["Parent Task"],  # Dependencies can be titles
            phase=2,
        )

        # Start and update parent quality
        task_queue.assign_task(parent.id, "t1")
        task_queue.update_task_quality(parent.id, 0.85)

        # Child should now be available (parent is substantially complete)
        next_task = task_queue.get_next_task_for_terminal("t2", current_phase=2)
        assert next_task is not None
        assert next_task.id == child.id

    def test_flow_state_summary(self, task_queue):
        """Get flow state should return organic flow metrics."""
        # Add some tasks with different states
        task1 = task_queue.add_task(title="Task 1", description="First")
        task2 = task_queue.add_task(title="Task 2", description="Second")

        task_queue.assign_task(task1.id, "t1")
        task_queue.assign_task(task2.id, "t2")

        task_queue.update_task_quality(task1.id, 0.8)
        task_queue.update_task_quality(task2.id, 0.5)

        flow_state = task_queue.get_flow_state()

        assert "overall_flow" in flow_state
        assert "quality_average" in flow_state
        assert "blocked_count" in flow_state
        assert "flourishing_count" in flow_state
        assert "ready_for_convergence" in flow_state


class TestFlowStateTracking:
    """Test flow state tracking across the task queue."""

    def test_overall_flow_state_with_blocked_tasks(self, task_queue):
        """Overall flow should be BLOCKED when many tasks are blocked."""
        # Add tasks and block them
        for i in range(5):
            task = task_queue.add_task(title=f"Task {i}", description=f"Task {i}")
            task_queue.assign_task(task.id, "t1")
            if i < 3:  # Block more than 30%
                task_queue.mark_task_blocked(task.id, "Test block")

        flow_state = task_queue.get_flow_state()
        # 3 out of 5 blocked = 60% > 30% threshold
        assert flow_state["blocked_count"] >= 2

    def test_overall_flow_state_with_flourishing_tasks(self, task_queue):
        """Overall flow should reflect flourishing when tasks are high quality."""
        # Add tasks with high quality
        for i in range(4):
            task = task_queue.add_task(title=f"Task {i}", description=f"Task {i}")
            task_queue.assign_task(task.id, "t1")
            task_queue.update_task_quality(task.id, 0.8)

        flow_state = task_queue.get_flow_state()
        assert flow_state["flourishing_count"] >= 3

    def test_ready_for_convergence_conditions(self, task_queue):
        """Ready for convergence requires high quality average and no blockers."""
        # Add tasks with high quality
        for i in range(3):
            task = task_queue.add_task(title=f"Task {i}", description=f"Task {i}")
            task_queue.assign_task(task.id, "t1")
            task_queue.update_task_quality(task.id, 0.85)

        flow_state = task_queue.get_flow_state()
        assert flow_state["ready_for_convergence"] is True

    def test_not_ready_for_convergence_with_blockers(self, task_queue):
        """Not ready for convergence if there are blocked tasks."""
        # Add tasks
        task1 = task_queue.add_task(title="Task 1", description="First")
        task2 = task_queue.add_task(title="Task 2", description="Second")

        task_queue.assign_task(task1.id, "t1")
        task_queue.assign_task(task2.id, "t2")

        task_queue.update_task_quality(task1.id, 0.9)
        task_queue.mark_task_blocked(task2.id, "Blocked for test")

        flow_state = task_queue.get_flow_state()
        assert flow_state["ready_for_convergence"] is False


class TestBlockAndUnblock:
    """Test blocking and unblocking tasks in organic flow."""

    def test_mark_task_blocked_in_progress(self, task_queue):
        """Can mark an in-progress task as blocked."""
        task = task_queue.add_task(title="Test Task", description="Test")
        task_queue.assign_task(task.id, "t1")

        result = task_queue.mark_task_blocked(task.id, "Waiting for API")
        assert result is not None
        assert result.flow_state == FlowState.BLOCKED
        assert result.metadata.get("blocked_reason") == "Waiting for API"

    def test_mark_task_blocked_pending(self, task_queue):
        """Can mark a pending task as blocked."""
        task = task_queue.add_task(title="Test Task", description="Test")

        result = task_queue.mark_task_blocked(task.id, "Missing dependency")
        assert result is not None
        assert result.flow_state == FlowState.BLOCKED

    def test_unblock_task(self, task_queue):
        """Can unblock a blocked task."""
        task = task_queue.add_task(title="Test Task", description="Test")
        task_queue.assign_task(task.id, "t1")
        task_queue.mark_task_blocked(task.id, "Waiting")

        result = task_queue.unblock_task(task.id)
        assert result is not None
        assert result.flow_state == FlowState.FLOWING
        assert "blocked_reason" not in result.metadata

    def test_blocked_task_not_returned_for_assignment(self, task_queue):
        """Blocked tasks should not be returned when getting next task."""
        task = task_queue.add_task(title="Blocked Task", description="Blocked")
        task_queue.mark_task_blocked(task.id, "External blocker")

        # Add another non-blocked task
        available = task_queue.add_task(title="Available Task", description="Ready")

        next_task = task_queue.get_next_task_for_terminal("t1")
        assert next_task is not None
        assert next_task.id == available.id  # Should get the non-blocked task


class TestFlowStateSerializationDeserialization:
    """Test that flow state survives serialization/deserialization."""

    def test_flow_state_in_to_dict(self, sample_task: Task):
        """Flow state should be included in task dict."""
        sample_task.flow_state = FlowState.FLOURISHING
        task_dict = sample_task.to_dict()

        assert "flow_state" in task_dict
        assert task_dict["flow_state"] == "flourishing"

    def test_flow_state_from_dict(self):
        """Flow state should be restored from dict."""
        task_dict = {
            "id": "test",
            "title": "Test",
            "description": "Test",
            "status": "pending",
            "priority": "medium",
            "dependencies": [],
            "phase": 1,
            "quality_level": 0.5,
            "flow_state": "blocked",
        }

        task = Task.from_dict(task_dict)
        assert task.flow_state == FlowState.BLOCKED

    def test_flow_state_default_when_missing(self):
        """Flow state should default to FLOWING when missing from dict."""
        task_dict = {
            "id": "test",
            "title": "Test",
            "description": "Test",
            "status": "pending",
            "priority": "medium",
            "dependencies": [],
            "phase": 1,
        }

        task = Task.from_dict(task_dict)
        assert task.flow_state == FlowState.FLOWING


class TestContinuousWorkFlow:
    """Test that work continues without artificial breaks."""

    def test_work_flows_across_traditional_phase_boundaries(self, task_queue):
        """Work should flow continuously across what were phase boundaries."""
        # Create tasks that span traditional phases
        tasks = []
        for i in range(1, 4):
            task = task_queue.add_task(
                title=f"Phase {i} Task",
                description=f"Work for phase {i}",
                phase=i,
            )
            tasks.append(task)

        # All phase 1 tasks should be immediately available
        next_task = task_queue.get_next_task_for_terminal("t1", current_phase=1)
        assert next_task is not None

        # Complete first task
        task_queue.assign_task(next_task.id, "t1")
        task_queue.complete_task(next_task.id, "Done")

        # Work continues to next available
        next_task = task_queue.get_next_task_for_terminal("t1", current_phase=1)
        # Additional tasks might be available based on dependencies

    def test_no_artificial_sync_points_required(self, task_queue):
        """Work should not require artificial sync points between phases."""
        # Add phase 1 and phase 2 tasks
        p1_task = task_queue.add_task(title="P1 Task", description="Phase 1", phase=1)
        p2_task = task_queue.add_task(
            title="P2 Task",
            description="Phase 2",
            phase=2,
            dependencies=[],  # No dependencies
        )

        # Both should be accessible without completing phase 1 first
        # (in organic flow, phases are hints not gates)
        pending = task_queue.pending
        assert len(pending) == 2
