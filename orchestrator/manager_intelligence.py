"""
Manager Intelligence - Active Manager for Orchestrator.

Transforms the orchestrator from a passive task distributor into an active manager
that analyzes heartbeats, detects conflicts, and makes coordination decisions in real-time.

This is the core of "Company Mode" - where the orchestrator acts like a CEO managing
engineers, not just a cron job distributing tasks.

## Organic Flow Model (v2.0)

The manager uses 5 intervention types instead of rigid phase transitions:

1. AMPLIFY - Increase resources/attention on flourishing work
2. REDIRECT - Change direction when work is stalled or misaligned
3. MEDIATE - Resolve conflicts between terminals
4. INJECT - Add new work to fill gaps or unblock
5. PRUNE - Remove or deprioritize work that's not valuable

Decisions are based on flow state (flowing/blocked/flourishing/stalled/converging)
rather than phase completion gates.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Literal

from .config import Config, TerminalID
from .report_manager import Report
from .task_queue import Task, TaskQueue, FlowState


# =============================================================================
# Heartbeat Data Structure
# =============================================================================


@dataclass
class TerminalHeartbeat:
    """
    Heartbeat data from a terminal indicating its current state.

    Terminals should update this regularly (every 30-60s) to show:
    - What they're working on
    - What files they're touching
    - Current progress
    - Any blockers
    """

    terminal_id: TerminalID
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    # Current work
    current_task_id: str | None = None
    current_task_title: str | None = None
    progress_percent: int = 0  # 0-100

    # File activity
    files_being_edited: list[str] = field(default_factory=list)
    files_recently_created: list[str] = field(default_factory=list)

    # Status
    is_blocked: bool = False
    blocker_reason: str | None = None

    # Last activity
    last_output_timestamp: str | None = None

    def to_dict(self) -> dict:
        return {
            "terminal_id": self.terminal_id,
            "timestamp": self.timestamp,
            "current_task_id": self.current_task_id,
            "current_task_title": self.current_task_title,
            "progress_percent": self.progress_percent,
            "files_being_edited": self.files_being_edited,
            "files_recently_created": self.files_recently_created,
            "is_blocked": self.is_blocked,
            "blocker_reason": self.blocker_reason,
            "last_output_timestamp": self.last_output_timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TerminalHeartbeat":
        return cls(
            terminal_id=data["terminal_id"],
            timestamp=data.get("timestamp", datetime.now().isoformat()),
            current_task_id=data.get("current_task_id"),
            current_task_title=data.get("current_task_title"),
            progress_percent=data.get("progress_percent", 0),
            files_being_edited=data.get("files_being_edited", []),
            files_recently_created=data.get("files_recently_created", []),
            is_blocked=data.get("is_blocked", False),
            blocker_reason=data.get("blocker_reason"),
            last_output_timestamp=data.get("last_output_timestamp"),
        )

    @property
    def age_seconds(self) -> float:
        """Calculate how old this heartbeat is in seconds."""
        try:
            ts = datetime.fromisoformat(self.timestamp)
            return (datetime.now() - ts).total_seconds()
        except (ValueError, TypeError):
            return 0.0


# =============================================================================
# Manager Actions
# =============================================================================


class ActionType(Enum):
    """
    Types of actions the manager can take.

    ORGANIC FLOW INTERVENTIONS (v2.0):
    - AMPLIFY: Increase resources/attention on flourishing work
    - REDIRECT: Change direction when work is stalled or misaligned
    - MEDIATE: Resolve conflicts between terminals
    - INJECT: Add new work to fill gaps or unblock (same as inject_task)
    - PRUNE: Remove or deprioritize work that's not valuable

    LEGACY ACTIONS (kept for backward compatibility):
    - REORDER_TASKS, PAUSE_TERMINAL, RESUME_TERMINAL, etc.
    """

    # Organic Flow Interventions (v2.0)
    AMPLIFY = "amplify"                      # Increase focus on flourishing work
    REDIRECT = "redirect"                    # Change direction on stalled work
    MEDIATE = "mediate"                      # Resolve conflicts between terminals
    INJECT = "inject"                        # Add new work (alias for inject_task)
    PRUNE = "prune"                          # Remove/deprioritize unproductive work

    # Legacy Actions (backward compatibility)
    REORDER_TASKS = "reorder_tasks"          # Reorder task queue for better flow
    INJECT_TASK = "inject_task"              # Add emergency/unblocking task
    BROADCAST_UPDATE = "broadcast_update"    # Send coordination message to all
    PAUSE_TERMINAL = "pause_terminal"        # Tell terminal to wait
    RESUME_TERMINAL = "resume_terminal"      # Resume paused terminal
    ESCALATE = "escalate"                    # Needs human attention
    TRIGGER_SYNC_POINT = "trigger_sync_point" # Force a synchronization point


@dataclass
class ManagerAction:
    """
    An action the manager intelligence wants to take.

    The orchestrator will execute these actions to coordinate terminals.

    ORGANIC FLOW MODEL (v2.0):
    Actions now include intervention-specific data for the 5 intervention types:
    - AMPLIFY: quality_boost, resource_increase
    - REDIRECT: new_direction, reason_for_redirect
    - MEDIATE: conflict_parties, resolution_approach
    - INJECT: task_title, task_description (same as legacy)
    - PRUNE: task_ids_to_prune, prune_reason
    """

    action_type: ActionType
    reason: str  # Human-readable explanation
    priority: Literal["low", "medium", "high", "critical"] = "medium"

    # Action-specific data
    target_terminal: TerminalID | None = None
    affected_terminals: list[TerminalID] = field(default_factory=list)

    # For INJECT_TASK / INJECT
    task_title: str | None = None
    task_description: str | None = None
    task_intent: str | None = None  # High-level intent for organic model

    # For BROADCAST_UPDATE
    broadcast_message: str | None = None

    # For REORDER_TASKS
    new_task_order: list[str] | None = None  # List of task IDs in desired order

    # Organic Flow Intervention Data (v2.0)
    # For AMPLIFY
    quality_boost: float | None = None  # How much to boost quality expectation
    resource_increase: str | None = None  # Description of resource increase

    # For REDIRECT
    new_direction: str | None = None  # New direction for the work
    redirect_reason: str | None = None  # Why we're redirecting

    # For MEDIATE
    conflict_parties: list[TerminalID] = field(default_factory=list)
    resolution_approach: str | None = None  # How to resolve the conflict

    # For PRUNE
    task_ids_to_prune: list[str] = field(default_factory=list)
    prune_reason: str | None = None

    # Flow state context
    flow_state_before: str | None = None  # Flow state that triggered this action
    expected_flow_state_after: str | None = None  # Expected flow state after action

    # Metadata
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            "action_type": self.action_type.value,
            "reason": self.reason,
            "priority": self.priority,
            "target_terminal": self.target_terminal,
            "affected_terminals": self.affected_terminals,
            "task_title": self.task_title,
            "task_description": self.task_description,
            "task_intent": self.task_intent,
            "broadcast_message": self.broadcast_message,
            "new_task_order": self.new_task_order,
            "quality_boost": self.quality_boost,
            "resource_increase": self.resource_increase,
            "new_direction": self.new_direction,
            "redirect_reason": self.redirect_reason,
            "conflict_parties": self.conflict_parties,
            "resolution_approach": self.resolution_approach,
            "task_ids_to_prune": self.task_ids_to_prune,
            "prune_reason": self.prune_reason,
            "flow_state_before": self.flow_state_before,
            "expected_flow_state_after": self.expected_flow_state_after,
            "created_at": self.created_at,
        }


# =============================================================================
# Conflict Detection
# =============================================================================


@dataclass
class FileConflict:
    """Detected conflict between terminals editing the same file."""

    file_path: str
    terminals: list[TerminalID]
    severity: Literal["low", "medium", "high"] = "medium"

    def __str__(self) -> str:
        terms = ", ".join(self.terminals)
        return f"File conflict: {self.file_path} (terminals: {terms})"


@dataclass
class InterfaceMismatch:
    """Detected mismatch between T1 and T2 interface contracts."""

    component_name: str
    t1_expectation: str
    t2_implementation: str | None
    severity: Literal["low", "medium", "high"] = "medium"

    def __str__(self) -> str:
        if self.t2_implementation:
            return f"Interface mismatch: {self.component_name} - T1 expects '{self.t1_expectation}', T2 provides '{self.t2_implementation}'"
        return f"Missing implementation: {self.component_name} - T1 expects '{self.t1_expectation}', T2 hasn't implemented it"


# =============================================================================
# Manager Intelligence
# =============================================================================


class ManagerIntelligence:
    """
    Active Manager Intelligence for the Orchestrator.

    This class implements the "smart manager" behavior that makes Archon feel like
    a company instead of a task runner. It:

    - Analyzes heartbeats in real-time
    - Detects conflicts between terminals
    - Sends coordination broadcasts
    - Decides when to reorder tasks
    - Detects stalled progress

    ORGANIC FLOW MODEL (v2.0):
    The manager now uses 5 intervention types:
    - AMPLIFY: Increase resources/attention on flourishing work
    - REDIRECT: Change direction when work is stalled or misaligned
    - MEDIATE: Resolve conflicts between terminals
    - INJECT: Add new work to fill gaps or unblock
    - PRUNE: Remove or deprioritize work that's not valuable

    All decisions are made with HEURISTICS (no Claude API calls) to keep it fast
    and cost-free.
    """

    def __init__(self, config: Config, task_queue: TaskQueue):
        self.config = config
        self.task_queue = task_queue

        # Thresholds for detection (all configurable)
        self.stall_threshold_seconds = 180  # 3 minutes without heartbeat = stalled
        self.blocked_threshold_seconds = 120  # 2 minutes blocked = intervention needed
        self.file_conflict_threshold = 2  # Number of terminals editing same file

        # Organic flow thresholds (v2.0)
        self.quality_flourishing_threshold = 0.7  # Quality level to consider flourishing
        self.quality_stalled_threshold = 0.3  # Quality level below which work is stalled
        self.flow_check_interval = 30  # Seconds between flow state checks

        # Decision history (to avoid duplicate actions)
        self._action_history: list[ManagerAction] = []
        self._last_decision_time = datetime.now()
        self._last_flow_check_time = datetime.now()

        # Deduplication tracking (to prevent duplicate actions)
        self._addressed_mismatches: set[str] = set()  # Track addressed interface mismatches
        self._addressed_conflicts: set[str] = set()  # Track addressed file conflicts
        self._triggered_sync_points: set[int] = set()  # Track triggered sync points by phase
        self._injected_task_keys: set[str] = set()  # Track injected task titles
        self._amplified_tasks: set[str] = set()  # Track tasks we've already amplified
        self._redirected_tasks: set[str] = set()  # Track tasks we've already redirected

    # =========================================================================
    # Main Analysis Entry Point
    # =========================================================================

    def analyze_and_decide(
        self,
        heartbeats: dict[TerminalID, TerminalHeartbeat],
        contracts: dict[TerminalID, list[Report]],
        current_phase: int,
    ) -> list[ManagerAction]:
        """
        Analyze current state and decide what actions to take.

        This is the main entry point called by the orchestrator regularly.

        ORGANIC FLOW MODEL (v2.0):
        In addition to legacy checks, this now analyzes flow state and uses
        the 5 intervention types (AMPLIFY, REDIRECT, MEDIATE, INJECT, PRUNE).

        Args:
            heartbeats: Current heartbeat from each terminal
            contracts: Recent reports/contracts from each terminal
            current_phase: Current execution phase (kept for backward compatibility)

        Returns:
            List of actions to take (may be empty if everything is fine)
        """
        actions: list[ManagerAction] = []

        # Get overall flow state
        flow_state = self.task_queue.get_flow_state()

        # ORGANIC FLOW CHECKS (v2.0)
        # These are checked first as they're more holistic

        # Check for flourishing work that should be amplified
        amplify_actions = self._check_for_amplify_opportunities(heartbeats, flow_state)
        actions.extend(amplify_actions)

        # Check for stalled work that should be redirected
        redirect_actions = self._check_for_redirect_opportunities(heartbeats, flow_state)
        actions.extend(redirect_actions)

        # Check for conflicts that need mediation
        mediate_actions = self._check_for_mediation_needs(heartbeats, contracts)
        actions.extend(mediate_actions)

        # Check for pruning opportunities
        prune_actions = self._check_for_prune_opportunities(flow_state)
        actions.extend(prune_actions)

        # LEGACY CHECKS (backward compatibility)

        # 1. Check for stalled terminals
        stalled = self.detect_stalled_terminals(heartbeats)
        for terminal_id in stalled:
            actions.append(ManagerAction(
                action_type=ActionType.ESCALATE,
                reason=f"Terminal {terminal_id} stalled for {self.stall_threshold_seconds}s",
                priority="high",
                target_terminal=terminal_id,
                flow_state_before=flow_state["overall_flow"],
            ))

        # 2. Check for blocked terminals
        blocked = self.detect_blocked_terminals(heartbeats)
        for terminal_id, blocker_reason in blocked:
            # Try to generate an unblocking action
            unblock_action = self._generate_unblock_action(terminal_id, blocker_reason)
            if unblock_action:
                actions.append(unblock_action)

        # 3. Check for file conflicts - with deduplication
        conflicts = self.detect_file_conflicts(heartbeats)
        for conflict in conflicts:
            conflict_key = f"{conflict.file_path}:{'-'.join(sorted(conflict.terminals))}"
            if conflict_key not in self._addressed_conflicts:
                action = self._resolve_file_conflict(conflict)
                if action:
                    actions.append(action)
                    self._addressed_conflicts.add(conflict_key)

        # 4. Check for interface mismatches (T1 vs T2) - with deduplication
        mismatches = self.detect_interface_mismatches(contracts)
        for mismatch in mismatches:
            mismatch_key = f"{mismatch.component_name}:{mismatch.t1_expectation}"
            if mismatch_key not in self._addressed_mismatches:
                action = self._resolve_interface_mismatch(mismatch)
                if action:
                    actions.append(action)
                    self._addressed_mismatches.add(mismatch_key)

        # 5. Check if we should trigger a sync point - with deduplication
        # NOTE: In organic model, sync points are replaced by flow convergence
        if current_phase not in self._triggered_sync_points:
            # Use flow state instead of phase completion
            if flow_state["ready_for_convergence"] or self.should_trigger_sync_point(heartbeats, current_phase):
                actions.append(ManagerAction(
                    action_type=ActionType.TRIGGER_SYNC_POINT,
                    reason=f"Work converging (quality avg: {flow_state['quality_average']})",
                    priority="high",
                    affected_terminals=list(heartbeats.keys()),
                    flow_state_before=flow_state["overall_flow"],
                    expected_flow_state_after=FlowState.CONVERGING.value,
                ))
                self._triggered_sync_points.add(current_phase)

        # 6. Check for task reordering opportunities
        reorder_action = self._check_task_reordering(heartbeats, current_phase)
        if reorder_action:
            actions.append(reorder_action)

        # Store actions in history
        self._action_history.extend(actions)
        self._last_decision_time = datetime.now()

        return actions

    # =========================================================================
    # Organic Flow Interventions (v2.0)
    # =========================================================================

    def _check_for_amplify_opportunities(
        self,
        heartbeats: dict[TerminalID, TerminalHeartbeat],
        flow_state: dict,
    ) -> list[ManagerAction]:
        """
        Check for flourishing work that should be amplified.

        AMPLIFY intervention: Increase resources/attention on work that's
        exceeding expectations to help it reach completion faster.
        """
        actions: list[ManagerAction] = []

        # Find tasks that are flourishing (quality > threshold)
        in_progress = self.task_queue.in_progress
        for task in in_progress:
            if task.id in self._amplified_tasks:
                continue

            if task.quality_level >= self.quality_flourishing_threshold:
                # This task is doing well - amplify it
                actions.append(ManagerAction(
                    action_type=ActionType.AMPLIFY,
                    reason=f"Task '{task.title}' flourishing at {task.quality_level:.0%} quality",
                    priority="medium",
                    target_terminal=task.assigned_to,
                    quality_boost=0.1,  # Aim for 10% more quality
                    resource_increase=f"Prioritize completion of {task.title}",
                    flow_state_before=flow_state["overall_flow"],
                    expected_flow_state_after=FlowState.CONVERGING.value,
                    broadcast_message=f"Great progress on '{task.title}'! Keep the momentum.",
                ))
                self._amplified_tasks.add(task.id)

        return actions

    def _check_for_redirect_opportunities(
        self,
        heartbeats: dict[TerminalID, TerminalHeartbeat],
        flow_state: dict,
    ) -> list[ManagerAction]:
        """
        Check for stalled work that should be redirected.

        REDIRECT intervention: Change direction when work is stalled or
        misaligned with project goals.
        """
        actions: list[ManagerAction] = []

        # Find tasks that are stalled (low quality, long time in progress)
        in_progress = self.task_queue.in_progress
        for task in in_progress:
            if task.id in self._redirected_tasks:
                continue

            # Check if task is stalled
            if task.started_at:
                try:
                    start_time = datetime.fromisoformat(task.started_at)
                    elapsed = (datetime.now() - start_time).total_seconds()

                    # Stalled: low quality AND long time elapsed
                    if task.quality_level < self.quality_stalled_threshold and elapsed > 300:
                        actions.append(ManagerAction(
                            action_type=ActionType.REDIRECT,
                            reason=f"Task '{task.title}' stalled at {task.quality_level:.0%} for {elapsed/60:.1f}m",
                            priority="high",
                            target_terminal=task.assigned_to,
                            new_direction="Simplify approach or break into smaller pieces",
                            redirect_reason=f"Low progress after {elapsed/60:.1f} minutes",
                            flow_state_before=FlowState.STALLED.value,
                            expected_flow_state_after=FlowState.FLOWING.value,
                            broadcast_message=f"Consider simplifying '{task.title}' - breaking it down may help.",
                        ))
                        self._redirected_tasks.add(task.id)
                except (ValueError, TypeError):
                    pass

        return actions

    def _check_for_mediation_needs(
        self,
        heartbeats: dict[TerminalID, TerminalHeartbeat],
        contracts: dict[TerminalID, list[Report]],
    ) -> list[ManagerAction]:
        """
        Check for conflicts that need mediation.

        MEDIATE intervention: Resolve conflicts between terminals through
        coordination rather than just broadcasting warnings.
        """
        actions: list[ManagerAction] = []

        # Check for interface mismatches that indicate deeper conflicts
        mismatches = self.detect_interface_mismatches(contracts)
        if len(mismatches) > 2:
            # Multiple mismatches suggest T1/T2 are not aligned
            actions.append(ManagerAction(
                action_type=ActionType.MEDIATE,
                reason=f"Multiple interface mismatches ({len(mismatches)}) between T1 and T2",
                priority="high",
                conflict_parties=["t1", "t2"],
                resolution_approach="Schedule alignment check - T1 and T2 should review each other's contracts",
                flow_state_before=FlowState.BLOCKED.value,
                expected_flow_state_after=FlowState.FLOWING.value,
                broadcast_message=(
                    "T1 and T2: Please pause and align your interfaces. "
                    "Check .orchestra/contracts/ for the latest expectations."
                ),
            ))

        return actions

    def _check_for_prune_opportunities(
        self,
        flow_state: dict,
    ) -> list[ManagerAction]:
        """
        Check for work that should be pruned.

        PRUNE intervention: Remove or deprioritize work that's not valuable
        or is blocking more important work.
        """
        actions: list[ManagerAction] = []

        # Find low-priority pending tasks when we have blocked high-priority work
        pending = self.task_queue.pending
        blocked_high_priority = [
            t for t in pending
            if t.flow_state == FlowState.BLOCKED and t.priority.value in ["critical", "high"]
        ]

        if blocked_high_priority:
            # Look for low priority tasks that could be pruned
            low_priority_pending = [
                t for t in pending
                if t.priority.value in ["low", "medium"] and t.flow_state != FlowState.BLOCKED
            ]

            if len(low_priority_pending) > 3:
                # Too many low priority tasks - suggest pruning
                task_ids = [t.id for t in low_priority_pending[:2]]
                actions.append(ManagerAction(
                    action_type=ActionType.PRUNE,
                    reason=f"High-priority work blocked while {len(low_priority_pending)} low-priority tasks pending",
                    priority="medium",
                    task_ids_to_prune=task_ids,
                    prune_reason="Deprioritize to focus on blocked high-priority work",
                    flow_state_before=flow_state["overall_flow"],
                    expected_flow_state_after=FlowState.FLOWING.value,
                ))

        return actions

    # =========================================================================
    # Detection: Stalled Terminals
    # =========================================================================

    def detect_stalled_terminals(
        self,
        heartbeats: dict[TerminalID, TerminalHeartbeat],
        threshold_seconds: float | None = None,
    ) -> list[TerminalID]:
        """
        Detect terminals that haven't updated their heartbeat in a while.

        Args:
            heartbeats: Current heartbeats
            threshold_seconds: Override default stall threshold

        Returns:
            List of terminal IDs that appear stalled
        """
        threshold = threshold_seconds or self.stall_threshold_seconds
        stalled: list[TerminalID] = []

        for terminal_id, heartbeat in heartbeats.items():
            if heartbeat.age_seconds > threshold:
                # Terminal hasn't sent heartbeat in a while
                stalled.append(terminal_id)

        return stalled

    # =========================================================================
    # Detection: Blocked Terminals
    # =========================================================================

    def detect_blocked_terminals(
        self,
        heartbeats: dict[TerminalID, TerminalHeartbeat],
    ) -> list[tuple[TerminalID, str]]:
        """
        Detect terminals that report being blocked.

        Returns:
            List of (terminal_id, blocker_reason) tuples
        """
        blocked: list[tuple[TerminalID, str]] = []

        for terminal_id, heartbeat in heartbeats.items():
            if heartbeat.is_blocked:
                reason = heartbeat.blocker_reason or "Unknown blocker"
                blocked.append((terminal_id, reason))

        return blocked

    def _generate_unblock_action(
        self,
        terminal_id: TerminalID,
        blocker_reason: str,
    ) -> ManagerAction | None:
        """
        Generate an action to unblock a terminal.

        Uses heuristics to decide what to do based on the blocker reason.
        """
        blocker_lower = blocker_reason.lower()

        # Waiting for another terminal
        if "waiting" in blocker_lower or "need" in blocker_lower:
            return ManagerAction(
                action_type=ActionType.BROADCAST_UPDATE,
                reason=f"Coordinate: {terminal_id} blocked waiting for dependency",
                priority="high",
                broadcast_message=f"⚠️ {terminal_id.upper()} is blocked: {blocker_reason}\n\n"
                                  f"If you have related work ready, please complete it to unblock {terminal_id.upper()}.",
            )

        # Missing file or component
        if "missing" in blocker_lower or "not found" in blocker_lower:
            return ManagerAction(
                action_type=ActionType.INJECT_TASK,
                reason=f"Create missing dependency for {terminal_id}",
                priority="critical",
                target_terminal=self._guess_responsible_terminal(blocker_reason),
                task_title=f"Unblock {terminal_id}: Create missing dependency",
                task_description=f"Terminal {terminal_id} is blocked because: {blocker_reason}\n\n"
                                 f"Please create the missing file/component to unblock them.",
            )

        # Unknown blocker - escalate
        return ManagerAction(
            action_type=ActionType.ESCALATE,
            reason=f"Terminal {terminal_id} blocked with unclear reason: {blocker_reason}",
            priority="medium",
            target_terminal=terminal_id,
        )

    def _guess_responsible_terminal(self, blocker_reason: str) -> TerminalID:
        """
        Guess which terminal should handle an unblocking task based on keywords.

        Simple heuristic routing.
        """
        blocker_lower = blocker_reason.lower()

        if any(kw in blocker_lower for kw in ["model", "data", "api", "service", "backend"]):
            return "t2"
        if any(kw in blocker_lower for kw in ["ui", "view", "component", "screen"]):
            return "t1"
        if any(kw in blocker_lower for kw in ["doc", "readme", "documentation"]):
            return "t3"
        if any(kw in blocker_lower for kw in ["test", "testing", "verify"]):
            return "t5"

        # Default to T2 (features)
        return "t2"

    # =========================================================================
    # Detection: File Conflicts
    # =========================================================================

    def detect_file_conflicts(
        self,
        heartbeats: dict[TerminalID, TerminalHeartbeat],
    ) -> list[FileConflict]:
        """
        Detect when multiple terminals are editing the same file.

        This is a potential merge conflict or coordination issue.
        """
        file_to_terminals: dict[str, list[TerminalID]] = {}

        # Build map of file -> terminals editing it
        for terminal_id, heartbeat in heartbeats.items():
            for file_path in heartbeat.files_being_edited:
                if file_path not in file_to_terminals:
                    file_to_terminals[file_path] = []
                file_to_terminals[file_path].append(terminal_id)

        # Find conflicts
        conflicts: list[FileConflict] = []
        for file_path, terminals in file_to_terminals.items():
            if len(terminals) >= self.file_conflict_threshold:
                # Multiple terminals editing same file
                severity: Literal["low", "medium", "high"] = "medium"

                # Increase severity for critical files
                if any(critical in file_path.lower() for critical in ["model", "schema", "config", "main"]):
                    severity = "high"

                conflicts.append(FileConflict(
                    file_path=file_path,
                    terminals=terminals,
                    severity=severity,
                ))

        return conflicts

    def _resolve_file_conflict(self, conflict: FileConflict) -> ManagerAction | None:
        """
        Generate action to resolve a file conflict.
        """
        if conflict.severity == "high":
            # Pause one terminal to avoid conflict
            # Pause the one with lower priority (later in the list)
            terminal_to_pause = conflict.terminals[-1]

            return ManagerAction(
                action_type=ActionType.BROADCAST_UPDATE,
                reason=f"File conflict: Multiple terminals editing {conflict.file_path}",
                priority="high",
                affected_terminals=conflict.terminals,
                broadcast_message=f"⚠️ FILE CONFLICT DETECTED\n\n"
                                  f"File: `{conflict.file_path}`\n"
                                  f"Terminals: {', '.join(t.upper() for t in conflict.terminals)}\n\n"
                                  f"Please coordinate to avoid merge conflicts. "
                                  f"{terminal_to_pause.upper()}, consider waiting for others to finish first.",
            )

        # Low/medium severity - just warn
        return ManagerAction(
            action_type=ActionType.BROADCAST_UPDATE,
            reason=f"File being edited by multiple terminals: {conflict.file_path}",
            priority="low",
            affected_terminals=conflict.terminals,
            broadcast_message=f"ℹ️ FYI: `{conflict.file_path}` is being edited by multiple terminals. "
                              f"Coordinate if needed.",
        )

    # =========================================================================
    # Detection: Interface Mismatches (T1 vs T2)
    # =========================================================================

    def detect_interface_mismatches(
        self,
        contracts: dict[TerminalID, list[Report]],
    ) -> list[InterfaceMismatch]:
        """
        Detect mismatches between T1's interface expectations and T2's implementations.

        T1 (UI) defines what APIs/models it needs in its reports.
        T2 (Features) implements those APIs/models.

        This checks if there's a mismatch.
        """
        mismatches: list[InterfaceMismatch] = []

        # Get T1 and T2 reports
        t1_reports = contracts.get("t1", [])
        t2_reports = contracts.get("t2", [])

        # Extract what T1 needs from T2
        t1_needs: dict[str, str] = {}  # component_name -> description
        for report in t1_reports:
            for dep in report.dependencies_needed:
                if dep.get("from") == "t2":
                    component = dep.get("what", "")
                    if component:
                        # Extract component name (simple heuristic)
                        component_name = self._extract_component_name(component)
                        t1_needs[component_name] = component

        # Extract what T2 provides
        t2_provides: set[str] = set()
        for report in t2_reports:
            for comp in report.components_created:
                t2_provides.add(comp.lower())

        # Check for mismatches
        for component_name, description in t1_needs.items():
            # Simple check: is the component name in T2's provides list?
            if component_name.lower() not in t2_provides:
                mismatches.append(InterfaceMismatch(
                    component_name=component_name,
                    t1_expectation=description,
                    t2_implementation=None,
                    severity="medium",
                ))

        return mismatches

    def _extract_component_name(self, description: str) -> str:
        """
        Extract component name from a description.

        E.g., "User model with authentication" -> "User"
        """
        # Simple heuristic: take first capitalized word
        words = description.split()
        for word in words:
            clean = word.strip(".,;:!?'\"")
            if clean and clean[0].isupper():
                return clean
        return description.split()[0] if description else ""

    def _resolve_interface_mismatch(self, mismatch: InterfaceMismatch) -> ManagerAction | None:
        """
        Generate action to resolve an interface mismatch.
        """
        return ManagerAction(
            action_type=ActionType.INJECT_TASK,
            reason=f"Interface mismatch: T1 needs {mismatch.component_name}, T2 hasn't implemented it",
            priority="high",
            target_terminal="t2",
            task_title=f"Implement {mismatch.component_name} for T1",
            task_description=f"T1 (UI) needs: {mismatch.t1_expectation}\n\n"
                             f"Please implement this so T1 can integrate with it.",
        )

    # =========================================================================
    # Detection: Sync Points
    # =========================================================================

    def should_trigger_sync_point(
        self,
        heartbeats: dict[TerminalID, TerminalHeartbeat],
        current_phase: int,
    ) -> bool:
        """
        Decide if we should trigger a sync point (phase transition).

        Sync points occur when:
        - All terminals in current phase have completed their work
        - No terminals are currently busy
        - We have tasks ready for the next phase
        """
        # Check if all terminals are idle or blocked
        all_idle = all(
            hb.current_task_id is None or hb.progress_percent >= 100
            for hb in heartbeats.values()
        )

        if not all_idle:
            return False

        # Check if we have tasks for next phase
        next_phase = current_phase + 1
        if next_phase > 3:
            return False  # No phase after 3

        next_phase_tasks = self.task_queue.get_tasks_by_phase(next_phase)
        if not next_phase_tasks:
            return False  # No tasks for next phase

        # Check if current phase is truly complete
        current_phase_tasks = self.task_queue.get_tasks_by_phase(current_phase)
        pending_current = [t for t in current_phase_tasks if t.status.value != "completed"]

        return len(pending_current) == 0

    # =========================================================================
    # Detection: Task Reordering
    # =========================================================================

    def _check_task_reordering(
        self,
        heartbeats: dict[TerminalID, TerminalHeartbeat],
        current_phase: int,
    ) -> ManagerAction | None:
        """
        Check if we should reorder tasks for better flow.

        Heuristics:
        - If a terminal is idle and has no assigned tasks, but there are unassigned tasks
        - If tasks are blocked by dependencies that can't be resolved yet
        """
        # Get pending tasks
        pending = self.task_queue.pending
        if len(pending) <= 1:
            return None  # Nothing to reorder

        # Check for idle terminals with no assigned work
        idle_terminals = [
            tid for tid, hb in heartbeats.items()
            if hb.current_task_id is None and not hb.is_blocked
        ]

        if not idle_terminals:
            return None  # All terminals busy

        # Check if there are unassigned tasks that could go to idle terminals
        unassigned_tasks = [t for t in pending if t.assigned_to is None]
        if unassigned_tasks:
            # Suggest moving unassigned tasks to front
            new_order = [t.id for t in unassigned_tasks] + [t.id for t in pending if t.assigned_to is not None]

            return ManagerAction(
                action_type=ActionType.REORDER_TASKS,
                reason=f"Idle terminals available: {', '.join(idle_terminals)}. Prioritize unassigned tasks.",
                priority="low",
                affected_terminals=idle_terminals,
                new_task_order=new_order,
            )

        return None

    # =========================================================================
    # Coordination Broadcast Generation
    # =========================================================================

    def generate_coordination_broadcast(
        self,
        situation: str,
        affected_terminals: list[TerminalID] | None = None,
    ) -> str:
        """
        Generate a human-readable coordination broadcast message.

        Args:
            situation: Description of the situation
            affected_terminals: Which terminals are affected (None = all)

        Returns:
            Markdown-formatted broadcast message
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        header = "## 📢 Coordination Update"

        if affected_terminals:
            recipients = ", ".join(t.upper() for t in affected_terminals)
            header += f" (for {recipients})"

        message = f"""{header}

**Time:** {timestamp}

{situation}

---
*From: Orchestrator Manager Intelligence*
"""
        return message

    # =========================================================================
    # Persistence
    # =========================================================================

    def save_heartbeat(self, heartbeat: TerminalHeartbeat) -> None:
        """
        Save a terminal's heartbeat to disk.

        Heartbeats are stored in .orchestra/heartbeats/{terminal_id}.json
        """
        heartbeats_dir = self.config.orchestra_dir / "heartbeats"
        heartbeats_dir.mkdir(exist_ok=True)

        heartbeat_file = heartbeats_dir / f"{heartbeat.terminal_id}.json"
        heartbeat_file.write_text(json.dumps(heartbeat.to_dict(), indent=2))

    def load_heartbeat(self, terminal_id: TerminalID) -> TerminalHeartbeat | None:
        """
        Load a terminal's heartbeat from disk.

        Returns None if no heartbeat exists yet.
        """
        heartbeats_dir = self.config.orchestra_dir / "heartbeats"
        heartbeat_file = heartbeats_dir / f"{terminal_id}.json"

        if not heartbeat_file.exists():
            return None

        try:
            data = json.loads(heartbeat_file.read_text())
            return TerminalHeartbeat.from_dict(data)
        except (json.JSONDecodeError, KeyError):
            return None

    def load_all_heartbeats(self) -> dict[TerminalID, TerminalHeartbeat]:
        """
        Load all terminal heartbeats.

        Returns:
            Dictionary mapping terminal_id to heartbeat (only for terminals with heartbeats)
        """
        heartbeats: dict[TerminalID, TerminalHeartbeat] = {}

        for terminal_id in ["t1", "t2", "t3", "t4", "t5"]:
            heartbeat = self.load_heartbeat(terminal_id)  # type: ignore
            if heartbeat:
                heartbeats[terminal_id] = heartbeat  # type: ignore

        return heartbeats

    def clear_heartbeats(self) -> None:
        """Clear all heartbeat files."""
        heartbeats_dir = self.config.orchestra_dir / "heartbeats"
        if heartbeats_dir.exists():
            for f in heartbeats_dir.glob("*.json"):
                f.unlink()

    # =========================================================================
    # Action History
    # =========================================================================

    def get_recent_actions(self, limit: int = 10) -> list[ManagerAction]:
        """Get recent actions taken by the manager."""
        return self._action_history[-limit:]

    def clear_action_history(self) -> None:
        """Clear action history and deduplication tracking."""
        self._action_history.clear()
        self._addressed_mismatches.clear()
        self._addressed_conflicts.clear()
        self._triggered_sync_points.clear()
        self._injected_task_keys.clear()
        # Organic flow tracking (v2.0)
        self._amplified_tasks.clear()
        self._redirected_tasks.clear()
