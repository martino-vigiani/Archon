"""
Task Queue for managing work distribution across terminals.

Handles task creation, assignment, status tracking, and completion.

## Organic Flow Model (v2.0)

This module supports both the legacy phase-based model and the new organic flow model.

### Legacy Model (deprecated but supported):
- Tasks have `phase` (0-3) that gates execution
- Phase transitions happen when all tasks in a phase complete
- Rigid sequential progression

### Organic Flow Model:
- Tasks have `quality_level` (0.0-1.0) instead of binary completion
- Work flows based on dependencies and terminal availability
- Manager uses interventions (AMPLIFY, REDIRECT, MEDIATE, INJECT, PRUNE) to guide flow
- Terminals interpret intent rather than receiving rigid assignments
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Literal

from .config import Config, TerminalID


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class TaskPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FlowState(str, Enum):
    """
    Organic flow states for tasks and terminals.

    Unlike the rigid phase model, flow states describe the current
    health of work rather than sequential progression.
    """
    FLOWING = "flowing"       # Work progressing normally
    BLOCKED = "blocked"       # Work stopped due to dependency
    FLOURISHING = "flourishing"  # Work exceeding expectations
    STALLED = "stalled"       # Work slow/stuck without clear blocker
    CONVERGING = "converging" # Work approaching completion


@dataclass
class Task:
    """
    A single task to be executed by a terminal.

    Supports both legacy phase model and new organic flow model:
    - Legacy: Uses `phase` (0-3) to gate execution
    - Organic: Uses `quality_level` (0.0-1.0) and `flow_state` for continuous tracking
    """

    id: str
    title: str
    description: str
    assigned_to: TerminalID | None = None
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.MEDIUM
    dependencies: list[str] = field(default_factory=list)

    # Legacy phase field (deprecated, kept for backward compatibility)
    # 0 = planning, 1 = immediate (no deps), 2 = integration, 3 = testing
    phase: int = 1

    # Organic Flow Model fields (v2.0)
    quality_level: float = 0.0  # 0.0 = not started, 1.0 = complete, values in between = partial
    flow_state: FlowState = FlowState.FLOWING
    intent: str | None = None  # High-level intent/goal for the task (organic planning)

    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: str | None = None
    completed_at: str | None = None
    result: str | None = None
    error: str | None = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "assigned_to": self.assigned_to,
            "status": self.status.value,
            "priority": self.priority.value,
            "dependencies": self.dependencies,
            "phase": self.phase,
            "quality_level": self.quality_level,
            "flow_state": self.flow_state.value,
            "intent": self.intent,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "result": self.result,
            "error": self.error,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        data["status"] = TaskStatus(data["status"])
        data["priority"] = TaskPriority(data["priority"])
        # Handle older tasks without phase field
        if "phase" not in data:
            data["phase"] = 1
        # Handle older tasks without organic flow fields
        if "quality_level" not in data:
            data["quality_level"] = 0.0
        if "flow_state" not in data:
            data["flow_state"] = FlowState.FLOWING
        elif isinstance(data["flow_state"], str):
            data["flow_state"] = FlowState(data["flow_state"])
        if "intent" not in data:
            data["intent"] = None
        return cls(**data)

    def is_ready(self, completed_task_ids: set[str], current_phase: int = 0) -> bool:
        """
        Check if task is ready to execute.

        ORGANIC FLOW MODEL (v2.0):
        Tasks are ready when their dependencies are met AND a terminal is available.
        There are no phase gates - work flows based on readiness and availability.

        LEGACY BEHAVIOR (for backward compatibility):
        The phase parameter is still accepted but only used for soft prioritization.
        Phase 0/1 tasks: Always ready (no blocking dependencies)
        Phase 2+ tasks: Check dependencies

        Dependencies are SOFT in parallel execution - they inform but don't block
        initial work. Tasks can start with mock data and integrate later.
        """
        # ORGANIC: Check flow state - blocked tasks are not ready
        if self.flow_state == FlowState.BLOCKED:
            return False

        # ORGANIC: Check dependencies (soft check - can still start with partial deps)
        # A task is fully ready if all deps are met
        deps_met = all(dep in completed_task_ids for dep in self.dependencies)

        # LEGACY COMPATIBILITY: Phase 0/1 are always ready for initial work
        if self.phase <= 1:
            return True

        # Phase 2+ tasks prefer dependencies to be met, but we use soft blocking
        # If current_phase >= task.phase, allow the task to start
        if current_phase >= self.phase:
            return deps_met

        return False

    def update_quality(self, new_level: float) -> None:
        """
        Update the quality level of this task.

        Quality is a gradient (0.0-1.0) not a binary:
        - 0.0: Not started
        - 0.1-0.3: Initial work, scaffolding
        - 0.4-0.6: Core functionality implemented
        - 0.7-0.9: Integration and polish
        - 1.0: Complete and verified
        """
        self.quality_level = max(0.0, min(1.0, new_level))

        # Update flow state based on quality
        if self.quality_level >= 0.9:
            self.flow_state = FlowState.CONVERGING
        elif self.quality_level >= 0.7:
            self.flow_state = FlowState.FLOURISHING

    def is_substantially_complete(self, threshold: float = 0.8) -> bool:
        """
        Check if task is substantially complete (organic model).

        Unlike binary completion, this allows for gradients:
        - A task at 80% quality can unblock dependent tasks
        - Final polish can happen in parallel
        """
        return self.quality_level >= threshold


class TaskQueue:
    """
    Manages the task queue with persistence to .orchestra/tasks/.

    Maintains three files:
    - pending.json: Tasks waiting to be assigned
    - in_progress.json: Tasks currently being worked on
    - completed.json: Finished tasks (success or failure)
    """

    def __init__(self, config: Config):
        self.config = config
        self._task_counter = 0
        self._ensure_files()

    def _ensure_files(self) -> None:
        """Create task files if they don't exist."""
        self.config.ensure_dirs()

        for filename in ["pending.json", "in_progress.json", "completed.json"]:
            filepath = self.config.tasks_dir / filename
            if not filepath.exists():
                filepath.write_text("[]")

    def _load_tasks(self, filename: str) -> list[Task]:
        """Load tasks from a JSON file."""
        filepath = self.config.tasks_dir / filename
        try:
            data = json.loads(filepath.read_text())
            return [Task.from_dict(t) for t in data]
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _save_tasks(self, filename: str, tasks: list[Task]) -> None:
        """Save tasks to a JSON file."""
        filepath = self.config.tasks_dir / filename
        data = [t.to_dict() for t in tasks]
        filepath.write_text(json.dumps(data, indent=2))

    def _generate_task_id(self) -> str:
        """Generate a unique task ID."""
        self._task_counter += 1
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"task_{timestamp}_{self._task_counter:04d}"

    @property
    def pending(self) -> list[Task]:
        return self._load_tasks("pending.json")

    @property
    def in_progress(self) -> list[Task]:
        return self._load_tasks("in_progress.json")

    @property
    def completed(self) -> list[Task]:
        return self._load_tasks("completed.json")

    def add_task(
        self,
        title: str,
        description: str,
        priority: TaskPriority = TaskPriority.MEDIUM,
        dependencies: list[str] | None = None,
        assigned_to: TerminalID | None = None,
        metadata: dict | None = None,
        phase: int = 1,
        # Organic flow model parameters (v2.0)
        intent: str | None = None,
        quality_target: float = 1.0,
    ) -> Task:
        """
        Add a new task to the queue.

        ORGANIC FLOW MODEL (v2.0):
        Tasks can now include intent and quality_target for organic planning.
        """
        task = Task(
            id=self._generate_task_id(),
            title=title,
            description=description,
            priority=priority,
            dependencies=dependencies or [],
            phase=phase,
            assigned_to=assigned_to,
            metadata=metadata or {},
            # Organic flow model fields (v2.0)
            intent=intent,
            quality_level=0.0,  # Start at 0, progress tracked during execution
            flow_state=FlowState.FLOWING,
        )

        pending = self.pending
        pending.append(task)

        # Sort by priority
        priority_order = {
            TaskPriority.CRITICAL: 0,
            TaskPriority.HIGH: 1,
            TaskPriority.MEDIUM: 2,
            TaskPriority.LOW: 3,
        }
        pending.sort(key=lambda t: priority_order[t.priority])

        self._save_tasks("pending.json", pending)
        return task

    def add_tasks(self, tasks: list[dict]) -> list[Task]:
        """Add multiple tasks at once."""
        created = []
        for task_data in tasks:
            task = self.add_task(
                title=task_data["title"],
                description=task_data["description"],
                priority=TaskPriority(task_data.get("priority", "medium")),
                dependencies=task_data.get("dependencies", []),
                assigned_to=task_data.get("assigned_to"),
                metadata=task_data.get("metadata", {}),
                phase=task_data.get("phase", 1),
            )
            created.append(task)
        return created

    def get_task(self, task_id: str) -> Task | None:
        """Get a task by ID from any queue."""
        for tasks in [self.pending, self.in_progress, self.completed]:
            for task in tasks:
                if task.id == task_id:
                    return task
        return None

    def get_next_task_for_terminal(
        self,
        terminal_id: TerminalID,
        current_phase: int = 0,
    ) -> Task | None:
        """
        Get the next available task for a specific terminal.

        ORGANIC FLOW MODEL (v2.0):
        Tasks are returned based on:
        1. Assignment (if assigned to this terminal)
        2. Flow state (not blocked)
        3. Dependencies (soft check - can start with partial)
        4. Priority ordering

        The current_phase parameter is kept for backward compatibility
        but no longer gates execution in the organic model.
        """
        pending = self.pending
        completed = self.completed

        # Include both IDs and titles for dependency matching
        completed_ids = {t.id for t in completed} | {t.title for t in completed}

        # Also consider substantially complete tasks (quality >= 0.8) as available dependencies
        for t in self.in_progress:
            if t.is_substantially_complete():
                completed_ids.add(t.id)
                completed_ids.add(t.title)

        for task in pending:
            # Check if task is assigned to this terminal or unassigned
            if task.assigned_to is not None and task.assigned_to != terminal_id:
                continue

            # Check if task is ready (organic flow-aware)
            if not task.is_ready(completed_ids, current_phase):
                continue

            return task

        return None

    def get_current_phase(self) -> int:
        """
        Determine the current execution phase based on completed tasks.

        DEPRECATED: This method exists for backward compatibility.
        The organic flow model uses get_flow_state() instead.

        Legacy phase transitions:
        - Phase 0: Initial state, planning and contracts
        - Phase 1: When Phase 0 completes (or immediately if no Phase 0 tasks)
        - Phase 2: When ALL Phase 1 tasks complete (if Phase 2 tasks exist)
        - Phase 3: When ALL Phase 2 tasks complete (or if no Phase 2 tasks exist)
        """
        completed = self.completed
        pending = self.pending
        in_progress = self.in_progress

        # Get all tasks
        all_tasks = completed + pending + in_progress

        # Count tasks by phase
        phase_0_total = len([t for t in all_tasks if t.phase == 0])
        phase_0_done = len([t for t in completed if t.phase == 0])

        phase_1_total = len([t for t in all_tasks if t.phase == 1])
        phase_1_done = len([t for t in completed if t.phase == 1])

        phase_2_total = len([t for t in all_tasks if t.phase == 2])
        phase_2_done = len([t for t in completed if t.phase == 2])

        phase_3_total = len([t for t in all_tasks if t.phase == 3])

        # Check Phase 0 completion
        phase_0_complete = phase_0_total == 0 or phase_0_done >= phase_0_total

        # Check if Phase 1 is complete
        phase_1_complete = phase_1_total > 0 and phase_1_done >= phase_1_total

        # If Phase 0 not complete, stay in Phase 0
        if not phase_0_complete:
            return 0

        # Phase 3 if:
        # - All Phase 2 done, OR
        # - Phase 1 complete AND no Phase 2 tasks exist
        if phase_2_total > 0 and phase_2_done >= phase_2_total:
            return 3
        if phase_1_complete and phase_2_total == 0 and phase_3_total > 0:
            return 3

        # Phase 2 if Phase 1 complete AND Phase 2 tasks exist
        if phase_1_complete and phase_2_total > 0:
            return 2

        # Phase 1 if Phase 0 is complete
        if phase_0_complete:
            return 1

        return 0

    def get_flow_state(self) -> dict:
        """
        Get the current organic flow state of the task queue.

        ORGANIC FLOW MODEL (v2.0):
        Instead of discrete phases, returns a holistic view of work flow:
        - overall_flow: The dominant flow state across all tasks
        - quality_average: Average quality level of all tasks
        - blocked_count: Number of blocked tasks
        - flourishing_count: Number of tasks exceeding expectations
        - ready_for_convergence: Whether work is ready to converge/complete
        """
        all_tasks = self.pending + self.in_progress + self.completed

        if not all_tasks:
            return {
                "overall_flow": FlowState.FLOWING.value,
                "quality_average": 0.0,
                "blocked_count": 0,
                "flourishing_count": 0,
                "ready_for_convergence": False,
            }

        # Calculate quality average
        quality_sum = sum(t.quality_level for t in all_tasks)
        quality_avg = quality_sum / len(all_tasks)

        # Count flow states
        blocked_count = len([t for t in all_tasks if t.flow_state == FlowState.BLOCKED])
        flourishing_count = len([t for t in all_tasks if t.flow_state == FlowState.FLOURISHING])
        stalled_count = len([t for t in all_tasks if t.flow_state == FlowState.STALLED])
        converging_count = len([t for t in all_tasks if t.flow_state == FlowState.CONVERGING])

        # Determine overall flow state
        if blocked_count > len(all_tasks) * 0.3:
            overall_flow = FlowState.BLOCKED
        elif stalled_count > len(all_tasks) * 0.3:
            overall_flow = FlowState.STALLED
        elif converging_count > len(all_tasks) * 0.5:
            overall_flow = FlowState.CONVERGING
        elif flourishing_count > len(all_tasks) * 0.3:
            overall_flow = FlowState.FLOURISHING
        else:
            overall_flow = FlowState.FLOWING

        # Ready for convergence when quality average is high and no blockers
        ready_for_convergence = quality_avg >= 0.7 and blocked_count == 0

        return {
            "overall_flow": overall_flow.value,
            "quality_average": round(quality_avg, 2),
            "blocked_count": blocked_count,
            "flourishing_count": flourishing_count,
            "stalled_count": stalled_count,
            "converging_count": converging_count,
            "ready_for_convergence": ready_for_convergence,
        }

    def get_sync_point_status(self) -> dict:
        """
        Get status for sync point decision making.

        Returns:
            Dictionary with phase completion status
        """
        completed = self.completed
        pending = self.pending
        in_progress = self.in_progress

        all_tasks = completed + pending + in_progress

        status = {}
        for phase in [0, 1, 2, 3]:
            phase_total = len([t for t in all_tasks if t.phase == phase])
            phase_done = len([t for t in completed if t.phase == phase])
            phase_in_progress = len([t for t in in_progress if t.phase == phase])
            phase_pending = len([t for t in pending if t.phase == phase])

            status[f"phase_{phase}"] = {
                "total": phase_total,
                "done": phase_done,
                "in_progress": phase_in_progress,
                "pending": phase_pending,
                "complete": phase_total > 0 and phase_done >= phase_total,
            }

        status["current_phase"] = self.get_current_phase()

        return status

    def get_tasks_by_phase(self, phase: int) -> list[Task]:
        """Get all pending tasks for a specific phase."""
        return [t for t in self.pending if t.phase == phase]

    def assign_task(self, task_id: str, terminal_id: TerminalID) -> Task | None:
        """Assign a task to a terminal and move to in_progress."""
        pending = self.pending
        in_progress = self.in_progress

        task = None
        for i, t in enumerate(pending):
            if t.id == task_id:
                task = pending.pop(i)
                break

        if task is None:
            return None

        task.assigned_to = terminal_id
        task.status = TaskStatus.IN_PROGRESS
        task.started_at = datetime.now().isoformat()

        in_progress.append(task)

        self._save_tasks("pending.json", pending)
        self._save_tasks("in_progress.json", in_progress)

        return task

    def complete_task(
        self,
        task_id: str,
        result: str | None = None,
        success: bool = True,
        error: str | None = None,
    ) -> Task | None:
        """Mark a task as completed and move to completed queue."""
        in_progress = self.in_progress
        completed = self.completed

        task = None
        for i, t in enumerate(in_progress):
            if t.id == task_id:
                task = in_progress.pop(i)
                break

        if task is None:
            return None

        task.status = TaskStatus.COMPLETED if success else TaskStatus.FAILED
        task.completed_at = datetime.now().isoformat()
        task.result = result
        task.error = error

        completed.append(task)

        self._save_tasks("in_progress.json", in_progress)
        self._save_tasks("completed.json", completed)

        return task

    def get_terminal_current_task(self, terminal_id: TerminalID) -> Task | None:
        """Get the task currently assigned to a terminal."""
        for task in self.in_progress:
            if task.assigned_to == terminal_id:
                return task
        return None

    def get_status_summary(self) -> dict:
        """
        Get a summary of task queue status.

        Includes both legacy phase info and organic flow state.
        """
        pending = self.pending
        in_progress = self.in_progress
        completed = self.completed

        successful = [t for t in completed if t.status == TaskStatus.COMPLETED]
        failed = [t for t in completed if t.status == TaskStatus.FAILED]

        # Get organic flow state
        flow_state = self.get_flow_state()

        return {
            "pending_count": len(pending),
            "in_progress_count": len(in_progress),
            "completed_count": len(successful),
            "failed_count": len(failed),
            "done_count": len(completed),  # Total finished (success + failed)
            "total_count": len(pending) + len(in_progress) + len(completed),
            "in_progress_tasks": [
                {"id": t.id, "title": t.title, "assigned_to": t.assigned_to, "quality_level": t.quality_level}
                for t in in_progress
            ],
            "pending_tasks": [{"id": t.id, "title": t.title} for t in pending[:5]],
            # Organic flow model additions
            "flow_state": flow_state,
            "quality_average": flow_state["quality_average"],
        }

    def update_task_quality(self, task_id: str, quality_level: float) -> Task | None:
        """
        Update the quality level of a task (organic flow model).

        Quality is a gradient (0.0-1.0) allowing partial progress tracking.
        """
        # Check in_progress first
        in_progress = self.in_progress
        for task in in_progress:
            if task.id == task_id:
                task.update_quality(quality_level)
                self._save_tasks("in_progress.json", in_progress)
                return task

        return None

    def mark_task_blocked(self, task_id: str, reason: str | None = None) -> Task | None:
        """
        Mark a task as blocked (organic flow model).
        """
        in_progress = self.in_progress
        for task in in_progress:
            if task.id == task_id:
                task.flow_state = FlowState.BLOCKED
                if reason:
                    task.metadata["blocked_reason"] = reason
                self._save_tasks("in_progress.json", in_progress)
                return task

        pending = self.pending
        for task in pending:
            if task.id == task_id:
                task.flow_state = FlowState.BLOCKED
                if reason:
                    task.metadata["blocked_reason"] = reason
                self._save_tasks("pending.json", pending)
                return task

        return None

    def unblock_task(self, task_id: str) -> Task | None:
        """
        Unblock a task (organic flow model).
        """
        in_progress = self.in_progress
        for task in in_progress:
            if task.id == task_id:
                task.flow_state = FlowState.FLOWING
                task.metadata.pop("blocked_reason", None)
                self._save_tasks("in_progress.json", in_progress)
                return task

        pending = self.pending
        for task in pending:
            if task.id == task_id:
                task.flow_state = FlowState.FLOWING
                task.metadata.pop("blocked_reason", None)
                self._save_tasks("pending.json", pending)
                return task

        return None

    def clear_all(self) -> None:
        """Clear all task queues."""
        self._save_tasks("pending.json", [])
        self._save_tasks("in_progress.json", [])
        self._save_tasks("completed.json", [])
        self._task_counter = 0

    def is_all_done(self) -> bool:
        """Check if all tasks are completed."""
        return len(self.pending) == 0 and len(self.in_progress) == 0

    def cancel_task(self, task_id: str) -> Task | None:
        """
        Cancel a pending task by removing it from the queue.

        Args:
            task_id: ID of the task to cancel

        Returns:
            The cancelled Task if found, None if not found or already in progress
        """
        pending = self.pending

        for i, task in enumerate(pending):
            if task.id == task_id:
                cancelled = pending.pop(i)
                self._save_tasks("pending.json", pending)
                return cancelled

        return None
