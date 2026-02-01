"""
Main Orchestrator - Coordinates all terminals and manages the workflow.

This is the central controller that:
- Manages 4 Claude Code terminal workers
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
import json
import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable

from .config import Config, TerminalID
from .logger import EventLogger
from .message_bus import MessageBus
from .planner import Planner, TaskPlan
from .report_manager import ReportManager, Report
from .task_queue import TaskQueue, TaskPriority, Task, TaskStatus
from .terminal import Terminal, TerminalState


# =============================================================================
# Terminal Colors
# =============================================================================

class Colors:
    """ANSI color codes for terminal output."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # Standard colors
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"

    # Background colors
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"

    @classmethod
    def disable(cls):
        """Disable colors (for non-TTY output)."""
        cls.RESET = ""
        cls.BOLD = ""
        cls.DIM = ""
        cls.RED = ""
        cls.GREEN = ""
        cls.YELLOW = ""
        cls.BLUE = ""
        cls.MAGENTA = ""
        cls.CYAN = ""
        cls.WHITE = ""
        cls.BG_RED = ""
        cls.BG_GREEN = ""
        cls.BG_YELLOW = ""


# Check if we're outputting to a TTY
if not sys.stdout.isatty():
    Colors.disable()


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
            return self.retry_delay * (2 ** attempt)
        return self.retry_delay


# =============================================================================
# Main Orchestrator
# =============================================================================

class Orchestrator:
    """
    Main orchestrator that coordinates all components.

    Features:
    - Task distribution across 4 terminals
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
    ):
        self.config = config or Config()
        self.verbose = verbose
        self.retry_config = retry_config or RetryConfig()
        self.continuous_mode = continuous_mode
        self.enable_quality_check = enable_quality_check
        self.use_colors = use_colors
        self.use_progress_bar = use_progress_bar
        self.max_quality_iterations = max_quality_iterations

        # Disable colors if requested
        if not use_colors:
            Colors.disable()

        # Initialize components
        self.message_bus = MessageBus(self.config)
        self.task_queue = TaskQueue(self.config)
        self.planner = Planner(self.config)
        self.report_manager = ReportManager(self.config)
        self.event_logger = EventLogger(self.config.orchestra_dir / "events.json")

        # Terminal instances
        self.terminals: dict[TerminalID, Terminal] = {}

        # Running task futures
        self._running_tasks: dict[TerminalID, asyncio.Task] = {}

        # Retry tracking: task_id -> retry_count
        self._retry_counts: dict[str, int] = {}

        # Tasks pending retry
        self._retry_queue: list[tuple[Task, TerminalID]] = []

        # Progress tracker
        self._progress: ProgressTracker | None = None

        # Quality check iteration counter
        self._quality_check_iteration = 0
        self._processed_task_ids: set[str] = set()  # Track already quality-checked tasks

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

    def _handle_shutdown(self, signum, frame):
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
        """Write to orchestrator.log for dashboard consumption."""
        log_file = self.config.orchestra_dir / "orchestrator.log"
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"[{timestamp}] [{log_type.upper()}] {message}\n"
        try:
            with open(log_file, "a") as f:
                f.write(entry)
        except IOError:
            pass  # Ignore write errors

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
        except IOError:
            pass

    def _log_retry(self, terminal_id: str, task_title: str, attempt: int, max_attempts: int):
        """Log a retry attempt."""
        self._log_terminal(
            terminal_id,
            f"Retry {attempt}/{max_attempts}: {task_title}",
            Colors.YELLOW
        )

    # =========================================================================
    # Subagent Detection
    # =========================================================================

    def _detect_subagent_usage(self, terminal_id: str, task_title: str, output: str):
        """Detect and log subagent usage from task output."""
        subagents = [
            "swiftui-crafter", "react-crafter", "html-stylist", "design-system",
            "swift-architect", "node-architect", "python-architect",
            "swiftdata-expert", "database-expert", "ml-engineer",
            "tech-writer", "marketing-strategist",
            "product-thinker", "monetization-expert",
        ]
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
        self._update_status({
            "state": "initializing",
            "terminals": {},
            "tasks": self.task_queue.get_status_summary(),
            "started_at": datetime.now().isoformat(),
        })

        self._log_success("Orchestrator initialized")

    def _update_status(self, status: dict) -> None:
        """Update the status file."""
        self.config.status_file.write_text(json.dumps(status, indent=2))

    def _get_status(self) -> dict:
        """Get current status."""
        try:
            return json.loads(self.config.status_file.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    # =========================================================================
    # Terminal Management
    # =========================================================================

    async def spawn_terminals(self) -> None:
        """Create all 4 terminal workers."""
        self._log_info("Creating terminal workers...")

        for tid in ["t1", "t2", "t3", "t4"]:
            terminal_id: TerminalID = tid  # type: ignore
            await self._spawn_terminal(terminal_id)

        self._log_success(f"All {len(self.terminals)} terminals ready")

    async def _spawn_terminal(self, terminal_id: TerminalID) -> Terminal | None:
        """Spawn a single terminal."""
        try:
            config = self.config.get_terminal_config(terminal_id)
            prompt_file = self.config.templates_dir / config.prompt_file

            # Load system prompt from template
            system_prompt = None
            if prompt_file.exists():
                system_prompt = prompt_file.read_text()

            terminal = Terminal(
                terminal_id=terminal_id,
                working_dir=self.config.base_dir,
                system_prompt=system_prompt,
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
            try:
                await self.terminals[terminal_id].stop()
            except Exception:
                pass
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
        plan = self.planner.plan(task, project_context=project_context)

        self._log_success(f"Plan created: {plan.summary}")
        self._log_info(f"Total tasks: {len(plan.tasks)}")

        # Add tasks to queue with phase information
        for planned_task in plan.tasks:
            self.task_queue.add_task(
                title=planned_task.title,
                description=planned_task.description,
                priority=TaskPriority(planned_task.priority),
                dependencies=planned_task.dependencies,
                assigned_to=planned_task.terminal,
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

        try:
            output = await terminal.execute_task(
                prompt=prompt,
                task_id=task.id,
                timeout=self.config.terminal_timeout,
            )

            # Save terminal output for dashboard
            self._save_terminal_output(terminal_id, output.content)

            # Check for subagent usage in output
            self._detect_subagent_usage(terminal_id, task.title, output.content)

            # Check for rate limit
            if output.is_error and output.content.startswith("RATE_LIMIT:"):
                reset_time = output.content.replace("RATE_LIMIT:", "").strip()
                self._log_error(f"Claude rate limit reached! Resets: {reset_time}")
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
                return await self._handle_task_failure(terminal_id, task, "Task failed or timed out")
            else:
                # Parse output into structured report (Manager Intelligence)
                report = self.report_manager.parse_output_to_report(
                    output=output.content,
                    task_id=task.id,
                    task_title=task.title,
                    terminal_id=terminal_id,
                    success=True,
                )

                # Save the report
                self.report_manager.save_report(report)
                self._log_info(f"Report saved: {report.summary[:60]}...")

                # Notify other terminals of relevant info
                self._notify_terminals_of_completion(terminal_id, task, report)

                # Mark task complete
                self.task_queue.complete_task(
                    task.id,
                    result=output.content[:2000],
                    success=True,
                )

                self._log_terminal(terminal_id, f"Done: {task.title}", Colors.GREEN)
                self.event_logger.task_completed(terminal_id, task.id, task.title)

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

        # Determine who to notify
        recipients: set[TerminalID] = set()

        # Check explicit provides_to_others
        for provides in report.provides_to_others:
            target = provides.get("to", "all")
            if target == "all":
                recipients = {"t1", "t2", "t3", "t4"}
                break
            elif target in ["t1", "t2", "t3", "t4"]:
                recipients.add(target)  # type: ignore

        # If nothing explicit, notify based on task type
        if not recipients:
            # UI completion -> notify Features
            if completed_terminal == "t1":
                recipients.add("t2")
            # Features completion -> notify UI and Docs
            elif completed_terminal == "t2":
                recipients.add("t1")
                recipients.add("t3")
            # Strategy completion -> notify everyone
            elif completed_terminal == "t4":
                recipients = {"t1", "t2", "t3"}

        # Remove self
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

        for tid in ["t1", "t2", "t3", "t4"]:
            terminal_config = self.config.get_terminal_config(tid)  # type: ignore
            components = all_components.get(tid, [])  # type: ignore

            context_parts.append(f"### {tid.upper()} ({terminal_config.role})")
            if components:
                context_parts.append("Components: " + ", ".join(components[:10]))
            else:
                context_parts.append("No components yet")
            context_parts.append("")

        return "\n".join(context_parts)

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
            self._log_info(f"Quality check skipped (max iterations {self.max_quality_iterations} reached)")
            return []

        self._log_info(f"Running quality check (iteration {self._quality_check_iteration}/{self.max_quality_iterations})...")

        completed_tasks = self.task_queue.completed

        # Only check tasks that haven't been processed yet
        new_tasks = [t for t in completed_tasks if t.id not in self._processed_task_ids]

        # Mark all current tasks as processed
        for t in completed_tasks:
            self._processed_task_ids.add(t.id)

        # Skip Review/Fix tasks - don't create Review of Review
        original_tasks = [t for t in new_tasks
                         if not t.title.startswith("Review:")
                         and not t.title.startswith("Fix:")
                         and not t.metadata.get("is_fix_task")
                         and not t.metadata.get("is_review_task")]

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

        PARALLEL EXECUTION:
        - Phase 1: ALL terminals start immediately (no blocking dependencies)
        - Phase 2: Integration tasks (after Phase 1 completes)
        - Phase 3: Testing/verification tasks (after Phase 2 completes)
        """
        self._log_info("Starting PARALLEL task execution loop...")

        # Track current phase
        current_phase = 1
        phase_announced = {1: False, 2: False, 3: False}

        while self.is_running:
            # Check if shutdown was requested
            if self._shutdown_requested:
                break

            # Process retry queue first
            while self._retry_queue:
                task, terminal_id = self._retry_queue.pop(0)
                # Re-add to pending if not already there
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
                        failed=len([t for t in self.task_queue.completed if t.status.value == "failed"]),
                    )
                    break
                # Otherwise continue with fix tasks

            # Determine current phase from task completion state
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
                        terminal_id,
                        f"{phase_tag} Assigned: {assigned.title}",
                        Colors.CYAN
                    )

                    # Start task execution in background
                    future = asyncio.create_task(
                        self._execute_task_on_terminal(terminal_id, assigned)
                    )
                    self._running_tasks[terminal_id] = future

            # Update status with phase info
            self._update_status({
                "state": "running",
                "current_phase": current_phase,
                "terminals": {
                    tid: {
                        "state": t.state.value,
                        "current_task": t.current_task_id,
                    }
                    for tid, t in self.terminals.items()
                },
                "tasks": self.task_queue.get_status_summary(),
            })

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

        try:
            # Initialize
            await self.initialize()

            # Create terminals
            await self.spawn_terminals()

            if not self.terminals:
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
            return self._generate_report()

        finally:
            # Cleanup
            await self.shutdown()

    async def shutdown(self) -> None:
        """Shutdown all terminals and cleanup."""
        self._log_info("Shutting down...")
        self.is_running = False

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
        self._update_status({
            "state": "stopped",
            "stopped_at": datetime.now().isoformat(),
            "tasks": self.task_queue.get_status_summary(),
        })

        self._log_success("Shutdown complete")

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
                "total": len(completed_tasks) + len(self.task_queue.pending) + len(self.task_queue.in_progress),
                "completed": len(successful),
                "failed": len(failed),
                "pending": len(self.task_queue.pending),
                "total_retries": total_retries,
            },
            "completed_tasks": [
                {"title": t.title, "terminal": t.assigned_to}
                for t in successful
            ],
            "failed_tasks": [
                {"title": t.title, "terminal": t.assigned_to, "error": t.error}
                for t in failed
            ],
        }

        # Print report
        print()
        print(f"{Colors.BOLD}{'='*60}{Colors.RESET}")
        print(f"{Colors.BOLD}EXECUTION REPORT{Colors.RESET}")
        print(f"{'='*60}")

        if self._rate_limited:
            print(f"Status: {Colors.RED}RATE LIMITED{Colors.RESET}")
            print(f"{Colors.YELLOW}Claude rate limit reached!{Colors.RESET}")
            print(f"Reset time: {Colors.CYAN}{self._rate_limit_reset_time or 'Check Claude dashboard'}{Colors.RESET}")
            print()
            print(f"{Colors.DIM}Re-run this command after the rate limit resets.{Colors.RESET}")
        else:
            status_color = Colors.GREEN if status == "success" else Colors.YELLOW
            print(f"Status: {status_color}{status.upper()}{Colors.RESET}")

        print(f"Duration: {duration:.1f}s")
        print(f"Tasks: {Colors.GREEN}{report['tasks']['completed']}{Colors.RESET}/{report['tasks']['total']} completed")

        if total_retries > 0:
            print(f"Retries: {Colors.YELLOW}{total_retries}{Colors.RESET}")

        if failed and not self._rate_limited:
            print(f"Failed: {Colors.RED}{len(failed)} tasks{Colors.RESET}")
            for f in failed:
                error_msg = f.get('error', '')
                # Don't show rate limit tasks as failures
                if 'rate limit' not in error_msg.lower():
                    print(f"  {Colors.RED}✗{Colors.RESET} {f['title']}")

        print(f"{'='*60}")
        print()

        return report


# =============================================================================
# CLI Entry Point
# =============================================================================

def main():
    """CLI entry point for the orchestrator."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Archon Orchestrator - Multi-terminal task coordination"
    )
    parser.add_argument(
        "task",
        nargs="?",
        help="The task to execute (will prompt if not provided)"
    )
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="Run in continuous mode (don't exit after completion)"
    )
    parser.add_argument(
        "--no-quality-check",
        action="store_true",
        help="Disable quality check after task completion"
    )
    parser.add_argument(
        "--no-colors",
        action="store_true",
        help="Disable colored output"
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable progress bar"
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=2,
        help="Maximum retries per failed task (default: 2)"
    )
    parser.add_argument(
        "--retry-delay",
        type=float,
        default=2.0,
        help="Delay between retries in seconds (default: 2.0)"
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Quiet mode (less verbose output)"
    )

    args = parser.parse_args()

    # Get task from argument or prompt
    task = args.task
    if not task:
        if not args.no_colors:
            print(f"{Colors.CYAN}Archon Orchestrator{Colors.RESET}")
            print()
        task = input("Enter your task: ").strip()
        if not task:
            print("No task provided. Exiting.")
            return

    # Create orchestrator
    orchestrator = Orchestrator(
        verbose=not args.quiet,
        retry_config=RetryConfig(
            max_retries=args.max_retries,
            retry_delay=args.retry_delay,
        ),
        continuous_mode=args.continuous,
        enable_quality_check=not args.no_quality_check,
        use_colors=not args.no_colors,
        use_progress_bar=not args.no_progress,
    )

    # Run
    asyncio.run(orchestrator.run(task))


if __name__ == "__main__":
    main()
