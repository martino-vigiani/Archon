"""
Task Queue for managing work distribution across terminals.

Handles task creation, assignment, status tracking, and completion.
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


@dataclass
class Task:
    """A single task to be executed by a terminal."""

    id: str
    title: str
    description: str
    assigned_to: TerminalID | None = None
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.MEDIUM
    dependencies: list[str] = field(default_factory=list)
    phase: int = 1  # 0 = planning, 1 = immediate (no deps), 2 = integration, 3 = testing
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
        return cls(**data)

    def is_ready(self, completed_task_ids: set[str], current_phase: int = 0) -> bool:
        """
        Check if task is ready to execute.

        Phase 0 tasks: Always ready (no blocking dependencies) - Planning phase
        Phase 1 tasks: Ready when Phase 0 completes (or immediately if no Phase 0)
        Phase 2+ tasks: Ready when their phase is reached

        Dependencies are SOFT in parallel execution - they inform but don't block.
        """
        # Phase 0 tasks are always ready - planning phase
        if self.phase == 0:
            return True

        # Phase 1 tasks are always ready - parallel execution
        if self.phase == 1:
            return True

        # Phase 2+ tasks wait for their phase
        if self.phase > current_phase:
            return False

        # Once phase is reached, check dependencies (soft check for awareness)
        return all(dep in completed_task_ids for dep in self.dependencies)


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
    ) -> Task:
        """Add a new task to the queue."""
        task = Task(
            id=self._generate_task_id(),
            title=title,
            description=description,
            priority=priority,
            dependencies=dependencies or [],
            phase=phase,
            assigned_to=assigned_to,
            metadata=metadata or {},
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

        In parallel execution:
        - Phase 0 tasks: Planning and contracts, always available
        - Phase 1 tasks: Always available (no blocking)
        - Phase 2+ tasks: Wait for their phase to be reached
        """
        pending = self.pending
        completed = self.completed
        # Include both IDs and titles for dependency matching
        completed_ids = {t.id for t in completed} | {t.title for t in completed}

        for task in pending:
            # Check if task is assigned to this terminal or unassigned
            if task.assigned_to is not None and task.assigned_to != terminal_id:
                continue

            # Check if task is ready (phase-aware)
            if not task.is_ready(completed_ids, current_phase):
                continue

            return task

        return None

    def get_current_phase(self) -> int:
        """
        Determine the current execution phase based on completed tasks.

        Phase transitions:
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
        """Get a summary of task queue status."""
        pending = self.pending
        in_progress = self.in_progress
        completed = self.completed

        successful = [t for t in completed if t.status == TaskStatus.COMPLETED]
        failed = [t for t in completed if t.status == TaskStatus.FAILED]

        return {
            "pending_count": len(pending),
            "in_progress_count": len(in_progress),
            "completed_count": len(successful),
            "failed_count": len(failed),
            "done_count": len(completed),  # Total finished (success + failed)
            "total_count": len(pending) + len(in_progress) + len(completed),
            "in_progress_tasks": [
                {"id": t.id, "title": t.title, "assigned_to": t.assigned_to}
                for t in in_progress
            ],
            "pending_tasks": [{"id": t.id, "title": t.title} for t in pending[:5]],
        }

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
