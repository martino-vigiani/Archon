"""
Main Orchestrator - Coordinates all terminals and manages the workflow.

This is the central controller that:
- Manages 5 model-backed terminal workers (T1-T5)
- Distributes tasks via the TaskQueue
- Handles inter-terminal communication via MessageBus
- Monitors progress and handles failures
- Supports retry logic for failed tasks
- Implements continuous mode for long-running sessions
- Performs quality checks after task completion
- Provides colorful terminal output with progress tracking
- Gracefully recovers from terminal errors
"""

import asyncio
import contextlib
import fcntl
import json
import os
import signal
from datetime import datetime
from pathlib import Path

from . import metrics, sessions
from .cli_display import Colors
from .config import Config, TerminalID
from .contract_manager import ContractManager
from .control import ControlChannel
from .dynamic_agents import AgentSpec, derive_agents, route_to_agent
from .execution import ExecutionProfile, classify_task, profile_for_kind
from .logger import EventLogger
from .manager_intelligence import ActionType, ManagerAction, ManagerIntelligence, TerminalHeartbeat
from .message_bus import MessageBus
from .planner import Planner, TaskPlan
from .report_manager import Report, ReportManager
from .session_log import SessionLog
from .sync_manager import SyncManager
from .task_queue import FlowState, Task, TaskPriority, TaskQueue, TaskStatus
from .terminal import Terminal, TerminalState

# =============================================================================
# Progress Bar (optional tqdm integration)
# =============================================================================

try:
    from tqdm import tqdm

    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False


class ProgressTracker:
    """Track progress with optional tqdm integration."""

    def __init__(self, total: int, description: str = "Tasks", use_tqdm: bool = True):
        self.total = total
        self.completed = 0
        self.failed = 0
        self.description = description
        self.use_tqdm = use_tqdm and TQDM_AVAILABLE
        self._pbar = None

        if self.use_tqdm and total > 0:
            self._pbar = tqdm(
                total=total,
                desc=description,
                bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]",
                colour="green",
            )

    def update(self, success: bool = True):
        """Update progress."""
        if success:
            self.completed += 1
        else:
            self.failed += 1

        if self._pbar:
            self._pbar.update(1)
            if not success:
                self._pbar.colour = "yellow" if self.failed < self.total // 2 else "red"

    def close(self):
        """Close progress bar."""
        if self._pbar:
            self._pbar.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


# =============================================================================
# Retry Configuration
# =============================================================================


class RetryConfig:
    """Configuration for retry behavior."""

    def __init__(
        self,
        max_retries: int = 2,
        retry_delay: float = 2.0,
        exponential_backoff: bool = False,
    ):
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.exponential_backoff = exponential_backoff

    def get_delay(self, attempt: int) -> float:
        """Get delay for a specific retry attempt."""
        if self.exponential_backoff:
            return self.retry_delay * (2**attempt)
        return self.retry_delay


# =============================================================================
# Main Orchestrator
# =============================================================================

# Cap on control-plane-supplied "how-to instructions" merged into a worker's
# system prompt. Bounds an unauthenticated/untrusted injector's influence on the
# prompt size while leaving ample room for legitimate guidance.
_MAX_INSTRUCTIONS_CHARS = 8000


class Orchestrator:
    """
    Main orchestrator that coordinates all components.

    Features:
    - Task distribution across 5 terminals (T1-T5)
    - Retry logic for failed tasks
    - Continuous mode for persistent operation
    - Quality checks after completion
    - Colorful logging with progress tracking
    - Graceful error recovery
    """

    def __init__(
        self,
        config: Config | None = None,
        verbose: bool = True,
        retry_config: RetryConfig | None = None,
        continuous_mode: bool = False,
        enable_quality_check: bool = True,
        use_colors: bool = True,
        use_progress_bar: bool = True,
        max_quality_iterations: int = 1,  # Maximum quality check iterations (prevents infinite loops)
        use_organic_model: bool = False,  # Enable organic flow model (v2.0)
    ):
        self.config = config or Config()
        self.verbose = verbose
        self.retry_config = retry_config or RetryConfig()
        self.continuous_mode = continuous_mode
        self.enable_quality_check = enable_quality_check
        self.use_colors = use_colors
        self.use_progress_bar = use_progress_bar
        self.max_quality_iterations = max_quality_iterations
        self.use_organic_model = use_organic_model  # Organic flow model (v2.0)

        # Disable colors if requested
        if not use_colors:
            Colors.disable()

        # Initialize components
        self.message_bus = MessageBus(self.config)
        self.task_queue = TaskQueue(self.config)
        self.planner = Planner(self.config, use_organic_model=use_organic_model)
        self.report_manager = ReportManager(self.config)
        self.event_logger = EventLogger(self.config.orchestra_dir / "events.json")

        # Company Mode components
        self.sync_manager = SyncManager(self.config)
        self.manager_intelligence = ManagerIntelligence(self.config, self.task_queue)

        # Manager loop control
        self._manager_loop_task: asyncio.Task | None = None
        self._manager_loop_interval = 15.0  # Check every 15 seconds (was 5s)

        # Control-plane loop (dashboard commands)
        self._control_loop_task: asyncio.Task | None = None

        # Terminal instances
        self.terminals: dict[TerminalID, Terminal] = {}

        # Running task futures
        self._running_tasks: dict[TerminalID, asyncio.Task] = {}

        # Pause/Resume control
        self._paused = asyncio.Event()
        self._paused.set()  # Not paused initially (set = not paused)

        # Retry tracking: task_id -> retry_count
        self._retry_counts: dict[str, int] = {}

        # Tasks pending retry
        self._retry_queue: list[tuple[Task, TerminalID]] = []

        # Progress tracker
        self._progress: ProgressTracker | None = None

        # Quality check iteration counter
        self._quality_check_iteration = 0
        self._processed_task_ids: set[str] = set()  # Track already quality-checked tasks

        # Log buffer (flush every N entries or on shutdown)
        self._log_buffer: list[str] = []
        self._log_buffer_max = 20

        # Status dedup (skip writes when unchanged)
        self._last_status_hash: int = 0

        # Per-terminal active execution mode badge (for the dashboard / status snapshot)
        self._terminal_modes: dict[TerminalID, str] = {}

        # Dynamic agent roster (populated only when config.dynamic_agents is on).
        self.agent_roster: list[AgentSpec] = []
        self._dynamic_specs: dict[TerminalID, AgentSpec] = {}

        # Control plane: file-based command bus driven by the dashboard.
        self.control = ControlChannel(self.config.orchestra_dir)
        # Per-worker mode overrides set live via the control plane (set_mode command).
        self._mode_overrides: dict[TerminalID, dict] = {}

        # Total firehose log (F16): one append-only session.jsonl for this run.
        self._session_log = SessionLog(self.config.orchestra_dir)

        # F15: real per-worker progress timestamps (assign / output-save / done).
        # Feeds TerminalHeartbeat.timestamp so a genuine stall actually fires.
        self._last_progress_at: dict[TerminalID, str] = {}
        # Conservative no-progress threshold (seconds) before flagging stuck/needs_input.
        # Long, quiet `claude --print` tasks (MAX effort) buffer all output until they
        # finish, so a busy worker can legitimately emit no progress for several
        # minutes. 600s avoids false "stuck" alarms while still catching a real hang.
        self._stuck_threshold_seconds = 600.0
        # Latest stuck / needs_input snapshot (mirrored into status.json).
        self._stuck: bool = False
        self._needs_input: dict | None = None

        # F11: latest captured prompt record + adherence per worker (status.json).
        self._last_adherence: dict[TerminalID, float] = {}

        # Rate limit tracking
        self._rate_limited = False
        self._rate_limit_reset_time: str | None = None

        # State
        self.is_running = False
        self.start_time: datetime | None = None
        self._shutdown_requested = False

        # Setup signal handlers
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

    def _handle_shutdown(self, _signum, _frame):
        """Handle graceful shutdown on SIGINT/SIGTERM."""
        self._log_warning("Received shutdown signal...")
        self._shutdown_requested = True
        if not self.continuous_mode:
            self.is_running = False

    # =========================================================================
    # Logging Methods with Colors
    # =========================================================================

    def _log(self, message: str, color: str = "", log_type: str = "info"):
        """Log a message if verbose mode is enabled."""
        if self.verbose:
            timestamp = datetime.now().strftime("%H:%M:%S")
            prefix = f"{Colors.DIM}[{timestamp}]{Colors.RESET}"
            print(f"{prefix} {color}{message}{Colors.RESET}")

        # Also write to orchestrator.log file for dashboard
        self._write_to_log_file(message, log_type)

    def _write_to_log_file(self, message: str, log_type: str = "info"):
        """Buffer log entries and flush when buffer is full."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"[{timestamp}] [{log_type.upper()}] {message}\n"
        self._log_buffer.append(entry)

        if len(self._log_buffer) >= self._log_buffer_max:
            self._flush_log_buffer()

    def _flush_log_buffer(self):
        """Flush buffered log entries to disk."""
        if not self._log_buffer:
            return
        log_file = self.config.orchestra_dir / "orchestrator.log"
        entries = "".join(self._log_buffer)
        self._log_buffer.clear()
        try:
            with open(log_file, "a") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                f.write(entries)
                f.flush()
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except (IOError, OSError):
            pass

    def _log_success(self, message: str):
        """Log a success message (green)."""
        self._log(f"{Colors.GREEN}✓{Colors.RESET} {message}", Colors.GREEN, "success")

    def _log_error(self, message: str):
        """Log an error message (red)."""
        self._log(f"{Colors.RED}✗{Colors.RESET} {message}", Colors.RED, "error")

    def _log_warning(self, message: str):
        """Log a warning message (yellow)."""
        self._log(f"{Colors.YELLOW}⚠{Colors.RESET} {message}", Colors.YELLOW, "warning")

    def _log_info(self, message: str):
        """Log an info message (blue)."""
        self._log(f"{Colors.BLUE}ℹ{Colors.RESET} {message}", Colors.BLUE, "info")

    def _log_terminal(self, terminal_id: str, message: str, color: str = ""):
        """Log a terminal-specific message."""
        term_color = {
            "t1": Colors.CYAN,
            "t2": Colors.MAGENTA,
            "t3": Colors.YELLOW,
            "t4": Colors.BLUE,
            "t5": Colors.RED,
        }.get(terminal_id, Colors.WHITE)

        if self.verbose:
            timestamp = datetime.now().strftime("%H:%M:%S")
            prefix = f"{Colors.DIM}[{timestamp}]{Colors.RESET}"
            term_badge = f"{term_color}[{terminal_id}]{Colors.RESET}"
            print(f"{prefix} {term_badge} {color}{message}{Colors.RESET}")

        # Also write to orchestrator.log for dashboard
        self._write_to_log_file(f"[{terminal_id}] {message}", "terminal")

    def _save_terminal_output(self, terminal_id: str, output: str):
        """Save terminal output for dashboard display."""
        terminal_output_dir = self.config.orchestra_dir / "terminal_output"
        terminal_output_dir.mkdir(parents=True, exist_ok=True)
        output_file = terminal_output_dir / f"{terminal_id}.txt"

        timestamp = datetime.now().isoformat()
        entry = f"\n--- [{timestamp}] ---\n{output[:3000]}\n"

        try:
            with open(output_file, "a") as f:
                f.write(entry)
            # Rotate: keep only the tail so the file (which the dashboard reads into
            # memory) cannot grow without bound over a long run. Decode with
            # errors="ignore" before rewriting so a byte-slice never leaves a partial
            # UTF-8 sequence at the head (which would crash the dashboard's read_text).
            max_bytes = 64 * 1024
            if output_file.stat().st_size > max_bytes:
                tail = output_file.read_bytes()[-max_bytes:].decode("utf-8", "ignore")
                output_file.write_text(tail)
        except OSError:
            pass

    def _log_retry(self, terminal_id: str, task_title: str, attempt: int, max_attempts: int):
        """Log a retry attempt."""
        self._log_terminal(
            terminal_id, f"Retry {attempt}/{max_attempts}: {task_title}", Colors.YELLOW
        )

    # =========================================================================
    # Subagent Detection
    # =========================================================================

    def _detect_subagent_usage(self, terminal_id: str, task_title: str, output: str):
        """Detect and log subagent usage from task output."""
        subagents = self.config.get_all_subagents()
        output_lower = output.lower()
        for subagent in subagents:
            if subagent in output_lower or subagent.replace("-", " ") in output_lower:
                self.event_logger.subagent_invoked(terminal_id, subagent, task_title)

    # =========================================================================
    # Initialization
    # =========================================================================

    async def initialize(self) -> None:
        """Initialize the orchestrator and all directories."""
        self._log_info("Initializing orchestrator...")

        # Create directories
        self.config.ensure_dirs()

        # Clear previous state
        self.message_bus.clear_all()
        self.task_queue.clear_all()
        self.report_manager.clear_reports()  # Clear previous reports
        self.event_logger.clear()  # Clear previous events

        # Clear Company Mode state
        self.sync_manager.clear_all_heartbeats()
        self.manager_intelligence.clear_action_history()

        # Clear orchestrator log file
        log_file = self.config.orchestra_dir / "orchestrator.log"
        if log_file.exists():
            log_file.write_text("")

        # Clear terminal outputs
        terminal_output_dir = self.config.orchestra_dir / "terminal_output"
        if terminal_output_dir.exists():
            for f in terminal_output_dir.glob("*.txt"):
                f.write_text("")

        # Clear retry tracking
        self._retry_counts.clear()
        self._retry_queue.clear()

        # Initialize status file
        self._update_status(
            {
                "state": "initializing",
                "terminals": {},
                "tasks": self.task_queue.get_status_summary(),
                "started_at": datetime.now().isoformat(),
            }
        )

        self._log_success("Orchestrator initialized")

    def _update_status(self, status: dict) -> None:
        """Update the status file only if the state has changed.

        Serialized compactly (no indent) — it is machine state polled by the dashboard,
        so smaller payloads mean less IO/RAM each tick.

        The live execution-mode toggles live on the in-process Config and are flipped at
        runtime via the control bus; the dashboard runs in a SEPARATE process, so this file
        is the only channel that can carry their CURRENT truth to the header toggles.
        """
        status["model_tiering"] = self.config.model_tiering
        status["effort_dial"] = self.config.effort_dial
        status["dynamic_agents"] = self.config.dynamic_agents
        data = json.dumps(status, separators=(",", ":"), default=str)
        # The dedup hash must IGNORE per-tick wall-clocks (they change almost every poll
        # and would defeat change-detection, forcing a write every tick). Hash a copy of
        # the payload with the clock fields stripped; still WRITE the full status.
        data_hash = hash(self._status_dedup_key(status))
        if data_hash != self._last_status_hash:
            self._last_status_hash = data_hash
            self.config.status_file.write_text(data)
            # Mirror each distinct status snapshot into the firehose (F16).
            self._session_log.state(status)

    @staticmethod
    def _status_dedup_key(status: dict) -> str:
        """Serialize a status payload for change-detection, excluding wall-clocks.

        ``metrics.elapsed_sec`` and ``metrics.throughput_per_min`` advance on nearly
        every poll, so including them in the dedup hash would force a status write each
        tick. Strip them (and any top-level ``duration_seconds``) from a shallow copy
        before hashing — the full status is still written; only the HASH excludes clocks.

        Args:
            status: The status payload about to be written.

        Returns:
            A compact JSON string of the payload with per-tick clock fields removed.
        """
        dedup = dict(status)
        dedup.pop("duration_seconds", None)
        raw_metrics = dedup.get("metrics")
        if isinstance(raw_metrics, dict):
            trimmed = dict(raw_metrics)
            trimmed.pop("elapsed_sec", None)
            trimmed.pop("throughput_per_min", None)
            dedup["metrics"] = trimmed
        return json.dumps(dedup, separators=(",", ":"), default=str)

    def _get_status(self) -> dict:
        """Get current status."""
        try:
            return json.loads(self.config.status_file.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    # =========================================================================
    # Session Registry (F1, F14)
    # =========================================================================

    def _registry_path(self) -> Path:
        """Resolve the top-level (NON-namespaced) ``sessions.json`` registry path.

        The registry lives at ``<base>/.orchestra/sessions.json`` regardless of
        whether this run uses a namespaced per-session dir
        (``<base>/.orchestra/runs/<id>``) or the legacy ``<base>/.orchestra``.

        Returns:
            Absolute path to the shared ``sessions.json`` registry file.
        """
        orch = Path(self.config.orchestra_dir)
        # Namespaced: .../.orchestra/runs/<id> → registry is two levels up.
        if orch.parent.name == "runs":
            return orch.parent.parent / "sessions.json"
        # Legacy single-session: .../.orchestra → registry sits beside the runs.
        return orch / "sessions.json"

    def _register_session_start(self, goal: str) -> None:
        """Register (or refresh) this run in the shared session registry.

        Mints a session id when the config lacks one, records it back onto the
        config, and writes a ``running`` entry. Best-effort: never raises.

        Args:
            goal: The run's goal text (used for the slug when minting an id).
        """
        try:
            if not self.config.session_id:
                self.config.session_id = sessions.make_session_id(goal)
            # Preserve the project_path the launcher (dashboard /api/runs or __main__'s
            # --project handling) already recorded; only fall back to base_dir when no
            # prior entry exists. Otherwise this clobbers the real target dir with the
            # repo root, which is just where .orchestra lives — not where work happens.
            existing = sessions.read_session(self._registry_path(), self.config.session_id) or {}
            project_path = existing.get("project_path") or str(self.config.base_dir)
            sessions.register_session(
                self._registry_path(),
                {
                    "session_id": self.config.session_id,
                    "goal": goal,
                    "project_path": project_path,
                    "pid": os.getpid(),
                    "status": "running",
                    "started_at": (
                        self.start_time.isoformat()
                        if self.start_time
                        else datetime.now().isoformat()
                    ),
                    "orchestra_dir": str(self.config.orchestra_dir),
                },
            )
        except Exception as e:  # never let registry I/O crash the run
            self._log_warning(f"[session] register failed (non-fatal): {e}")

    def _update_session_status(self, status: str, **fields: object) -> None:
        """Update this run's status in the shared registry (best-effort).

        Args:
            status: New session status (e.g. ``paused``/``running``/``completed``).
            **fields: Extra registry fields to set.
        """
        sid = self.config.session_id
        if not sid:
            return
        try:
            sessions.update_session_status(self._registry_path(), sid, status, **fields)
        except Exception as e:  # never let registry I/O crash the run
            self._log_warning(f"[session] status update failed (non-fatal): {e}")

    # =========================================================================
    # Pause/Resume Control (for Manager Chat)
    # =========================================================================

    async def pause(self) -> None:
        """Pause task execution. Current tasks will complete but no new tasks start."""
        self._paused.clear()
        self._log_warning("Execution PAUSED by user")
        self._update_session_status("paused")

    async def resume(self) -> None:
        """Resume task execution after pause."""
        self._paused.set()
        self._log_success("Execution RESUMED")
        self._update_session_status("running")

    async def inject_task(
        self,
        title: str,
        description: str,
        terminal_id: TerminalID,
        priority: str = "high",
        intent: str | None = None,
    ) -> Task:
        """
        Inject a new task into the queue during execution.

        Args:
            title: Task title
            description: Task description
            terminal_id: Which terminal should handle this
            priority: Task priority (low, medium, high, critical)
            intent: High-level intent (organic flow model)

        Returns:
            The created Task object

        ORGANIC FLOW MODEL (v2.0):
        Injected tasks start in FLOWING state with quality_level 0.0.
        They are not phase-gated - they start based on terminal availability.
        """
        # In organic model, use phase 1 (no phase gating)
        # In legacy model, use current phase
        phase = 1 if self.use_organic_model else self.task_queue.get_current_phase()

        task = self.task_queue.add_task(
            title=title,
            description=description,
            priority=TaskPriority(priority),
            assigned_to=terminal_id,
            phase=phase,
            metadata={
                "injected": True,
                "injected_at": datetime.now().isoformat(),
                "intent": intent,
                "organic_model": self.use_organic_model,
            },
        )

        self._log_info(f"Task injected: {title} -> {terminal_id}")
        self.event_logger.log_event(
            "task_injected",
            {
                "task_id": task.id,
                "title": title,
                "terminal": terminal_id,
            },
        )

        # Update progress tracker if it exists
        if self._progress:
            self._progress.total += 1

        return task

    async def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a pending task.

        Args:
            task_id: ID of the task to cancel

        Returns:
            True if task was cancelled, False if not found or already in progress
        """
        pending = self.task_queue.pending

        for i, task in enumerate(pending):
            if task.id == task_id:
                # Remove from pending
                pending.pop(i)
                self.task_queue._save_tasks("pending.json", pending)

                self._log_warning(f"Task cancelled: {task.title}")
                self.event_logger.log_event(
                    "task_cancelled",
                    {
                        "task_id": task_id,
                        "title": task.title,
                    },
                )
                return True

        return False

    async def _apply_control_commands(self) -> None:
        """Drain and apply control-plane commands from the dashboard (once per tick).

        This is the orchestrator side of the "direct access" surface: pause/resume,
        live task injection (with an optional execution profile), per-worker mode
        overrides (model/effort/plan/agents), and live config toggles.
        """
        for cmd in self.control.drain():
            ctype = cmd.get("type")
            # Mirror every drained command into the firehose before applying it (F16).
            self._session_log.control(cmd)
            try:
                if ctype == "pause":
                    await self.pause()
                elif ctype == "resume":
                    await self.resume()
                elif ctype == "cancel":
                    await self.cancel_task(cmd.get("task_id", ""))
                elif ctype == "inject":
                    target = cmd.get("target")
                    if not target or target not in self.terminals:
                        # Route onto the dynamic roster, else fall back to keyword routing.
                        if self.agent_roster:
                            target = route_to_agent(
                                f"{cmd.get('title','')}\n{cmd.get('description','')}",
                                self.agent_roster,
                            )
                        else:
                            target = self.config.route_task_to_terminal(
                                f"{cmd.get('title','')} {cmd.get('description','')}"
                            )
                    metadata = {"profile": cmd["profile"]} if cmd.get("profile") else None
                    task = self.task_queue.add_task(
                        title=cmd.get("title", "Injected task"),
                        description=cmd.get("description", ""),
                        priority=TaskPriority(cmd.get("priority", "high")),
                        assigned_to=target,
                        phase=1 if self.use_organic_model else self.task_queue.get_current_phase(),
                        metadata={**(metadata or {}), "injected": True},
                    )
                    self._log_info(f"[control] Injected task -> {target}: {task.title}")
                    if self._progress:
                        self._progress.total += 1
                elif ctype == "set_mode":
                    target = cmd.get("target")
                    if target and cmd.get("clear"):
                        self._mode_overrides.pop(target, None)
                        self._log_info(f"[control] Mode override cleared for {target}")
                    elif target and isinstance(cmd.get("profile"), dict):
                        self._mode_overrides[target] = cmd["profile"]
                        self._log_info(f"[control] Mode override for {target}: {cmd['profile']}")
                elif ctype == "set_config":
                    for key in ("model_tiering", "effort_dial", "dynamic_agents"):
                        if key in cmd:
                            setattr(self.config, key, bool(cmd[key]))
                    self._log_info(f"[control] Config updated: {cmd}")
                elif ctype == "spawn_worker":
                    await self._spawn_worker_from_control(cmd)
                elif ctype == "chat":
                    await self._handle_chat_command(cmd)
                elif ctype == "stop":
                    self._log_warning("[control] Stop requested - graceful shutdown")
                    self._shutdown_requested = True
                    if not self.continuous_mode:
                        self.is_running = False
                    self._update_session_status("stopped")
            except Exception as e:  # never let a bad command crash the loop
                self._log_warning(f"[control] Failed to apply {ctype}: {e}")

    def _record_adherence(self, terminal_id: TerminalID, output_text: str, task: Task) -> None:
        """Compute and cache prompt-adherence for a worker's latest output (F11).

        Uses :func:`metrics.adherence_for` over the raw output and the task's
        title/description/deliverables. The result rides status.json so the
        dashboard can badge each worker's output quality. Best-effort.

        Args:
            terminal_id: The worker that produced the output.
            output_text: The worker's raw output text.
            task: The task the output belongs to.
        """
        try:
            task_dict = {
                "title": task.title,
                "description": task.description,
                "metadata": task.metadata or {},
            }
            self._last_adherence[terminal_id] = metrics.adherence_for(None, output_text, task_dict)
        except Exception:  # adherence is advisory — never crash the run
            self._last_adherence[terminal_id] = 0.0

    def _mark_progress(self, terminal_id: TerminalID) -> None:
        """Record that a worker just made real progress (F15).

        Stamps ``last_progress_at`` for the worker with the current time. This is
        what feeds :attr:`TerminalHeartbeat.timestamp` so a genuine stall (no
        assign / output / completion for a while) actually fires, instead of the
        heartbeat resetting to now every tick.

        Args:
            terminal_id: The worker that progressed.
        """
        self._last_progress_at[terminal_id] = datetime.now().isoformat()

    def _compute_stuck_state(self, terminal_snapshot: dict) -> tuple[bool, dict | None]:
        """Derive the run-level ``stuck`` / ``needs_input`` signals (F15).

        A worker that is busy (has a current task) but has made no real progress
        (assign / output / completion) for longer than
        :attr:`_stuck_threshold_seconds` is considered stalled. The whole run is
        ``stuck`` when any busy worker is stalled; ``needs_input`` then carries the
        most-stalled worker as an ASK (never an auto-action).

        Args:
            terminal_snapshot: The per-worker snapshot just built for status.json.

        Returns:
            A ``(stuck, needs_input)`` tuple where ``needs_input`` is
            ``{"worker": wid|None, "question": str}`` or ``None``.
        """
        now = datetime.now()
        worst_worker: TerminalID | None = None
        worst_elapsed = 0.0
        for tid, snap in terminal_snapshot.items():
            # Only busy workers can stall; an idle worker waiting for work is fine.
            if not snap.get("current_task"):
                continue
            stamp = self._last_progress_at.get(tid)
            if not stamp:
                continue
            try:
                elapsed = (now - datetime.fromisoformat(stamp)).total_seconds()
            except (ValueError, TypeError):
                continue
            if elapsed > self._stuck_threshold_seconds and elapsed > worst_elapsed:
                worst_elapsed = elapsed
                worst_worker = tid

        if worst_worker is None:
            return False, None
        question = (
            f"Worker {worst_worker} has shown no progress for "
            f"{int(worst_elapsed)}s. Intervene, redirect, or wait?"
        )
        return True, {"worker": worst_worker, "question": question}

    def _next_dynamic_worker_id(self) -> str:
        """Mint the next non-colliding dynamic worker id (``w{N+1}``).

        Scans both the live terminals and the dynamic spec map so a spawned worker
        never reuses an id that already exists in either, even with gaps.

        Returns:
            A fresh ``w<N>`` id not currently in use.
        """
        used = set(self.terminals.keys()) | set(self._dynamic_specs.keys())
        n = 1
        while f"w{n}" in used:
            n += 1
        return f"w{n}"

    async def _spawn_worker_from_control(self, cmd: dict) -> None:
        """Spawn a new dynamic worker mid-run from a control command (F10).

        Builds an :class:`AgentSpec` from a ``focus`` (free text) or a capability
        ``lane`` key, gates its profile (honouring an optional ``profile`` override),
        appends it to the live roster + dynamic spec map, and starts a Terminal —
        mirroring :meth:`_spawn_dynamic_roster`.

        Args:
            cmd: The control command, with ``focus`` and/or ``lane`` and an optional
                ``profile`` dict.
        """
        from .dynamic_agents import LANES, _select_subagents

        lane_key = cmd.get("lane")
        focus = cmd.get("focus")
        lane = next((ln for ln in LANES if ln.key == lane_key), None)
        if lane is None:
            # Default to the code backbone lane when only a free-text focus is given.
            lane = next(ln for ln in LANES if ln.key == "code")

        worker_id = self._next_dynamic_worker_id()
        base_profile = profile_for_kind(lane.kind, tiering=True)
        if isinstance(cmd.get("profile"), dict):
            override = ExecutionProfile.from_dict(cmd["profile"])
            base_profile = base_profile.merged(
                model_tier=override.model_tier,
                effort=override.effort,
                permission_mode=override.permission_mode,
                append_system_prompt=override.append_system_prompt,
                allowed_tools=override.allowed_tools,
                disallowed_tools=override.disallowed_tools,
                timeout=override.timeout,
            )

        spec = AgentSpec(
            id=worker_id,
            lane=lane.key,
            kind=lane.kind,
            focus=(focus.strip() if isinstance(focus, str) and focus.strip() else lane.focus),
            subagents=_select_subagents(lane, self.config.get_all_subagents()),
            keywords=list(lane.keywords),
            profile=base_profile,
        )

        gated = self.config.gate_profile(spec.profile)
        terminal = Terminal(
            terminal_id=spec.id,
            working_dir=self.config.base_dir,
            system_prompt=spec.system_prompt(),
            runtime_config=self.config,
            verbose=self.verbose,
            default_profile=gated,
        )
        await terminal.start()
        self.terminals[spec.id] = terminal
        self.agent_roster.append(spec)
        self._dynamic_specs[spec.id] = spec
        self._terminal_modes[spec.id] = gated.badge()
        self._mark_progress(spec.id)
        self._log_terminal(spec.id, f"Spawned ({spec.focus})", Colors.GREEN)
        self._session_log.event("worker_spawned", spec.to_dict())

    async def _handle_chat_command(self, cmd: dict) -> None:
        """Answer a manager-chat query against the live status and append the reply (F4).

        Calls :func:`manager_chat.answer_query` with the live detailed status,
        recent reply history and any session memory, then appends a
        ``{ts, query, answer}`` record to the per-chat reply channel
        ``<orchestra_dir>/chat/<chat_session_id>.replies.jsonl``.

        Args:
            cmd: The control command, with ``text`` (the query) and
                ``chat_session_id`` (the reply-channel key).
        """
        from . import manager_chat

        text = cmd.get("text") or ""
        # Sanitize the channel id before it becomes a filesystem path: this value comes
        # off the control bus (attacker-controllable). Replacing every char outside
        # [A-Za-z0-9._-] with '_' strips path separators, so traversal (../, absolute,
        # backslash) is impossible; a leftover ".." is collapsed to the default too.
        raw_id = str(cmd.get("chat_session_id") or "default")
        chat_session_id = (
            "".join(c if (c.isalnum() or c in "._-") else "_" for c in raw_id) or "default"
        )
        if ".." in chat_session_id:
            chat_session_id = "default"
        chat_dir = self.config.orchestra_dir / "chat"
        replies_path = chat_dir / f"{chat_session_id}.replies.jsonl"
        memory_path = chat_dir / f"{chat_session_id}.memory.json"

        # Prior turns on this channel become the conversational history.
        history: list[dict] = []
        with contextlib.suppress(OSError, ValueError):
            if replies_path.exists():
                for line in replies_path.read_text().splitlines():
                    line = line.strip()
                    if line:
                        history.append(json.loads(line))

        memory: list | None = None
        with contextlib.suppress(OSError, ValueError):
            if memory_path.exists():
                loaded = json.loads(memory_path.read_text())
                if isinstance(loaded, list):
                    memory = loaded

        try:
            # answer_query is async and reads context["status"]/["reports"] — mirror
            # ManagerChat.ask_claude exactly: await it and pass the structured context.
            answer = await manager_chat.answer_query(
                self.config,
                {
                    "status": {
                        "goal": getattr(self, "_current_goal", ""),
                        **self.get_detailed_status(),
                    },
                    "reports": self.report_manager.get_all_components(),
                },
                history,
                text,
                memory,
            )
        except Exception as e:  # never let a chat failure crash the loop
            answer = f"(chat error: {e})"

        record = {"ts": datetime.now().isoformat(), "query": text, "answer": answer}
        try:
            chat_dir.mkdir(parents=True, exist_ok=True)
            with open(replies_path, "a") as f:
                f.write(json.dumps(record, default=str) + "\n")
        except OSError as e:
            self._log_warning(f"[control] Failed to append chat reply (non-fatal): {e}")
        self._session_log.event("chat", record)

    async def _run_control_loop(self) -> None:
        """Background loop that applies dashboard control commands ~1x/sec.

        Runs independently of the main task loop so pause/resume/inject work even while
        the main loop is paused (it would otherwise be blocked on the pause event).
        """
        while self.is_running and not self._shutdown_requested:
            await self._apply_control_commands()
            await asyncio.sleep(1.0)

    def get_detailed_status(self) -> dict:
        """
        Get detailed status for the Manager Chat.

        Returns comprehensive information about execution state,
        terminals, tasks, and progress.

        ORGANIC FLOW MODEL (v2.0):
        Includes flow_state with quality gradients instead of just phase.
        """
        # Get task queue status
        task_status = self.task_queue.get_status_summary()

        # Get flow state (organic model)
        flow_state = self.task_queue.get_flow_state()

        # Get terminal states
        terminal_states = {}
        for tid, terminal in self.terminals.items():
            current_task = self.task_queue.get_terminal_current_task(tid)
            runtime_profile = self.config.get_terminal_runtime_profile(tid)
            terminal_states[tid] = {
                "state": terminal.state.value if terminal else "not_started",
                "current_task": current_task.title if current_task else None,
                "current_task_id": current_task.id if current_task else None,
                "quality_level": current_task.quality_level if current_task else 0.0,
                "flow_state": current_task.flow_state.value if current_task else "idle",
                "provider": runtime_profile["provider"],
                "model": runtime_profile["model"],
                "reasoning_profile": runtime_profile["reasoning"],
                "specialization": runtime_profile["specialization"],
                "mode": self._terminal_modes.get(tid, "auto"),
                **self._dynamic_meta(tid),
            }

        # Calculate duration
        duration = 0.0
        if self.start_time:
            duration = (datetime.now() - self.start_time).total_seconds()

        return {
            "state": "running" if self.is_running else "stopped",
            "paused": not self._paused.is_set(),
            "phase": self.task_queue.get_current_phase(),  # Legacy compatibility
            "duration_seconds": round(duration, 1),
            "terminals": terminal_states,
            "tasks": task_status,
            "rate_limited": self._rate_limited,
            "rate_limit_reset": self._rate_limit_reset_time,
            # Organic flow model additions (v2.0)
            "flow_state": flow_state,
            "use_organic_model": self.use_organic_model,
            "quality_average": flow_state["quality_average"],
            "ready_for_convergence": flow_state["ready_for_convergence"],
        }

    # =========================================================================
    # Terminal Management
    # =========================================================================

    async def spawn_terminals(self, goal: str = "") -> None:
        """Create worker terminals.

        When ``config.dynamic_agents`` is on and a ``goal`` is provided, a task-shaped
        roster of dynamic workers (w1, w2, ...) is derived — no fixed personalities.
        Otherwise the legacy fixed T1..T5 roster is used.
        """
        self._ensure_project_subagents()
        if self.config.dynamic_agents and goal.strip():
            await self._spawn_dynamic_roster(goal)
            return

        self._log_info("Creating terminal workers...")

        terminal_list = ["t1", "t2", "t3", "t4"]
        if not self.config.disable_testing:
            terminal_list.append("t5")
        else:
            self._log_info("T5 (QA/Testing) disabled via --no-testing")

        for tid in terminal_list:
            terminal_id: TerminalID = tid  # type: ignore
            await self._spawn_terminal(terminal_id)

        self._log_success(f"All {len(self.terminals)} terminals ready")

    def _ensure_project_subagents(self) -> None:
        """Make Archon's subagent pool discoverable to workers running in a separate
        project directory by symlinking ``<project>/.claude/agents`` -> the Archon
        agents dir. Without this, workers cd'd into a fresh project can't invoke any
        subagents (Claude Code only auto-discovers ``.claude/agents`` from the cwd and
        the home dir). No-op when the working dir already contains the agents."""
        try:
            agents_src = self.config.agents_dir
            if not agents_src.exists():
                return
            target_claude = self.config.base_dir / ".claude"
            target_agents = target_claude / "agents"
            if target_agents.resolve() == agents_src.resolve():
                return  # already the same (running inside Archon itself)
            if target_agents.exists() or target_agents.is_symlink():
                return  # project already provides agents — don't clobber
            target_claude.mkdir(parents=True, exist_ok=True)
            target_agents.symlink_to(agents_src, target_is_directory=True)
            self._log_info(f"Linked subagent pool into project: {target_agents}")
        except OSError as e:
            self._log_warning(f"Could not link subagents into project: {e}")

    async def _spawn_dynamic_roster(self, goal: str) -> None:
        """Derive and spawn a dynamic, task-shaped worker roster."""
        self._log_info("Deriving dynamic agent roster from goal...")
        # Always derive full lane profiles (model tier + effort); the global gates
        # (model_tiering / effort_dial) are applied centrally by config.gate_profile so
        # the effort dial still shows even when model tiering is off.
        roster = derive_agents(
            goal,
            available_subagents=self.config.get_all_subagents(),
            max_agents=self.config.max_terminals,
            include_testing=not self.config.disable_testing,
            tiering=True,
        )

        # F5: apply per-agent ExecutionProfile overrides from roster_overrides.json
        # (written into the session dir by the dashboard's /api/runs) on top of the
        # freshly derived roster, keyed by agent id.
        overrides = self._load_roster_overrides()
        if overrides:
            for spec in roster:
                ov = overrides.get(spec.id)
                if isinstance(ov, dict):
                    spec.profile = ExecutionProfile.from_dict(ov)
            self._log_info(f"Applied roster overrides for: {sorted(overrides.keys())}")

        self.agent_roster = roster
        self._dynamic_specs = {spec.id: spec for spec in roster}

        for spec in roster:
            gated = self.config.gate_profile(spec.profile)
            terminal = Terminal(
                terminal_id=spec.id,
                working_dir=self.config.base_dir,
                system_prompt=spec.system_prompt(),
                runtime_config=self.config,
                verbose=self.verbose,
                default_profile=gated,
            )
            await terminal.start()
            self.terminals[spec.id] = terminal
            self._terminal_modes[spec.id] = gated.badge()
            self._mark_progress(spec.id)
            self._log_terminal(spec.id, f"Ready ({spec.focus})", Colors.GREEN)

        self._log_success(
            f"Dynamic roster ready: {len(roster)} workers "
            f"({', '.join(f'{s.id}:{s.lane}' for s in roster)})"
        )

    def _load_roster_overrides(self) -> dict[str, dict]:
        """Load per-agent ExecutionProfile overrides from the session dir (F5).

        Reads ``<orchestra_dir>/roster_overrides.json`` — a mapping of agent id →
        :class:`ExecutionProfile` dict — that the dashboard writes before spawning
        a run. Best-effort: a missing/corrupt file yields an empty mapping.

        Returns:
            Mapping of agent id → profile-dict (possibly empty).
        """
        path = self.config.orchestra_dir / "roster_overrides.json"
        try:
            if not path.exists():
                return {}
            data = json.loads(path.read_text())
        except (OSError, ValueError) as e:
            self._log_warning(f"[roster] overrides unreadable (non-fatal): {e}")
            return {}
        if not isinstance(data, dict):
            return {}
        return {k: v for k, v in data.items() if isinstance(v, dict)}

    async def _spawn_terminal(self, terminal_id: TerminalID) -> Terminal | None:
        """Spawn a single terminal."""
        try:
            config = self.config.get_terminal_config(terminal_id)

            # Load system prompt from template
            system_prompt = self.config.load_system_prompt(terminal_id)

            terminal = Terminal(
                terminal_id=terminal_id,
                working_dir=self.config.base_dir,
                system_prompt=system_prompt,
                runtime_config=self.config,
                verbose=self.verbose,
            )

            await terminal.start()
            self.terminals[terminal_id] = terminal
            self._log_terminal(terminal_id, f"Ready ({config.role})", Colors.GREEN)
            return terminal

        except Exception as e:
            self._log_error(f"Failed to spawn terminal {terminal_id}: {e}")
            return None

    async def _restart_terminal(self, terminal_id: TerminalID) -> bool:
        """Restart a failed terminal."""
        self._log_warning(f"Attempting to restart terminal {terminal_id}...")

        # Stop existing terminal if any
        if terminal_id in self.terminals:
            with contextlib.suppress(Exception):
                await self.terminals[terminal_id].stop()
            del self.terminals[terminal_id]

        # Spawn new terminal
        terminal = await self._spawn_terminal(terminal_id)
        if terminal:
            self._log_success(f"Terminal {terminal_id} restarted successfully")
            return True
        else:
            self._log_error(f"Failed to restart terminal {terminal_id}")
            return False

    # =========================================================================
    # Task Planning
    # =========================================================================

    async def plan_and_distribute(self, task: str, project_context: str = "") -> TaskPlan:
        """Plan a high-level task and distribute to terminals."""
        self._log_info(f"Planning task: {task[:80]}...")

        # Log start event
        self.event_logger.orchestrator_started(task)

        # Use planner to break down task
        plan = await self.planner.plan(task, project_context=project_context)

        self._log_success(f"Plan created: {plan.summary}")
        self._log_info(f"Total tasks: {len(plan.tasks)}")

        # Add tasks to queue with phase information. In dynamic mode the planner still
        # emits legacy t1..t5 targets, so remap each task onto the best-matching
        # dynamic worker by capability.
        for planned_task in plan.tasks:
            assigned_to = planned_task.terminal
            if self.agent_roster:
                assigned_to = route_to_agent(
                    f"{planned_task.title}\n{planned_task.description}",
                    self.agent_roster,
                )
            self.task_queue.add_task(
                title=planned_task.title,
                description=planned_task.description,
                priority=TaskPriority(planned_task.priority),
                dependencies=planned_task.dependencies,
                assigned_to=assigned_to,
                phase=planned_task.phase,
                metadata={"from_plan": True, "phase": planned_task.phase},
            )

        # Log phase distribution
        phase_counts = {}
        for t in plan.tasks:
            phase_counts[t.phase] = phase_counts.get(t.phase, 0) + 1
        self._log_info(f"Task distribution by phase: {phase_counts}")

        # Broadcast plan to all terminals
        self.message_bus.broadcast_status(
            f"# New Project\n\n{plan.summary}\n\nTasks: {len(plan.tasks)}"
        )

        # Log plan creation
        self.event_logger.plan_created(len(plan.tasks), plan.summary)

        # Initialize progress tracker
        if self.use_progress_bar and len(plan.tasks) > 0:
            self._progress = ProgressTracker(
                total=len(plan.tasks),
                description="Tasks",
                use_tqdm=True,
            )

        return plan

    # =========================================================================
    # Task Execution with Retry Logic
    # =========================================================================

    def _dynamic_meta(self, terminal_id: TerminalID) -> dict:
        """Extra status fields for a dynamic worker: its capability lane, focus, and
        curated subagents. Empty for the legacy roster."""
        spec = self._dynamic_specs.get(terminal_id)
        if spec is None:
            return {}
        return {
            "lane": spec.lane,
            "focus": spec.focus,
            "specialization": spec.focus,  # override the generic "dynamic agent"
            "subagents": list(spec.subagents),
        }

    def _build_task_profile(
        self, task: Task, terminal_id: TerminalID | None = None
    ) -> ExecutionProfile:
        """Derive the per-task execution mode (model tier + effort).

        Precedence:
        1. an explicit per-task override in ``task.metadata['profile']`` (control plane);
        2. a live per-worker mode override set via the control plane (set_mode);
        3. the assigned dynamic worker's lane profile (when running a dynamic roster);
        4. the task kind classified from its text.

        Respects the ``effort_dial`` and ``model_tiering`` config switches:
        - effort is applied when ``effort_dial`` is on (safe, OAuth-friendly);
        - model tier is applied only when ``model_tiering`` is on (may request a model
          the plan lacks, so opt-in).
        """
        metadata = task.metadata if hasattr(task, "metadata") else None
        override = (metadata or {}).get("profile")
        if override:
            # Control-plane / metadata profiles are untrusted: gate them like every
            # other path so the F7 skill/MCP deny-set and the tiering/effort
            # switches are applied consistently (they previously slipped through
            # ungated, re-enabling tool-creation on a permission-bypassed worker).
            resolved = self.config.gate_profile(ExecutionProfile.from_dict(override))
        elif terminal_id and terminal_id in self._mode_overrides:
            resolved = self.config.gate_profile(
                ExecutionProfile.from_dict(self._mode_overrides[terminal_id])
            )
        else:
            spec = self._dynamic_specs.get(terminal_id) if terminal_id else None
            if spec is not None:
                profile = spec.profile
            else:
                kind = classify_task(task.title, task.description)
                profile = profile_for_kind(kind, tiering=True)  # both model + effort
            resolved = self.config.gate_profile(profile)

        # F2: carry how-to instructions from task metadata into the worker run as an
        # appended system prompt (without clobbering a profile that already set one).
        instructions = None
        if isinstance(metadata, dict):
            instructions = metadata.get("append_system_prompt") or metadata.get("instructions")
        if isinstance(instructions, str) and instructions.strip():
            # Cap untrusted, control-plane-supplied system-prompt text so an
            # unauthenticated injector cannot bloat the worker's system prompt.
            cleaned = instructions.strip()[:_MAX_INSTRUCTIONS_CHARS]
            if resolved.append_system_prompt:
                merged_system = f"{resolved.append_system_prompt}\n\n{cleaned}"
            else:
                merged_system = cleaned
            resolved = resolved.merged(append_system_prompt=merged_system)

        return resolved

    async def _execute_task_on_terminal(
        self,
        terminal_id: TerminalID,
        task: Task,
    ) -> bool:
        """
        Execute a single task on a terminal with retry logic.

        Returns:
            True if task succeeded, False if failed (after all retries)
        """
        terminal = self.terminals.get(terminal_id)

        # Check if terminal needs restart
        if terminal is None or terminal.state == TerminalState.ERROR:
            if not await self._restart_terminal(terminal_id):
                return False
            terminal = self.terminals.get(terminal_id)
            if terminal is None:
                return False

        # Get context from other terminals' reports (Manager Intelligence)
        context = self.report_manager.get_context_for_terminal(
            target_terminal=terminal_id,
            task_description=task.description,
        )

        prompt = f"""## Task: {task.title}

{task.description}

{context}

## Working Directory

Work in: {self.config.base_dir}

## Output Format

When done, provide a structured summary:
1. **Summary**: What you accomplished (1-2 sentences)
2. **Files Created**: List any new files
3. **Files Modified**: List any modified files
4. **Components/APIs**: List components, classes, or endpoints you created
5. **For Other Terminals**: What you've created that other terminals can use
6. **Dependencies Needed**: What you need from other terminals

This helps the orchestrator coordinate with other terminals.
"""

        retry_count = self._retry_counts.get(task.id, 0)

        if retry_count > 0:
            self._log_retry(terminal_id, task.title, retry_count, self.retry_config.max_retries)
        else:
            self._log_terminal(terminal_id, f"Starting: {task.title}", Colors.CYAN)

        self.event_logger.task_started(terminal_id, task.id, task.title)

        # Derive the per-task execution mode (model tier + effort) and record its badge
        # so the dashboard can show live mode switching.
        profile = self._build_task_profile(task, terminal_id)
        self._terminal_modes[terminal_id] = profile.badge()
        task_timeout = profile.timeout or self.config.terminal_timeout

        # F15: the worker is actively running now — stamp real progress.
        self._mark_progress(terminal_id)

        try:
            output = await terminal.execute_task(
                prompt=prompt,
                task_id=task.id,
                timeout=task_timeout,
                profile=profile,
            )

            # F16: capture the FULL, untruncated output into the firehose BEFORE the
            # 3000/2000-char truncations applied below for the dashboard / task result.
            self._session_log.output(
                terminal_id,
                task.id,
                output.content,
                profile=profile.badge(),
            )
            # F11: estimate prompt-adherence from the raw output for the status block.
            self._record_adherence(terminal_id, output.content, task)
            # F15: output arrived — real progress.
            self._mark_progress(terminal_id)

            # Save terminal output for dashboard
            self._save_terminal_output(terminal_id, output.content)

            # Check for subagent usage in output
            self._detect_subagent_usage(terminal_id, task.title, output.content)

            # Check for rate limit
            if output.is_error and output.content.startswith("RATE_LIMIT:"):
                reset_time = output.content.replace("RATE_LIMIT:", "").strip()
                provider_label = self.config.llm_provider.upper()
                self._log_error(f"{provider_label} rate limit reached! Resets: {reset_time}")
                self._log_warning("Stopping orchestrator - please wait for rate limit to reset")

                # Mark rate limited state
                self._rate_limited = True
                self._rate_limit_reset_time = reset_time

                # Mark task as failed with rate limit error
                self.task_queue.complete_task(
                    task.id,
                    result=output.content,
                    success=False,
                    error=f"Rate limit reached - resets {reset_time}",
                )

                # Request shutdown
                self._shutdown_requested = True
                return False

            if output.is_error:
                return await self._handle_task_failure(
                    terminal_id, task, "Task failed or timed out"
                )
            else:
                # The worker succeeded — its files are already written. Report parsing
                # and cross-terminal notification are METADATA: a failure there must
                # never discard successful work or trigger a (quota-wasting) retry.
                try:
                    # Async variant: the optional llm_report_parsing path shells
                    # out, so run it off the event loop to avoid freezing every
                    # worker / the manager / the control loop.
                    report = await self.report_manager.parse_output_to_report_async(
                        output=output.content,
                        task_id=task.id,
                        task_title=task.title,
                        terminal_id=terminal_id,
                        success=True,
                    )
                    self.report_manager.save_report(report)
                    self._log_info(f"Report saved: {report.summary[:60]}...")
                    self._notify_terminals_of_completion(terminal_id, task, report)
                except Exception as report_err:  # non-fatal: keep the success
                    self._log_warning(f"Report post-processing failed (non-fatal): {report_err}")

                # Mark task complete
                self.task_queue.complete_task(
                    task.id,
                    result=output.content[:2000],
                    success=True,
                )

                self._log_terminal(terminal_id, f"Done: {task.title}", Colors.GREEN)
                self.event_logger.task_completed(terminal_id, task.id, task.title)
                # F15: completion is real progress.
                self._mark_progress(terminal_id)

                # Update progress
                if self._progress:
                    self._progress.update(success=True)

                return True

        except Exception as e:
            return await self._handle_task_failure(terminal_id, task, str(e))

    async def _handle_task_failure(
        self,
        terminal_id: TerminalID,
        task: Task,
        error: str,
    ) -> bool:
        """Handle a task failure with retry logic."""
        retry_count = self._retry_counts.get(task.id, 0)

        if retry_count < self.retry_config.max_retries:
            # Schedule retry
            self._retry_counts[task.id] = retry_count + 1
            delay = self.retry_config.get_delay(retry_count)

            self._log_warning(
                f"Task failed: {task.title} - Retrying in {delay}s "
                f"(attempt {retry_count + 1}/{self.retry_config.max_retries})"
            )

            # Wait before retry
            await asyncio.sleep(delay)

            # Re-queue task for retry
            self._retry_queue.append((task, terminal_id))
            return False  # Not yet final failure

        else:
            # Max retries exceeded - mark as failed
            self.task_queue.complete_task(
                task.id,
                result=None,
                success=False,
                error=f"Failed after {self.retry_config.max_retries} retries: {error}",
            )

            self._log_error(f"Task failed permanently: {task.title}")
            self.event_logger.task_failed(terminal_id, task.id, task.title, error)

            # Update progress
            if self._progress:
                self._progress.update(success=False)

            return False

    # =========================================================================
    # Manager Intelligence - Cross-Terminal Coordination
    # =========================================================================

    def _notify_terminals_of_completion(
        self,
        completed_terminal: TerminalID,
        task: Task,
        report: Report,
    ) -> None:
        """
        Notify other terminals of what was completed (Manager Intelligence).

        This is the key coordination function - the orchestrator understands
        what was done and informs relevant terminals.
        """
        if not report.provides_to_others and not report.components_created:
            return  # Nothing to share

        # Build notification message
        terminal_config = self.config.get_terminal_config(completed_terminal)
        message_parts = [
            f"## Update from {completed_terminal.upper()} ({terminal_config.role})",
            "",
            f"**Task completed:** {task.title}",
            "",
            f"**Summary:** {report.summary}",
            "",
        ]

        if report.components_created:
            message_parts.append("**Available Components:**")
            for comp in report.components_created[:5]:
                message_parts.append(f"- {comp}")
            message_parts.append("")

        if report.files_created:
            message_parts.append("**New Files:**")
            for f in report.files_created[:5]:
                message_parts.append(f"- `{f}`")
            message_parts.append("")

        # Determine who to notify. Drive recipients off the live roster so dynamic
        # workers (w1, w2, ...) and a --no-testing run (no t5) are handled correctly.
        all_ids: set[TerminalID] = set(self.terminals.keys())
        recipients: set[TerminalID] = set()

        # Check explicit provides_to_others
        for provides in report.provides_to_others:
            target = provides.get("to", "all")
            if target == "all":
                recipients = set(all_ids)
                break
            elif target in all_ids:
                recipients.add(target)

        # If nothing explicit, notify based on task type (legacy role heuristics for the
        # fixed roster; dynamic workers simply share with everyone else).
        if not recipients:
            if completed_terminal == "t1":
                recipients.add("t2")
            elif completed_terminal == "t2":
                recipients.update({"t1", "t3"})
            elif completed_terminal == "t4":
                recipients.update({"t1", "t2", "t3"})
            else:
                recipients = set(all_ids)

        # Only notify terminals that actually exist, and never self.
        recipients &= all_ids
        recipients.discard(completed_terminal)

        # Send notifications
        message = "\n".join(message_parts)
        for recipient in recipients:
            self.message_bus.send(
                sender=f"{completed_terminal} (via orchestrator)",
                recipient=recipient,
                content=message,
                msg_type="status",
                metadata={
                    "report_id": report.id,
                    "task_id": task.id,
                },
            )
            self._log_info(f"Notified {recipient} of {completed_terminal}'s completion")

    def _get_collaboration_context(self) -> str:
        """
        Get a summary of what all terminals have produced.

        Used by the Manager to understand the current state of the project.
        """
        all_components = self.report_manager.get_all_components()

        context_parts = ["## Current Project State", ""]

        for tid in self.terminals.keys():
            terminal_config = self.config.get_terminal_config(tid)
            components = all_components.get(tid, [])

            context_parts.append(f"### {tid.upper()} ({terminal_config.role})")
            if components:
                context_parts.append("Components: " + ", ".join(components[:10]))
            else:
                context_parts.append("No components yet")
            context_parts.append("")

        return "\n".join(context_parts)

    async def _run_manager_loop(self) -> None:
        """
        Run the manager intelligence loop.

        This continuously monitors heartbeats and takes coordination actions.
        Runs in parallel with task execution.
        """
        while self.is_running:
            try:
                # Check if paused
                if not self._paused.is_set():
                    await asyncio.sleep(self._manager_loop_interval)
                    continue

                # Build heartbeats from internal terminal state (no disk I/O).
                # F15: feed the REAL last-progress timestamp into the heartbeat so a
                # genuine stall actually ages out (the heartbeat previously defaulted
                # its timestamp to now, so age_seconds was always ~0 and never fired).
                heartbeats = {}
                for tid, terminal in self.terminals.items():
                    kwargs: dict = {
                        "terminal_id": tid,
                        "current_task_id": terminal.current_task_id,
                        "current_task_title": terminal.current_task_id,
                        "is_blocked": (terminal.state.value == "blocked"),
                    }
                    # Only feed the real last-progress timestamp when the worker is
                    # actually BUSY (has a current task). An idle worker waiting for
                    # work has a stale last_progress_at and would otherwise look stalled;
                    # for it we keep the heartbeat default (now) so it is never flagged.
                    last_progress = self._last_progress_at.get(tid)
                    if last_progress and terminal.current_task_id:
                        kwargs["timestamp"] = last_progress
                        kwargs["last_output_timestamp"] = last_progress
                    heartbeats[tid] = TerminalHeartbeat(**kwargs)

                # Get contracts for context (live roster, dynamic-aware)
                contracts = {}
                for tid in self.terminals.keys():
                    contracts[tid] = self.report_manager.get_reports_for_terminal(tid)

                # Get current phase
                current_phase = self.task_queue.get_current_phase()

                # Analyze and decide
                actions = self.manager_intelligence.analyze_and_decide(
                    heartbeats=heartbeats,
                    contracts=contracts,
                    current_phase=current_phase,
                )

                # Execute actions
                for action in actions:
                    await self._execute_manager_action(action)

            except Exception as e:
                self._log_warning(f"Manager loop error: {e}")

            await asyncio.sleep(self._manager_loop_interval)

    async def _execute_manager_action(self, action: ManagerAction) -> None:
        """
        Execute a manager action.

        ORGANIC FLOW MODEL (v2.0):
        Handles the 5 intervention types: AMPLIFY, REDIRECT, MEDIATE, INJECT, PRUNE
        """
        self._log_info(f"Manager action: {action.action_type.value} - {action.reason}")
        action_payload = {
            "type": action.action_type.value,
            "reason": action.reason,
            "priority": action.priority,
            "flow_state_before": action.flow_state_before,
        }
        self.event_logger.log_event("manager_action", action_payload)
        # F16: mirror every manager intervention into the firehose.
        self._session_log.event("manager_action", action_payload)

        # ORGANIC FLOW INTERVENTIONS (v2.0)

        if action.action_type == ActionType.AMPLIFY:
            # Amplify: Increase focus on flourishing work
            self._log_success(f"AMPLIFY: {action.reason}")
            if action.broadcast_message:
                self.message_bus.broadcast_status(action.broadcast_message)
            # Could also increase polling frequency for this terminal, etc.

        elif action.action_type == ActionType.REDIRECT:
            # Redirect: Change direction on stalled work
            self._log_warning(f"REDIRECT: {action.reason}")
            if action.broadcast_message:
                self.message_bus.broadcast_status(action.broadcast_message)
            # Could also update task description, suggest different approach, etc.

        elif action.action_type == ActionType.MEDIATE:
            # Mediate: Resolve conflicts between terminals
            self._log_warning(f"MEDIATE: {action.reason}")
            if action.broadcast_message:
                self.message_bus.broadcast_status(action.broadcast_message)
            # Notify specific conflict parties
            for party in action.conflict_parties:
                self.message_bus.send(
                    sender="orchestrator",
                    recipient=party,
                    content=f"Conflict mediation required: {action.resolution_approach}",
                    msg_type="coordination",
                )

        elif action.action_type == ActionType.INJECT:
            # Inject: Add new work (alias for INJECT_TASK)
            if action.task_title and action.task_description and action.target_terminal:
                await self.inject_task(
                    title=action.task_title,
                    description=action.task_description,
                    terminal_id=action.target_terminal,
                    priority=action.priority,
                    intent=action.task_intent,
                )

        elif action.action_type == ActionType.PRUNE:
            # Prune: Remove or deprioritize unproductive work
            self._log_warning(f"PRUNE: {action.reason}")
            for task_id in action.task_ids_to_prune:
                # Mark task as blocked/deprioritized
                self.task_queue.mark_task_blocked(task_id, action.prune_reason)
                self._log_info(f"Deprioritized task: {task_id}")

        # LEGACY ACTIONS (backward compatibility)

        elif action.action_type == ActionType.BROADCAST_UPDATE:
            if action.broadcast_message:
                self.message_bus.broadcast_status(action.broadcast_message)

        elif action.action_type == ActionType.INJECT_TASK:
            if action.task_title and action.task_description and action.target_terminal:
                await self.inject_task(
                    title=action.task_title,
                    description=action.task_description,
                    terminal_id=action.target_terminal,
                    priority=action.priority,
                    intent=action.task_intent,
                )

        elif action.action_type == ActionType.TRIGGER_SYNC_POINT:
            # In organic model, this becomes "convergence point"
            if self.use_organic_model:
                self._log_info("CONVERGENCE POINT TRIGGERED")
                self.message_bus.broadcast_status(
                    f"## CONVERGENCE POINT\n\nWork quality threshold reached.\n"
                    f"Quality average: {action.flow_state_before or 'N/A'}"
                )
            else:
                self._log_info("SYNC POINT TRIGGERED")
                self.message_bus.broadcast_status(
                    "## SYNC POINT\n\nPhase transition triggered.\n"
                    "All terminals should check for phase-specific tasks."
                )

        elif action.action_type == ActionType.ESCALATE:
            self._log_warning(f"ESCALATION: {action.reason}")
            self._write_to_log_file(f"ESCALATION: {action.reason}", "escalate")

    # =========================================================================
    # Quality Check
    # =========================================================================

    async def _run_quality_check(self) -> list[dict]:
        """
        Run a quality check after all tasks complete.

        Returns:
            List of fix tasks that were created
        """
        if not self.enable_quality_check:
            return []

        # Check if we've exceeded max quality check iterations
        self._quality_check_iteration += 1
        if self._quality_check_iteration > self.max_quality_iterations:
            self._log_info(
                f"Quality check skipped (max iterations {self.max_quality_iterations} reached)"
            )
            return []

        self._log_info(
            f"Running quality check (iteration {self._quality_check_iteration}/{self.max_quality_iterations})..."
        )

        completed_tasks = self.task_queue.completed

        # Only check tasks that haven't been processed yet
        new_tasks = [t for t in completed_tasks if t.id not in self._processed_task_ids]

        # Mark all current tasks as processed
        for t in completed_tasks:
            self._processed_task_ids.add(t.id)

        # Skip Review/Fix tasks - don't create Review of Review
        original_tasks = [
            t
            for t in new_tasks
            if not t.title.startswith("Review:")
            and not t.title.startswith("Fix:")
            and not t.metadata.get("is_fix_task")
            and not t.metadata.get("is_review_task")
        ]

        failed_tasks = [t for t in original_tasks if t.status == TaskStatus.FAILED]

        fix_tasks = []

        # Check for failed tasks and create fix tasks
        for failed_task in failed_tasks:
            # Skip rate limit errors - nothing to fix, just need to wait
            if failed_task.error and "limit" in failed_task.error.lower():
                continue

            fix_task_data = {
                "title": f"Fix: {failed_task.title}",
                "description": f"""The following task failed and needs to be fixed:

Original Task: {failed_task.title}
Error: {failed_task.error or 'Unknown error'}

Please analyze what went wrong and implement a fix.
If the task is not critical, you may skip it with an explanation.
""",
                "priority": "high",
                "assigned_to": failed_task.assigned_to,
                "metadata": {
                    "is_fix_task": True,
                    "original_task_id": failed_task.id,
                },
            }
            fix_tasks.append(fix_task_data)

        # NOTE: Disabled automatic review task creation to prevent loops
        # The quality check now only creates Fix tasks for genuine failures
        # Uncomment below if you want to enable review tasks (with caution)
        #
        # # Check for potential issues in completed tasks
        # successful_tasks = [t for t in original_tasks if t.status == TaskStatus.COMPLETED]
        # error_indicators = ["error", "failed", "exception", "bug", "issue", "problem"]
        # for task in successful_tasks:
        #     if task.result:
        #         result_lower = task.result.lower()
        #         has_issues = any(indicator in result_lower for indicator in error_indicators)
        #         if has_issues and "fixed" not in result_lower and "resolved" not in result_lower:
        #             ...

        # Add fix tasks to queue
        if fix_tasks:
            self._log_warning(f"Quality check found {len(fix_tasks)} issues - creating fix tasks")
            self.task_queue.add_tasks(fix_tasks)

            # Reset progress tracker for fix tasks
            if self._progress:
                self._progress.close()
            if self.use_progress_bar:
                self._progress = ProgressTracker(
                    total=len(fix_tasks),
                    description="Fix Tasks",
                    use_tqdm=True,
                )
        else:
            self._log_success("Quality check passed - no issues found")

        return fix_tasks

    # =========================================================================
    # Main Task Loop
    # =========================================================================

    async def run_task_loop(self) -> None:
        """
        Main loop that assigns and monitors tasks.

        LEGACY PARALLEL EXECUTION:
        - Phase 1: ALL terminals start immediately (no blocking dependencies)
        - Phase 2: Integration tasks (after Phase 1 completes)
        - Phase 3: Testing/verification tasks (after Phase 2 completes)

        ORGANIC FLOW MODEL (v2.0):
        - Continuous observation loop instead of phase progression
        - Tasks assigned based on flow state and terminal availability
        - Quality gradients tracked instead of binary completion
        - Manager interventions guide work (AMPLIFY, REDIRECT, MEDIATE, INJECT, PRUNE)
        """
        if self.use_organic_model:
            self._log_info("Starting ORGANIC FLOW observation loop...")
        else:
            self._log_info("Starting PARALLEL task execution loop...")

        # Track current phase (legacy) / flow state (organic)
        current_phase = 1
        phase_announced = {1: False, 2: False, 3: False}
        last_flow_state = None

        while self.is_running:
            # Check if shutdown was requested
            if self._shutdown_requested:
                break

            # Wait if paused (blocks until resumed)
            if not self._paused.is_set():
                self._log_info("Waiting for resume...")
                await self._paused.wait()
                self._log_info("Resumed!")

            # Process retry queue first - move failed tasks back to pending
            while self._retry_queue:
                task, terminal_id = self._retry_queue.pop(0)
                # Move from in_progress back to pending for re-assignment
                if not self.task_queue.requeue_task(task.id):
                    # Task wasn't in in_progress, try adding as new
                    if self.task_queue.get_task(task.id) is None:
                        self.task_queue.add_task(
                            title=task.title,
                            description=task.description,
                            priority=task.priority,
                            dependencies=task.dependencies,
                            assigned_to=terminal_id,
                            phase=task.phase,
                            metadata=task.metadata,
                        )

            # Check if all done
            if self.task_queue.is_all_done():
                # Run quality check
                fix_tasks = await self._run_quality_check()

                if not fix_tasks:
                    self._log_success("All tasks completed!")
                    # Log completion event for dashboard
                    self.event_logger.orchestrator_stopped(
                        completed=len(self.task_queue.completed),
                        failed=len(
                            [t for t in self.task_queue.completed if t.status.value == "failed"]
                        ),
                    )
                    break
                # Otherwise continue with fix tasks

            # ORGANIC FLOW MODEL: Track flow state changes
            if self.use_organic_model:
                flow_state = self.task_queue.get_flow_state()
                current_flow = flow_state["overall_flow"]

                if current_flow != last_flow_state:
                    last_flow_state = current_flow
                    self._log_info(f"{'='*40}")
                    self._log_info(f"FLOW STATE: {current_flow.upper()}")
                    self._log_info(f"Quality average: {flow_state['quality_average']:.0%}")

                    if current_flow == FlowState.CONVERGING.value:
                        self._log_info("Work converging toward completion")
                    elif current_flow == FlowState.BLOCKED.value:
                        self._log_warning("Work blocked - intervention may be needed")
                    elif current_flow == FlowState.FLOURISHING.value:
                        self._log_success("Work flourishing - great progress!")
                    elif current_flow == FlowState.STALLED.value:
                        self._log_warning("Work stalled - may need redirection")

                    self._log_info(f"{'='*40}")

                    # Broadcast flow state change
                    self.message_bus.broadcast_status(
                        f"## FLOW STATE: {current_flow.upper()}\n\n"
                        f"Quality: {flow_state['quality_average']:.0%}\n"
                        f"Blocked: {flow_state['blocked_count']}, Flourishing: {flow_state['flourishing_count']}"
                    )

                # In organic model, phase is just for backward compatibility
                current_phase = self.task_queue.get_current_phase()

            else:
                # LEGACY: Determine current phase from task completion state
                new_phase = self.task_queue.get_current_phase()
                if new_phase != current_phase:
                    current_phase = new_phase
                    if not phase_announced.get(current_phase, True):
                        self._log_info(f"{'='*40}")
                        self._log_info(f"ENTERING PHASE {current_phase}")
                        if current_phase == 2:
                            self._log_info("Integration phase: connecting components")
                        elif current_phase == 3:
                            self._log_info("Testing phase: verification and polish")
                        self._log_info(f"{'='*40}")
                        phase_announced[current_phase] = True

                        # Broadcast phase change to all terminals
                        self.message_bus.broadcast_status(
                            f"## PHASE {current_phase} STARTED\n\n"
                            f"{'Integration' if current_phase == 2 else 'Testing'} phase beginning. "
                            f"Check .orchestra/reports/ for other terminals' work."
                        )

            # Get completed task IDs AND titles for dependency checking
            completed = self.task_queue.completed
            completed_ids = {t.id for t in completed} | {t.title for t in completed}

            # For each idle terminal, try to assign a task
            for terminal_id, terminal in list(self.terminals.items()):
                # Check terminal health
                if terminal.state == TerminalState.ERROR:
                    self._log_warning(f"Terminal {terminal_id} in error state - attempting restart")
                    await self._restart_terminal(terminal_id)
                    continue

                # Skip if terminal is busy
                if terminal_id in self._running_tasks:
                    task_future = self._running_tasks[terminal_id]
                    if not task_future.done():
                        continue
                    else:
                        # Clean up completed future
                        del self._running_tasks[terminal_id]

                # Get next task for this terminal (phase-aware)
                task = self.task_queue.get_next_task_for_terminal(terminal_id, current_phase)
                if task is None:
                    continue

                # Phase 1 tasks are ALWAYS ready - no dependency blocking
                # Phase 2+ tasks check dependencies
                if not task.is_ready(completed_ids, current_phase):
                    continue

                # Assign and start task
                assigned = self.task_queue.assign_task(task.id, terminal_id)
                if assigned:
                    # Log with phase info
                    phase_tag = f"[P{assigned.phase}]" if assigned.phase > 1 else ""
                    self._log_terminal(
                        terminal_id, f"{phase_tag} Assigned: {assigned.title}", Colors.CYAN
                    )
                    # F15: assignment is real progress for this worker.
                    self._mark_progress(terminal_id)

                    # Start task execution in background
                    future = asyncio.create_task(
                        self._execute_task_on_terminal(terminal_id, assigned)
                    )
                    self._running_tasks[terminal_id] = future

            # Update status with phase/flow info
            flow_state_data = self.task_queue.get_flow_state() if self.use_organic_model else {}
            terminal_snapshot = {}
            for tid, terminal in self.terminals.items():
                runtime_profile = self.config.get_terminal_runtime_profile(tid)
                current_task = self.task_queue.get_terminal_current_task(tid)
                terminal_snapshot[tid] = {
                    "state": terminal.state.value,
                    "current_task": terminal.current_task_id,
                    # F9: metrics._per_worker reads quality_level — mirror
                    # get_detailed_status so the metrics block sees real quality.
                    "quality_level": current_task.quality_level if current_task else 0.0,
                    "provider": runtime_profile["provider"],
                    "model": runtime_profile["model"],
                    "reasoning_profile": runtime_profile["reasoning"],
                    "specialization": runtime_profile["specialization"],
                    "mode": self._terminal_modes.get(tid, "auto"),
                    # F15 / F11: real progress timestamp + output-adherence per worker.
                    "last_progress_at": self._last_progress_at.get(tid),
                    "adherence": self._last_adherence.get(tid, 0.0),
                    **self._dynamic_meta(tid),
                }

            tasks_summary = self.task_queue.get_status_summary()
            now_iso = datetime.now().isoformat()
            stuck, needs_input = self._compute_stuck_state(terminal_snapshot)
            self._stuck, self._needs_input = stuck, needs_input

            status_payload: dict = {
                "state": "running",
                "current_phase": current_phase,
                "use_organic_model": self.use_organic_model,
                "flow_state": flow_state_data if self.use_organic_model else None,
                "terminals": terminal_snapshot,
                "tasks": tasks_summary,
                # F3: live roster (dynamic + spawned). Empty for the legacy fixed roster.
                "roster": [spec.to_dict() for spec in self.agent_roster],
                # F9: fresh metrics derived from the just-built snapshot.
                "metrics": metrics.compute_metrics(
                    {"terminals": terminal_snapshot},
                    tasks_summary,
                    self.start_time.isoformat() if self.start_time else None,
                    now_iso,
                ),
                # F15: stuck / needs-input signals.
                "stuck": stuck,
                "needs_input": needs_input,
            }
            self._update_status(status_payload)

            # Brief pause before next iteration
            await asyncio.sleep(self.config.poll_interval)

        # Wait for any running tasks to complete
        if self._running_tasks:
            self._log_info("Waiting for running tasks to complete...")
            await asyncio.gather(*self._running_tasks.values(), return_exceptions=True)

    # =========================================================================
    # Continuous Mode
    # =========================================================================

    async def _prompt_for_new_task(self) -> str | None:
        """Prompt user for a new task in continuous mode."""
        print()
        print(f"{Colors.CYAN}{'='*60}{Colors.RESET}")
        print(f"{Colors.BOLD}All tasks completed!{Colors.RESET}")
        print()
        print("Options:")
        print(f"  {Colors.GREEN}Enter a new task{Colors.RESET} - Start a new project/task")
        print(f"  {Colors.YELLOW}q/quit/exit{Colors.RESET} - Stop the orchestrator")
        print()

        try:
            user_input = input(f"{Colors.CYAN}> New task (or 'q' to quit): {Colors.RESET}").strip()
        except EOFError:
            return None
        except KeyboardInterrupt:
            return None

        if user_input.lower() in ("q", "quit", "exit", ""):
            return None

        return user_input

    # =========================================================================
    # Main Run Methods
    # =========================================================================

    async def run(self, task: str, project_context: str = "") -> dict:
        """
        Run the full orchestration workflow for a task.

        Args:
            task: High-level task description
            project_context: Optional context about an existing project

        Returns:
            Final status report
        """
        self.is_running = True
        self.start_time = datetime.now()
        # Remember the run goal so the live chat (F4) can answer about it even
        # before the plan/tasks land in the status snapshot.
        self._current_goal = task

        # Register this run in the shared session registry (mints a session id
        # if the config lacks one) so the dashboard can discover/steer it.
        self._register_session_start(task)
        self._session_log.event("run_started", {"goal": task, "session_id": self.config.session_id})

        run_status = "completed"
        try:
            # Initialize
            await self.initialize()

            # Create terminals (dynamic roster derives from the goal when enabled)
            await self.spawn_terminals(goal=task)

            # Start manager intelligence loop
            self._manager_loop_task = asyncio.create_task(self._run_manager_loop())

            # Start control-plane loop (applies dashboard commands)
            self.control.reset()
            self._control_loop_task = asyncio.create_task(self._run_control_loop())

            if not self.terminals:
                run_status = "failed"
                return {"error": "No terminals created"}

            # Run the main workflow (possibly in continuous mode)
            current_task = task

            while True:
                # Plan and distribute current task
                await self.plan_and_distribute(current_task, project_context=project_context)

                # Run main loop
                await self.run_task_loop()

                # Close progress tracker
                if self._progress:
                    self._progress.close()
                    self._progress = None

                # Check if continuous mode
                if not self.continuous_mode or self._shutdown_requested:
                    break

                # Prompt for new task
                new_task = await self._prompt_for_new_task()
                if new_task is None:
                    break

                # Clear state for new task
                self.task_queue.clear_all()
                self._retry_counts.clear()
                self._retry_queue.clear()
                current_task = new_task

            # Generate final report
            report = self._generate_report()
            if self._rate_limited or report.get("status") == "partial":
                run_status = "completed"
            return report

        except Exception:
            run_status = "failed"
            raise

        finally:
            # Record terminal session status before tearing down.
            self._update_session_status(run_status)
            self._session_log.event("run_finished", {"status": run_status})
            # Cleanup
            await self.shutdown()

    async def shutdown(self) -> None:
        """Shutdown all terminals and cleanup."""
        self._log_info("Shutting down...")
        self.is_running = False

        # Stop manager loop
        if self._manager_loop_task:
            self._manager_loop_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._manager_loop_task

        # Stop control-plane loop
        control_task = getattr(self, "_control_loop_task", None)
        if control_task:
            control_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await control_task

        # Close progress tracker
        if self._progress:
            self._progress.close()

        # Cancel running tasks
        for future in self._running_tasks.values():
            future.cancel()

        # Stop all terminals
        for terminal in self.terminals.values():
            try:
                await terminal.stop()
            except Exception as e:
                self._log_warning(f"Error stopping terminal: {e}")

        self.terminals.clear()
        self._running_tasks.clear()

        # Update final status
        self._update_status(
            {
                "state": "stopped",
                "stopped_at": datetime.now().isoformat(),
                "tasks": self.task_queue.get_status_summary(),
            }
        )

        self._log_success("Shutdown complete")

        # Flush remaining log entries
        self._flush_log_buffer()

    # =========================================================================
    # Reporting
    # =========================================================================

    def _generate_report(self) -> dict:
        """Generate a final execution report."""
        end_time = datetime.now()
        duration = (end_time - self.start_time).total_seconds() if self.start_time else 0

        completed_tasks = self.task_queue.completed
        successful = [t for t in completed_tasks if t.status == TaskStatus.COMPLETED]
        failed = [t for t in completed_tasks if t.status == TaskStatus.FAILED]

        # Count retries
        total_retries = sum(self._retry_counts.values())

        # Determine status
        if self._rate_limited:
            status = "rate_limited"
        elif not failed:
            status = "success"
        else:
            status = "partial"

        report = {
            "status": status,
            "duration_seconds": round(duration, 1),
            "rate_limited": self._rate_limited,
            "rate_limit_reset_time": self._rate_limit_reset_time,
            "tasks": {
                "total": len(completed_tasks)
                + len(self.task_queue.pending)
                + len(self.task_queue.in_progress),
                "completed": len(successful),
                "failed": len(failed),
                "pending": len(self.task_queue.pending),
                "total_retries": total_retries,
            },
            "completed_tasks": [{"title": t.title, "terminal": t.assigned_to} for t in successful],
            "failed_tasks": [
                {"title": t.title, "terminal": t.assigned_to, "error": t.error} for t in failed
            ],
        }

        # Print report
        print()
        print(f"{Colors.BOLD}{'='*60}{Colors.RESET}")
        print(f"{Colors.BOLD}EXECUTION REPORT{Colors.RESET}")
        print(f"{'='*60}")

        if self._rate_limited:
            print(f"Status: {Colors.RED}RATE LIMITED{Colors.RESET}")
            provider_label = self.config.llm_provider.upper()
            print(f"{Colors.YELLOW}{provider_label} rate limit reached!{Colors.RESET}")
            print(
                f"Reset time: {Colors.CYAN}{self._rate_limit_reset_time or 'Check provider dashboard'}{Colors.RESET}"
            )
            print()
            print(f"{Colors.DIM}Re-run this command after the rate limit resets.{Colors.RESET}")
        else:
            status_color = Colors.GREEN if status == "success" else Colors.YELLOW
            print(f"Status: {status_color}{status.upper()}{Colors.RESET}")

        print(f"Duration: {duration:.1f}s")
        print(
            f"Tasks: {Colors.GREEN}{report['tasks']['completed']}{Colors.RESET}/{report['tasks']['total']} completed"
        )

        if total_retries > 0:
            print(f"Retries: {Colors.YELLOW}{total_retries}{Colors.RESET}")

        if failed and not self._rate_limited:
            print(f"Failed: {Colors.RED}{len(failed)} tasks{Colors.RESET}")
            for f in failed:
                error_msg = f.get("error", "")
                # Don't show rate limit tasks as failures
                if "rate limit" not in error_msg.lower():
                    print(f"  {Colors.RED}✗{Colors.RESET} {f['title']}")

        print(f"{'='*60}")
        print()

        return report
