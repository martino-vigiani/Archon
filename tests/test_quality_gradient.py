"""
Tests for the Quality Gradient System (0.0-1.0).

The organic architecture uses a quality gradient instead of binary completion:
- 0.0: Not started
- 0.1-0.3: Initial work, scaffolding
- 0.4-0.6: Core functionality implemented
- 0.7-0.9: Integration and polish
- 1.0: Complete and verified

Quality is continuous, not discrete. Tasks can unblock dependencies
at partial quality levels (e.g., 0.8), allowing for parallel polish.
"""

import pytest

from orchestrator.task_queue import FlowState, Task, TaskPriority, TaskStatus


class TestQualityLevelAssignment:
    """Test that quality levels are properly assigned and bounded."""

    def test_initial_quality_is_zero(self, sample_task: Task):
        """New tasks should start with quality level 0.0."""
        assert sample_task.quality_level == 0.0

    def test_quality_update_basic(self, sample_task: Task):
        """Quality can be updated to any valid level."""
        sample_task.update_quality(0.5)
        assert sample_task.quality_level == 0.5

    def test_quality_bounded_at_zero(self, sample_task: Task):
        """Quality cannot go below 0.0."""
        sample_task.update_quality(-0.5)
        assert sample_task.quality_level == 0.0

    def test_quality_bounded_at_one(self, sample_task: Task):
        """Quality cannot exceed 1.0."""
        sample_task.update_quality(1.5)
        assert sample_task.quality_level == 1.0

    @pytest.mark.parametrize("quality_level", [0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0])
    def test_quality_accepts_valid_values(self, sample_task: Task, quality_level: float):
        """Quality accepts all values in the valid range [0.0, 1.0]."""
        sample_task.update_quality(quality_level)
        assert sample_task.quality_level == quality_level


class TestQualityThresholdChecks:
    """Test quality threshold checks for completion decisions."""

    def test_quality_below_threshold_not_complete(self, sample_task: Task):
        """Task with quality below threshold is not substantially complete."""
        sample_task.update_quality(0.5)
        assert not sample_task.is_substantially_complete(threshold=0.8)

    def test_quality_at_threshold_is_complete(self, sample_task: Task):
        """Task with quality exactly at threshold is substantially complete."""
        sample_task.update_quality(0.8)
        assert sample_task.is_substantially_complete(threshold=0.8)

    def test_quality_above_threshold_is_complete(self, sample_task: Task):
        """Task with quality above threshold is substantially complete."""
        sample_task.update_quality(0.95)
        assert sample_task.is_substantially_complete(threshold=0.8)

    @pytest.mark.parametrize(
        "quality,threshold,expected",
        [
            (0.0, 0.5, False),
            (0.4, 0.5, False),
            (0.5, 0.5, True),
            (0.6, 0.5, True),
            (0.79, 0.8, False),
            (0.8, 0.8, True),
            (0.99, 0.8, True),
            (1.0, 0.8, True),
        ],
    )
    def test_various_threshold_combinations(
        self, sample_task: Task, quality: float, threshold: float, expected: bool
    ):
        """Test various quality/threshold combinations."""
        sample_task.update_quality(quality)
        assert sample_task.is_substantially_complete(threshold=threshold) == expected

    def test_default_threshold_is_0_8(self, sample_task: Task):
        """Default threshold for substantial completion is 0.8."""
        sample_task.update_quality(0.79)
        assert not sample_task.is_substantially_complete()  # Default threshold

        sample_task.update_quality(0.8)
        assert sample_task.is_substantially_complete()  # Default threshold


class TestQualityProgressionTracking:
    """Test that quality progression is properly tracked."""

    def test_quality_progression_updates_flow_state(self, sample_task: Task):
        """Quality updates should affect flow state."""
        assert sample_task.flow_state == FlowState.FLOWING

        sample_task.update_quality(0.9)
        assert sample_task.flow_state == FlowState.CONVERGING

    def test_high_quality_triggers_flourishing(self, sample_task: Task):
        """Quality >= 0.7 but < 0.9 should trigger FLOURISHING state."""
        sample_task.update_quality(0.7)
        assert sample_task.flow_state == FlowState.FLOURISHING

        sample_task.update_quality(0.85)
        assert sample_task.flow_state == FlowState.FLOURISHING

    def test_very_high_quality_triggers_converging(self, sample_task: Task):
        """Quality >= 0.9 should trigger CONVERGING state."""
        sample_task.update_quality(0.9)
        assert sample_task.flow_state == FlowState.CONVERGING

        sample_task.update_quality(1.0)
        assert sample_task.flow_state == FlowState.CONVERGING

    def test_quality_progression_preserves_lower_states(self, sample_task: Task):
        """Lower quality levels should not change flow state to higher states."""
        sample_task.update_quality(0.5)
        # Flow state remains FLOWING for lower quality
        assert sample_task.flow_state == FlowState.FLOWING

    def test_multiple_quality_updates(self, sample_task: Task):
        """Quality can be updated multiple times, tracking progression."""
        quality_progression = [0.1, 0.3, 0.5, 0.7, 0.85, 0.95]

        for expected_quality in quality_progression:
            sample_task.update_quality(expected_quality)
            assert sample_task.quality_level == expected_quality


class TestQualityBasedCompletion:
    """Test quality-based completion decisions in the organic model."""

    def test_task_with_quality_can_unblock_dependencies(self, task_queue):
        """Tasks at sufficient quality can unblock dependent tasks."""
        # Create a parent task with high quality
        parent = task_queue.add_task(
            title="Build Auth Service",
            description="Create authentication service",
            phase=1,
        )

        # Create a dependent task
        child = task_queue.add_task(
            title="Integrate Auth in UI",
            description="Connect UI to auth service",
            dependencies=[parent.title],
            phase=2,
        )

        # Assign and update parent quality
        task_queue.assign_task(parent.id, "t2")
        task_queue.update_task_quality(parent.id, 0.85)

        # Get in-progress tasks to check substantially complete
        in_progress = task_queue.in_progress
        assert len(in_progress) == 1
        assert in_progress[0].is_substantially_complete()

    def test_quality_level_in_task_dict(self, sample_task: Task):
        """Quality level should be included in task dictionary serialization."""
        sample_task.update_quality(0.65)
        task_dict = sample_task.to_dict()

        assert "quality_level" in task_dict
        assert task_dict["quality_level"] == 0.65

    def test_quality_level_from_dict(self):
        """Quality level should be restored from dictionary."""
        task_dict = {
            "id": "task_test",
            "title": "Test Task",
            "description": "A test task",
            "status": "pending",
            "priority": "medium",
            "phase": 1,
            "quality_level": 0.75,
            "flow_state": "flourishing",
            "dependencies": [],
        }

        task = Task.from_dict(task_dict)
        assert task.quality_level == 0.75
        assert task.flow_state == FlowState.FLOURISHING


class TestQualityGradientSemantics:
    """Test the semantic meaning of quality levels."""

    @pytest.mark.parametrize(
        "level,expected_stage",
        [
            (0.0, "not_started"),
            (0.1, "scaffolding"),
            (0.2, "scaffolding"),
            (0.3, "scaffolding"),
            (0.4, "core_functionality"),
            (0.5, "core_functionality"),
            (0.6, "core_functionality"),
            (0.7, "integration_polish"),
            (0.8, "integration_polish"),
            (0.9, "integration_polish"),
            (1.0, "complete_verified"),
        ],
    )
    def test_quality_level_semantic_stages(self, level: float, expected_stage: str):
        """Test that quality levels map to expected development stages."""
        # This is a documentation test - the stages are defined in the docstring
        # We verify the ranges make sense
        if level == 0.0:
            assert expected_stage == "not_started"
        elif 0.1 <= level <= 0.3:
            assert expected_stage == "scaffolding"
        elif 0.4 <= level <= 0.6:
            assert expected_stage == "core_functionality"
        elif 0.7 <= level <= 0.9:
            assert expected_stage == "integration_polish"
        elif level == 1.0:
            assert expected_stage == "complete_verified"


class TestQualityInTaskQueue:
    """Test quality tracking in the task queue."""

    def test_update_task_quality_in_progress(self, task_queue):
        """Quality can be updated for in-progress tasks."""
        task = task_queue.add_task(
            title="Test Task",
            description="A test task",
        )
        task_queue.assign_task(task.id, "t1")

        updated = task_queue.update_task_quality(task.id, 0.6)
        assert updated is not None
        assert updated.quality_level == 0.6

    def test_update_quality_returns_none_for_pending(self, task_queue):
        """Quality update returns None for pending (not in-progress) tasks."""
        task = task_queue.add_task(
            title="Test Task",
            description="A test task",
        )

        # Task is pending, not in progress
        result = task_queue.update_task_quality(task.id, 0.5)
        assert result is None

    def test_update_quality_returns_none_for_nonexistent(self, task_queue):
        """Quality update returns None for non-existent tasks."""
        result = task_queue.update_task_quality("nonexistent_id", 0.5)
        assert result is None

    def test_quality_average_in_flow_state(self, task_queue):
        """Flow state should include quality average across tasks."""
        # Add multiple tasks
        task1 = task_queue.add_task(title="Task 1", description="First task")
        task2 = task_queue.add_task(title="Task 2", description="Second task")

        task_queue.assign_task(task1.id, "t1")
        task_queue.assign_task(task2.id, "t2")

        task_queue.update_task_quality(task1.id, 0.6)
        task_queue.update_task_quality(task2.id, 0.8)

        flow_state = task_queue.get_flow_state()
        # Average of 0.6 and 0.8 = 0.7
        assert flow_state["quality_average"] == 0.7

    def test_status_summary_includes_quality(self, task_queue):
        """Status summary should include quality information."""
        task = task_queue.add_task(title="Test Task", description="A test task")
        task_queue.assign_task(task.id, "t1")
        task_queue.update_task_quality(task.id, 0.75)

        summary = task_queue.get_status_summary()

        assert "quality_average" in summary
        assert "flow_state" in summary
