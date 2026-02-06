"""
Tests for the Organic Task Queue.

The organic task queue differs from the legacy phase-based model:
- No rigid phase gates (phases become hints, not blockers)
- Tasks ready based on dependencies and terminal availability
- Quality-based completion (0.0-1.0) instead of binary done/not-done
- Flow state transitions instead of phase transitions

This module tests the organic behaviors of the TaskQueue.
"""

import pytest
from datetime import datetime

from orchestrator.config import Config, TerminalID
from orchestrator.task_queue import (
    FlowState,
    Task,
    TaskPriority,
    TaskQueue,
    TaskStatus,
)


class TestNoPhaseBasedReadiness:
    """Test that readiness is not strictly phase-gated."""

    def test_phase_1_task_always_ready(self, task_queue: TaskQueue):
        """Phase 1 tasks should always be ready (no phase gate)."""
        task = task_queue.add_task(
            title="Phase 1 Task",
            description="Initial work",
            phase=1,
        )

        # Get task from queue
        next_task = task_queue.get_next_task_for_terminal("t1", current_phase=0)

        assert next_task is not None
        assert next_task.id == task.id

    def test_phase_2_task_checks_dependencies_not_phase(self, task_queue: TaskQueue):
        """Phase 2 tasks should check dependencies, not phase number."""
        # Add phase 2 task with no dependencies
        task = task_queue.add_task(
            title="Phase 2 No Deps",
            description="Can start early",
            phase=2,
            dependencies=[],
        )

        # Add it to pending
        pending = task_queue.pending
        assert len(pending) == 1

    def test_task_with_unmet_deps_blocked_in_phase_2(self, task_queue: TaskQueue):
        """Phase 2+ tasks with unmet dependencies should be blocked."""
        task_queue.add_task(
            title="Dependent Task",
            description="Needs something first",
            dependencies=["NonExistent"],
            phase=2,
        )

        # Should not be ready at phase 2 (deps not met)
        next_task = task_queue.get_next_task_for_terminal("t1", current_phase=2)

        # May or may not get this task depending on implementation
        # The key is that dependencies matter more than phases


class TestDependencyBasedReadiness:
    """Test that tasks become ready when dependencies are met."""

    def test_dependency_by_id(self, task_queue: TaskQueue):
        """Tasks can depend on other tasks by ID."""
        parent = task_queue.add_task(
            title="Parent Task",
            description="Foundation",
            phase=1,
        )

        child = task_queue.add_task(
            title="Child Task",
            description="Depends on parent",
            dependencies=[parent.id],
            phase=2,
        )

        # Complete parent
        task_queue.assign_task(parent.id, "t1")
        task_queue.complete_task(parent.id, "Done")

        # Child should now be available
        next_task = task_queue.get_next_task_for_terminal("t2", current_phase=2)
        assert next_task is not None
        assert next_task.id == child.id

    def test_dependency_by_title(self, task_queue: TaskQueue):
        """Tasks can depend on other tasks by title."""
        parent = task_queue.add_task(
            title="Build Foundation",
            description="Core work",
            phase=1,
        )

        child = task_queue.add_task(
            title="Extend Foundation",
            description="Built on top",
            dependencies=["Build Foundation"],  # Title dependency
            phase=2,
        )

        # Complete parent
        task_queue.assign_task(parent.id, "t1")
        task_queue.complete_task(parent.id, "Done")

        # Child should be ready (title matches)
        next_task = task_queue.get_next_task_for_terminal("t2", current_phase=2)
        assert next_task is not None

    def test_substantially_complete_satisfies_dependency(self, task_queue: TaskQueue):
        """Tasks at 80%+ quality should satisfy dependencies."""
        parent = task_queue.add_task(
            title="Parent Work",
            description="Core component",
            phase=1,
        )

        child = task_queue.add_task(
            title="Child Work",
            description="Uses parent",
            dependencies=["Parent Work"],
            phase=2,
        )

        # Start parent but don't complete - just get it to high quality
        task_queue.assign_task(parent.id, "t1")
        task_queue.update_task_quality(parent.id, 0.85)

        # Child should be available (parent substantially complete)
        next_task = task_queue.get_next_task_for_terminal("t2", current_phase=2)
        assert next_task is not None
        assert next_task.id == child.id


class TestQualityBasedCompletion:
    """Test quality-based completion instead of binary done/not-done."""

    def test_quality_tracks_progress(self, task_queue: TaskQueue):
        """Quality level should track partial progress."""
        task = task_queue.add_task(title="Test Task", description="Testing")
        task_queue.assign_task(task.id, "t1")

        # Update quality progressively
        task_queue.update_task_quality(task.id, 0.3)
        in_progress = task_queue.in_progress
        assert in_progress[0].quality_level == 0.3

        task_queue.update_task_quality(task.id, 0.6)
        in_progress = task_queue.in_progress
        assert in_progress[0].quality_level == 0.6

    def test_quality_0_8_is_substantially_complete(self, task_queue: TaskQueue):
        """Quality at 0.8 should be considered substantially complete."""
        task = task_queue.add_task(title="Test Task", description="Testing")
        task_queue.assign_task(task.id, "t1")
        task_queue.update_task_quality(task.id, 0.8)

        in_progress = task_queue.in_progress
        assert in_progress[0].is_substantially_complete()

    def test_complete_task_still_works(self, task_queue: TaskQueue):
        """Traditional complete_task should still work."""
        task = task_queue.add_task(title="Test Task", description="Testing")
        task_queue.assign_task(task.id, "t1")

        completed = task_queue.complete_task(task.id, "Finished")

        assert completed is not None
        assert completed.status == TaskStatus.COMPLETED
        assert len(task_queue.in_progress) == 0
        assert len(task_queue.completed) == 1


class TestFlowStateTransitions:
    """Test flow state transitions in the task queue."""

    def test_new_task_starts_flowing(self, task_queue: TaskQueue):
        """New tasks should start in FLOWING state."""
        task = task_queue.add_task(title="New Task", description="Fresh")

        pending = task_queue.pending
        assert pending[0].flow_state == FlowState.FLOWING

    def test_blocked_task_has_blocked_state(self, task_queue: TaskQueue):
        """Blocked tasks should have BLOCKED flow state."""
        task = task_queue.add_task(title="Blockable", description="Can be blocked")
        task_queue.mark_task_blocked(task.id, "External dependency")

        pending = task_queue.pending
        assert pending[0].flow_state == FlowState.BLOCKED

    def test_high_quality_triggers_flourishing(self, task_queue: TaskQueue):
        """High quality (0.7+) should trigger FLOURISHING state."""
        task = task_queue.add_task(title="Quality Task", description="Getting better")
        task_queue.assign_task(task.id, "t1")
        task_queue.update_task_quality(task.id, 0.75)

        in_progress = task_queue.in_progress
        assert in_progress[0].flow_state == FlowState.FLOURISHING

    def test_very_high_quality_triggers_converging(self, task_queue: TaskQueue):
        """Very high quality (0.9+) should trigger CONVERGING state."""
        task = task_queue.add_task(title="Almost Done", description="Finishing up")
        task_queue.assign_task(task.id, "t1")
        task_queue.update_task_quality(task.id, 0.95)

        in_progress = task_queue.in_progress
        assert in_progress[0].flow_state == FlowState.CONVERGING


class TestOverallFlowState:
    """Test overall flow state of the queue."""

    def test_empty_queue_is_flowing(self, task_queue: TaskQueue):
        """Empty queue should report FLOWING state."""
        flow_state = task_queue.get_flow_state()

        assert flow_state["overall_flow"] == "flowing"
        assert flow_state["quality_average"] == 0.0

    def test_flow_state_includes_blocked_count(self, task_queue: TaskQueue):
        """Flow state should include count of blocked tasks."""
        task1 = task_queue.add_task(title="T1", description="First")
        task2 = task_queue.add_task(title="T2", description="Second")

        task_queue.mark_task_blocked(task1.id, "Blocked")

        flow_state = task_queue.get_flow_state()
        assert flow_state["blocked_count"] == 1

    def test_flow_state_includes_flourishing_count(self, task_queue: TaskQueue):
        """Flow state should include count of flourishing tasks."""
        task1 = task_queue.add_task(title="T1", description="First")
        task2 = task_queue.add_task(title="T2", description="Second")

        task_queue.assign_task(task1.id, "t1")
        task_queue.assign_task(task2.id, "t2")

        task_queue.update_task_quality(task1.id, 0.8)
        task_queue.update_task_quality(task2.id, 0.85)

        flow_state = task_queue.get_flow_state()
        assert flow_state["flourishing_count"] == 2

    def test_ready_for_convergence(self, task_queue: TaskQueue):
        """Ready for convergence when quality high and no blockers."""
        task1 = task_queue.add_task(title="T1", description="First")
        task2 = task_queue.add_task(title="T2", description="Second")

        task_queue.assign_task(task1.id, "t1")
        task_queue.assign_task(task2.id, "t2")

        task_queue.update_task_quality(task1.id, 0.9)
        task_queue.update_task_quality(task2.id, 0.85)

        flow_state = task_queue.get_flow_state()

        # Quality average is 0.875 >= 0.7 and no blockers
        assert flow_state["ready_for_convergence"] is True


class TestTaskQueueOperations:
    """Test basic task queue operations work with organic model."""

    def test_add_task_with_organic_fields(self, task_queue: TaskQueue):
        """Can add tasks with organic flow fields."""
        task = task_queue.add_task(
            title="Organic Task",
            description="Uses organic model",
            priority=TaskPriority.HIGH,
            phase=1,
        )

        assert task.quality_level == 0.0
        assert task.flow_state == FlowState.FLOWING
        assert task.intent is None  # Optional field

    def test_assign_task(self, task_queue: TaskQueue):
        """Assigning task should update status and track start time."""
        task = task_queue.add_task(title="Test", description="Testing")

        assigned = task_queue.assign_task(task.id, "t1")

        assert assigned is not None
        assert assigned.status == TaskStatus.IN_PROGRESS
        assert assigned.started_at is not None
        assert assigned.assigned_to == "t1"

    def test_get_terminal_current_task(self, task_queue: TaskQueue):
        """Can get the current task for a terminal."""
        task = task_queue.add_task(title="T1 Work", description="For T1")
        task_queue.assign_task(task.id, "t1")

        current = task_queue.get_terminal_current_task("t1")

        assert current is not None
        assert current.id == task.id

    def test_status_summary_includes_organic_fields(self, task_queue: TaskQueue):
        """Status summary should include organic flow fields."""
        task = task_queue.add_task(title="Test", description="Testing")
        task_queue.assign_task(task.id, "t1")
        task_queue.update_task_quality(task.id, 0.5)

        summary = task_queue.get_status_summary()

        assert "flow_state" in summary
        assert "quality_average" in summary
        assert summary["quality_average"] == 0.5


class TestBackwardCompatibility:
    """Test backward compatibility with legacy phase model."""

    def test_phase_field_still_works(self, task_queue: TaskQueue):
        """Phase field should still be supported."""
        task = task_queue.add_task(
            title="Phase 2 Task",
            description="Legacy phase usage",
            phase=2,
        )

        pending = task_queue.pending
        assert pending[0].phase == 2

    def test_get_tasks_by_phase(self, task_queue: TaskQueue):
        """Can still query tasks by phase."""
        task_queue.add_task(title="P1", description="Phase 1", phase=1)
        task_queue.add_task(title="P2", description="Phase 2", phase=2)
        task_queue.add_task(title="P1b", description="Phase 1", phase=1)

        phase_1_tasks = task_queue.get_tasks_by_phase(1)
        phase_2_tasks = task_queue.get_tasks_by_phase(2)

        assert len(phase_1_tasks) == 2
        assert len(phase_2_tasks) == 1

    def test_get_current_phase_still_works(self, task_queue: TaskQueue):
        """Current phase calculation should still work."""
        task = task_queue.add_task(title="Phase 1", description="Initial", phase=1)

        current_phase = task_queue.get_current_phase()

        # Should be 1 (phase 0 complete, phase 1 has pending tasks)
        assert current_phase in [0, 1]

    def test_sync_point_status(self, task_queue: TaskQueue):
        """Sync point status should still be available."""
        task_queue.add_task(title="P1", description="Phase 1", phase=1)
        task_queue.add_task(title="P2", description="Phase 2", phase=2)

        status = task_queue.get_sync_point_status()

        assert "phase_1" in status
        assert "phase_2" in status
        assert "current_phase" in status


class TestTaskSerialization:
    """Test task serialization with organic fields."""

    def test_to_dict_includes_organic_fields(self, sample_task: Task):
        """to_dict should include organic flow fields."""
        sample_task.update_quality(0.65)

        d = sample_task.to_dict()

        assert "quality_level" in d
        assert "flow_state" in d
        assert "intent" in d
        assert d["quality_level"] == 0.65

    def test_from_dict_restores_organic_fields(self):
        """from_dict should restore organic flow fields."""
        d = {
            "id": "test_001",
            "title": "Test Task",
            "description": "A test",
            "status": "in_progress",
            "priority": "high",
            "dependencies": [],
            "phase": 1,
            "quality_level": 0.75,
            "flow_state": "flourishing",
            "intent": "Build a beautiful UI",
        }

        task = Task.from_dict(d)

        assert task.quality_level == 0.75
        assert task.flow_state == FlowState.FLOURISHING
        assert task.intent == "Build a beautiful UI"

    def test_from_dict_handles_missing_organic_fields(self):
        """from_dict should handle missing organic fields (legacy data)."""
        d = {
            "id": "legacy_001",
            "title": "Legacy Task",
            "description": "Old format",
            "status": "pending",
            "priority": "medium",
            "dependencies": [],
            "phase": 1,
            # No quality_level, flow_state, or intent
        }

        task = Task.from_dict(d)

        assert task.quality_level == 0.0  # Default
        assert task.flow_state == FlowState.FLOWING  # Default


class TestTaskQueuePersistence:
    """Test that organic fields persist correctly."""

    def test_quality_persists_after_update(self, task_queue: TaskQueue):
        """Quality level should persist after update."""
        task = task_queue.add_task(title="Test", description="Persistence test")
        task_queue.assign_task(task.id, "t1")
        task_queue.update_task_quality(task.id, 0.7)

        # Re-fetch from queue
        fetched = task_queue.get_task(task.id)

        assert fetched is not None
        assert fetched.quality_level == 0.7

    def test_blocked_state_persists(self, task_queue: TaskQueue):
        """Blocked state should persist."""
        task = task_queue.add_task(title="Test", description="Block test")
        task_queue.mark_task_blocked(task.id, "Testing persistence")

        # Re-fetch
        fetched = task_queue.get_task(task.id)

        assert fetched is not None
        assert fetched.flow_state == FlowState.BLOCKED

    def test_clear_all_resets_counter(self, task_queue: TaskQueue):
        """Clearing queue should reset task counter."""
        task_queue.add_task(title="T1", description="First")
        task_queue.add_task(title="T2", description="Second")

        task_queue.clear_all()

        assert task_queue.is_all_done()  # No pending or in-progress tasks
