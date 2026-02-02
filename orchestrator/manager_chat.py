"""
Manager Chat - Interactive REPL for communicating with Archon during execution.

Provides:
- Real-time status queries
- Execution control (pause/resume)
- Task injection
- Natural language Q&A via Claude
- Organic flow commands (quality, contracts, flow, intervene)
"""

import asyncio
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from .orchestrator import Orchestrator

from .config import Config, TerminalID
from .cli_display import (
    Colors,
    c,
    quality_bar,
    quality_label,
    get_terminal_badge,
    print_organic_status,
    print_contracts_summary,
    print_intervention_help,
    print_flow_state,
    TerminalStatus,
    ContractDisplay,
    FlowState,
    InterventionType,
    TERMINAL_PERSONALITIES,
)


# =============================================================================
# ANSI Colors for Chat Output (using cli_display Colors)
# =============================================================================

class ChatColors:
    """Colors for chat interface - wraps cli_display.Colors."""

    RESET = Colors.RESET
    BOLD = Colors.BOLD
    DIM = Colors.DIM

    # Manager colors
    MANAGER = Colors.BRIGHT_CYAN
    USER = Colors.BRIGHT_WHITE
    SUCCESS = Colors.BRIGHT_GREEN
    WARNING = Colors.BRIGHT_YELLOW
    ERROR = Colors.BRIGHT_RED
    INFO = Colors.BRIGHT_BLUE

    # Terminal colors (use personality colors)
    T1 = Colors.BRIGHT_CYAN
    T2 = Colors.BRIGHT_MAGENTA
    T3 = Colors.BRIGHT_YELLOW
    T4 = Colors.BRIGHT_BLUE
    T5 = Colors.BRIGHT_RED


# =============================================================================
# Chat History
# =============================================================================

class ChatHistory:
    """Manages chat history for context."""

    def __init__(self, config: Config, max_entries: int = 50):
        self.config = config
        self.max_entries = max_entries
        self.history_file = config.orchestra_dir / "chat_history.json"
        self.entries: list[dict] = []
        self._load()

    def _load(self) -> None:
        """Load history from file."""
        if self.history_file.exists():
            try:
                self.entries = json.loads(self.history_file.read_text())
            except (json.JSONDecodeError, IOError):
                self.entries = []

    def _save(self) -> None:
        """Save history to file."""
        self.config.ensure_dirs()
        self.history_file.write_text(json.dumps(self.entries[-self.max_entries:], indent=2))

    def add(self, role: str, content: str) -> None:
        """Add an entry to history."""
        self.entries.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        })
        # Keep only recent entries
        if len(self.entries) > self.max_entries:
            self.entries = self.entries[-self.max_entries:]
        self._save()

    def get_recent(self, count: int = 10) -> list[dict]:
        """Get recent history entries."""
        return self.entries[-count:]

    def clear(self) -> None:
        """Clear history."""
        self.entries = []
        self._save()


# =============================================================================
# Manager Chat Core
# =============================================================================

class ManagerChat:
    """
    Interactive chat interface for the orchestrator.

    Handles user input, executes commands, and provides intelligent
    responses about execution state via Claude.
    """

    # Built-in commands - organized by category
    COMMANDS = {
        # Status & Monitoring
        "status": "Show overall execution status",
        "status <t1-t5>": "Show specific terminal status",
        "quality": "Show quality gradients for all terminals",
        "flow": "Show current flow state (organic model)",
        "contracts": "Show all active interface contracts",

        # Control
        "pause": "Pause execution (current tasks will complete)",
        "resume": "Resume execution",

        # Task Management
        "inject: <task>": "Inject a new task into the queue",
        "cancel <task_id>": "Cancel a pending task",
        "tasks": "List all tasks with status",

        # Organic Interventions
        "intervene": "Show intervention types",
        "intervene <type> <target>": "Manual intervention (AMPLIFY, REDIRECT, etc.)",

        # Info
        "reports": "Show recent reports from terminals",
        "help": "Show this help message",
        "quit": "Exit chat (orchestrator continues)",
    }

    def __init__(self, orchestrator: "Orchestrator", config: Config):
        self.orchestrator = orchestrator
        self.config = config
        self.history = ChatHistory(config)
        self._running = True

    def _print_manager(self, message: str, color: str = ChatColors.MANAGER) -> None:
        """Print a message from the manager."""
        print(f"{color}[Manager]{ChatColors.RESET} {message}")

    def _print_error(self, message: str) -> None:
        """Print an error message."""
        print(f"{ChatColors.ERROR}[Error]{ChatColors.RESET} {message}")

    def _print_success(self, message: str) -> None:
        """Print a success message."""
        print(f"{ChatColors.SUCCESS}[OK]{ChatColors.RESET} {message}")

    def _get_terminal_color(self, terminal_id: str) -> str:
        """Get color for a terminal."""
        personality = TERMINAL_PERSONALITIES.get(terminal_id)
        if personality:
            return personality.color
        return ChatColors.INFO

    # =========================================================================
    # Command Parsing
    # =========================================================================

    def parse_command(self, text: str) -> tuple[str, str]:
        """
        Parse user input into command and arguments.

        Returns:
            Tuple of (command, arguments)
        """
        text = text.strip()

        if not text:
            return "", ""

        # Check for inject command with colon
        if text.lower().startswith("inject:"):
            return "inject", text[7:].strip()

        # Check for cancel command
        if text.lower().startswith("cancel "):
            return "cancel", text[7:].strip()

        # Check for status with terminal ID
        if text.lower().startswith("status "):
            return "status", text[7:].strip()

        # Check for intervene command
        if text.lower().startswith("intervene"):
            parts = text.split(maxsplit=1)
            args = parts[1] if len(parts) > 1 else ""
            return "intervene", args

        # Simple commands (including new organic commands)
        lower = text.lower()
        simple_commands = [
            "status", "pause", "resume", "tasks", "reports", "help",
            "quit", "exit", "q",
            # New organic commands
            "quality", "flow", "contracts", "intervene",
        ]

        if lower in simple_commands:
            if lower in ["exit", "q"]:
                return "quit", ""
            return lower, ""

        # Natural language query
        return "query", text

    # =========================================================================
    # Command Handlers
    # =========================================================================

    async def cmd_status(self, args: str = "") -> str:
        """Handle status command."""
        status = self.orchestrator.get_detailed_status()

        if args and args.lower() in ["t1", "t2", "t3", "t4", "t5"]:
            # Terminal-specific status
            return self._format_terminal_status(args.lower(), status)
        else:
            # Overall status
            return self._format_overall_status(status)

    def _format_overall_status(self, status: dict) -> str:
        """Format overall execution status."""
        lines = []

        # State
        state = status.get("state", "unknown")
        paused = status.get("paused", False)
        state_str = f"{ChatColors.WARNING}PAUSED{ChatColors.RESET}" if paused else f"{ChatColors.SUCCESS}{state.upper()}{ChatColors.RESET}"
        lines.append(f"State: {state_str}")

        # Phase
        phase = status.get("phase", 1)
        phase_names = {1: "Build", 2: "Integrate", 3: "Test"}
        lines.append(f"Phase: {phase} ({phase_names.get(phase, 'Unknown')})")

        # Tasks
        tasks = status.get("tasks", {})
        completed = tasks.get("completed_count", 0)
        pending = tasks.get("pending_count", 0)
        in_progress = tasks.get("in_progress_count", 0)
        failed = tasks.get("failed_count", 0)
        total = tasks.get("total_count", 0)

        lines.append("")
        lines.append(f"Tasks: {ChatColors.SUCCESS}{completed}{ChatColors.RESET}/{total} completed")
        if pending > 0:
            lines.append(f"  Pending: {ChatColors.WARNING}{pending}{ChatColors.RESET}")
        if in_progress > 0:
            lines.append(f"  In Progress: {ChatColors.INFO}{in_progress}{ChatColors.RESET}")
        if failed > 0:
            lines.append(f"  Failed: {ChatColors.ERROR}{failed}{ChatColors.RESET}")

        # Terminals
        lines.append("")
        lines.append("Terminals:")
        terminals = status.get("terminals", {})
        terminal_names = {"t1": "UI/UX", "t2": "Features", "t3": "Docs", "t4": "Strategy"}

        for tid in ["t1", "t2", "t3", "t4", "t5"]:
            t_info = terminals.get(tid, {})
            t_state = t_info.get("state", "unknown")
            t_task = t_info.get("current_task", None)
            color = self._get_terminal_color(tid)

            status_str = f"{ChatColors.SUCCESS}idle{ChatColors.RESET}" if t_state == "idle" else f"{ChatColors.INFO}working{ChatColors.RESET}"
            task_str = f" - {t_task[:40]}..." if t_task else ""

            lines.append(f"  {color}[{tid.upper()}]{ChatColors.RESET} {terminal_names[tid]}: {status_str}{task_str}")

        return "\n".join(lines)

    def _format_terminal_status(self, terminal_id: str, status: dict) -> str:
        """Format status for a specific terminal."""
        lines = []
        color = self._get_terminal_color(terminal_id)
        terminal_names = {"t1": "UI/UX", "t2": "Features", "t3": "Docs", "t4": "Strategy"}

        lines.append(f"{color}[{terminal_id.upper()}]{ChatColors.RESET} {terminal_names.get(terminal_id, 'Unknown')}")
        lines.append("")

        # Terminal state
        terminals = status.get("terminals", {})
        t_info = terminals.get(terminal_id, {})
        t_state = t_info.get("state", "unknown")
        current_task = t_info.get("current_task")

        lines.append(f"State: {t_state}")
        if current_task:
            lines.append(f"Current Task: {current_task}")

        # Recent reports
        reports = self.orchestrator.report_manager.get_reports_for_terminal(terminal_id, limit=3)
        if reports:
            lines.append("")
            lines.append("Recent Work:")
            for report in reports:
                lines.append(f"  - {report.summary[:60]}...")
                if report.components_created:
                    lines.append(f"    Components: {', '.join(report.components_created[:3])}")
                if report.files_created:
                    lines.append(f"    Files: {', '.join(report.files_created[:3])}")

        return "\n".join(lines)

    async def cmd_pause(self) -> str:
        """Handle pause command."""
        if not self.orchestrator._paused.is_set():
            return "Execution is already paused."

        await self.orchestrator.pause()
        return "Execution paused. Current tasks will complete, no new tasks will start.\nUse 'resume' to continue."

    async def cmd_resume(self) -> str:
        """Handle resume command."""
        if self.orchestrator._paused.is_set():
            return "Execution is not paused."

        await self.orchestrator.resume()
        status = self.orchestrator.get_detailed_status()
        pending = status.get("tasks", {}).get("pending_count", 0)
        return f"Execution resumed. {pending} tasks remaining."

    async def cmd_inject(self, task_description: str) -> str:
        """Handle inject command to add a new task."""
        if not task_description:
            return "Please provide a task description. Example: inject: Add dark mode support"

        # Determine which terminal should handle this task
        terminal_id = self.config.route_task_to_terminal(task_description)

        # Add the task
        task = await self.orchestrator.inject_task(
            title=task_description[:80],
            description=task_description,
            terminal_id=terminal_id,
        )

        terminal_names = {"t1": "UI/UX", "t2": "Features", "t3": "Docs", "t4": "Strategy"}
        return f"Task injected: \"{task.title}\"\nAssigned to: {terminal_id.upper()} ({terminal_names.get(terminal_id, 'Unknown')})\nTask ID: {task.id}"

    async def cmd_cancel(self, task_id: str) -> str:
        """Handle cancel command."""
        if not task_id:
            return "Please provide a task ID. Use 'tasks' to see pending tasks."

        success = await self.orchestrator.cancel_task(task_id)
        if success:
            return f"Task {task_id} cancelled."
        else:
            return f"Could not cancel task {task_id}. It may not exist or already be in progress."

    async def cmd_tasks(self) -> str:
        """Handle tasks command to list all tasks."""
        status = self.orchestrator.get_detailed_status()
        tasks_info = status.get("tasks", {})

        lines = ["Task List:", ""]

        # In Progress
        in_progress = tasks_info.get("in_progress_tasks", [])
        if in_progress:
            lines.append(f"{ChatColors.INFO}In Progress:{ChatColors.RESET}")
            for t in in_progress:
                color = self._get_terminal_color(t.get("assigned_to", ""))
                lines.append(f"  {color}[{t.get('assigned_to', '?').upper()}]{ChatColors.RESET} {t.get('title', 'Unknown')}")
            lines.append("")

        # Pending
        pending = tasks_info.get("pending_tasks", [])
        if pending:
            lines.append(f"{ChatColors.WARNING}Pending:{ChatColors.RESET}")
            for t in pending:
                lines.append(f"  - {t.get('title', 'Unknown')} (ID: {t.get('id', '?')})")
            total_pending = tasks_info.get("pending_count", 0)
            if total_pending > len(pending):
                lines.append(f"  ... and {total_pending - len(pending)} more")
            lines.append("")

        # Summary
        completed = tasks_info.get("completed_count", 0)
        failed = tasks_info.get("failed_count", 0)
        total = tasks_info.get("total_count", 0)

        lines.append(f"Summary: {ChatColors.SUCCESS}{completed}{ChatColors.RESET} completed, {ChatColors.ERROR}{failed}{ChatColors.RESET} failed, {total} total")

        return "\n".join(lines)

    async def cmd_reports(self) -> str:
        """Handle reports command to show recent terminal reports."""
        lines = ["Recent Reports:", ""]

        for tid in ["t1", "t2", "t3", "t4", "t5"]:
            reports = self.orchestrator.report_manager.get_reports_for_terminal(tid, limit=2)
            if reports:
                badge = get_terminal_badge(tid)
                lines.append(badge)

                for report in reports:
                    lines.append(f"  {report.summary[:70]}...")
                    if report.components_created:
                        lines.append(f"    Components: {', '.join(report.components_created[:4])}")

                lines.append("")

        if len(lines) == 2:  # Only header
            lines.append("No reports yet.")

        return "\n".join(lines)

    # =========================================================================
    # Organic Model Commands
    # =========================================================================

    async def cmd_quality(self) -> str:
        """Handle quality command - show quality gradients for all terminals."""
        lines = [c("Quality Gradients:", Colors.BOLD, Colors.WHITE), ""]

        status = self.orchestrator.get_detailed_status()
        terminals = status.get("terminals", {})

        for tid in ["t1", "t2", "t3", "t4", "t5"]:
            t_info = terminals.get(tid, {})
            personality = TERMINAL_PERSONALITIES.get(tid)

            if not personality:
                continue

            # Get quality from reports (estimate based on completed tasks)
            reports = self.orchestrator.report_manager.get_reports_for_terminal(tid, limit=5)

            # Estimate quality based on report completeness
            if reports:
                # Simple heuristic: more components + files = higher quality
                total_components = sum(len(r.components_created) for r in reports)
                total_files = sum(len(r.files_created) + len(r.files_modified) for r in reports)
                # Rough quality estimate
                quality = min(1.0, (total_components * 0.1 + total_files * 0.05 + 0.2))
            else:
                quality = 0.0

            # Current work
            current_task = t_info.get("current_task")
            work_str = current_task[:30] if current_task else "(idle)"

            # Build display line
            badge = get_terminal_badge(tid, include_name=True)
            qbar = quality_bar(quality, 10)
            qlabel = quality_label(quality)

            lines.append(f"  {badge}")
            lines.append(f"    {qbar} {quality:.2f} - {qlabel}")
            lines.append(f"    Current: {c(work_str, Colors.DIM)}")
            lines.append("")

        return "\n".join(lines)

    async def cmd_contracts(self) -> str:
        """Handle contracts command - show all interface contracts."""
        lines = [c("Interface Contracts:", Colors.BOLD, Colors.WHITE), ""]

        # Get contracts from contract manager
        contracts = self.orchestrator.contract_manager.list_contracts()

        if not contracts:
            lines.append(c("  No contracts defined yet.", Colors.DIM))
            lines.append("")
            lines.append(c("  Contracts are created when T1/T2 define interface expectations.", Colors.DIM))
            return "\n".join(lines)

        # Group by status
        status_groups = {"proposed": [], "implemented": [], "verified": []}
        for contract in contracts:
            status_groups[contract.status].append(contract)

        status_colors = {
            "proposed": Colors.BRIGHT_YELLOW,
            "implemented": Colors.BRIGHT_CYAN,
            "verified": Colors.BRIGHT_GREEN,
        }

        status_icons = {
            "proposed": "[?]",
            "implemented": "[>]",
            "verified": "[+]",
        }

        for status_name, status_contracts in status_groups.items():
            if status_contracts:
                color = status_colors[status_name]
                lines.append(c(f"  {status_name.upper()} ({len(status_contracts)}):", color, Colors.BOLD))

                for contract in status_contracts:
                    icon = c(status_icons[status_name], color)
                    defined_by = get_terminal_badge(contract.defined_by, include_name=False)

                    impl_str = ""
                    if contract.implemented_by:
                        impl_by = get_terminal_badge(contract.implemented_by, include_name=False)
                        impl_str = f" -> {impl_by}"

                    lines.append(f"    {icon} {c(contract.name, Colors.WHITE)} {defined_by}{impl_str}")

                lines.append("")

        # Summary
        total = len(contracts)
        verified = len(status_groups["verified"])
        lines.append(c(f"  Total: {total} contracts, {verified} verified", Colors.DIM))

        return "\n".join(lines)

    async def cmd_flow(self) -> str:
        """Handle flow command - show current organic flow state."""
        lines = [c("Organic Flow State:", Colors.BOLD, Colors.WHITE), ""]

        status = self.orchestrator.get_detailed_status()
        terminals = status.get("terminals", {})
        tasks = status.get("tasks", {})

        # Determine overall flow state
        in_progress_count = tasks.get("in_progress_count", 0)
        pending_count = tasks.get("pending_count", 0)
        paused = status.get("paused", False)

        flowing_terminals = []
        blocked_terminals = []
        idle_terminals = []

        for tid in ["t1", "t2", "t3", "t4", "t5"]:
            t_info = terminals.get(tid, {})
            state = t_info.get("state", "unknown")
            current_task = t_info.get("current_task")

            if current_task:
                flowing_terminals.append(tid)
            elif state == "blocked" or state == "error":
                blocked_terminals.append(tid)
            else:
                idle_terminals.append(tid)

        # Overall state
        if paused:
            overall_state: FlowState = "syncing"
            state_desc = "PAUSED"
            state_color = Colors.BRIGHT_YELLOW
        elif blocked_terminals and not flowing_terminals:
            overall_state = "blocked"
            state_desc = "BLOCKED"
            state_color = Colors.BRIGHT_RED
        elif in_progress_count == 0 and pending_count == 0:
            overall_state = "completing"
            state_desc = "COMPLETING"
            state_color = Colors.BRIGHT_GREEN
        elif flowing_terminals:
            overall_state = "flowing"
            state_desc = "FLOWING"
            state_color = Colors.BRIGHT_GREEN
        else:
            overall_state = "idle"
            state_desc = "IDLE"
            state_color = Colors.DIM

        lines.append(f"  Overall: {c(state_desc, state_color, Colors.BOLD)}")
        lines.append("")

        # Terminal states
        if flowing_terminals:
            badges = " ".join(get_terminal_badge(t, include_name=False) for t in flowing_terminals)
            lines.append(f"  {c('Flowing:', Colors.BRIGHT_GREEN)} {badges}")

        if blocked_terminals:
            badges = " ".join(get_terminal_badge(t, include_name=False) for t in blocked_terminals)
            lines.append(f"  {c('Blocked:', Colors.BRIGHT_RED)} {badges}")

        if idle_terminals:
            badges = " ".join(get_terminal_badge(t, include_name=False) for t in idle_terminals)
            lines.append(f"  {c('Idle:', Colors.DIM)} {badges}")

        lines.append("")

        # Task flow stats
        completed = tasks.get("completed_count", 0)
        total = tasks.get("total_count", 0)

        if total > 0:
            progress = completed / total
            progress_bar = quality_bar(progress, 20)
            lines.append(f"  Progress: {progress_bar} {completed}/{total}")
        else:
            lines.append(f"  Progress: {c('No tasks yet', Colors.DIM)}")

        # Phase info (still useful context)
        phase = status.get("phase", 1)
        phase_names = {1: "Build", 2: "Integrate", 3: "Test"}
        lines.append(f"  Phase: {phase} ({phase_names.get(phase, 'Unknown')})")

        return "\n".join(lines)

    async def cmd_intervene(self, args: str = "") -> str:
        """Handle intervene command - manual interventions."""
        if not args:
            # Show intervention help
            lines = [c("Intervention Types:", Colors.BOLD, Colors.WHITE), ""]

            interventions = [
                ("AMPLIFY", Colors.BRIGHT_GREEN, "Boost priority of promising work"),
                ("REDIRECT", Colors.BRIGHT_YELLOW, "Change direction of a terminal"),
                ("BRIDGE", Colors.BRIGHT_CYAN, "Connect two terminals' work"),
                ("CLARIFY", Colors.BRIGHT_BLUE, "Request clarification from terminal"),
                ("ACCELERATE", Colors.BRIGHT_MAGENTA, "Speed up slow progress"),
                ("PAUSE", Colors.BRIGHT_RED, "Temporarily pause terminal"),
            ]

            for name, color, desc in interventions:
                lines.append(f"  {c(name.ljust(12), color, Colors.BOLD)} {desc}")

            lines.append("")
            lines.append(c("  Usage: intervene <TYPE> <target> [message]", Colors.DIM))
            lines.append(c("  Example: intervene AMPLIFY t1", Colors.DIM))
            lines.append(c("  Example: intervene REDIRECT t2 'Focus on API endpoints'", Colors.DIM))

            return "\n".join(lines)

        # Parse intervention
        parts = args.split(maxsplit=2)
        if len(parts) < 2:
            return c("Usage: intervene <TYPE> <target> [message]", Colors.BRIGHT_RED)

        intervention_type = parts[0].upper()
        target = parts[1].lower()
        message = parts[2] if len(parts) > 2 else None

        valid_types = ["AMPLIFY", "REDIRECT", "BRIDGE", "CLARIFY", "ACCELERATE", "PAUSE"]
        if intervention_type not in valid_types:
            return c(f"Unknown intervention type: {intervention_type}. Valid: {', '.join(valid_types)}", Colors.BRIGHT_RED)

        valid_targets = ["t1", "t2", "t3", "t4", "t5"]
        if target not in valid_targets:
            return c(f"Unknown target: {target}. Valid: {', '.join(valid_targets)}", Colors.BRIGHT_RED)

        # Execute intervention
        return await self._execute_intervention(intervention_type, target, message)

    async def _execute_intervention(
        self,
        intervention_type: str,
        target: str,
        message: str | None,
    ) -> str:
        """Execute an intervention action."""
        # Build intervention message for the message bus
        intervention_colors = {
            "AMPLIFY": Colors.BRIGHT_GREEN,
            "REDIRECT": Colors.BRIGHT_YELLOW,
            "BRIDGE": Colors.BRIGHT_CYAN,
            "CLARIFY": Colors.BRIGHT_BLUE,
            "ACCELERATE": Colors.BRIGHT_MAGENTA,
            "PAUSE": Colors.BRIGHT_RED,
        }

        color = intervention_colors.get(intervention_type, Colors.WHITE)

        if intervention_type == "AMPLIFY":
            broadcast = f"## INTERVENTION: AMPLIFY\n\n{target.upper()}, your current work looks promising. Continue with higher priority.\n\n{message or ''}"
        elif intervention_type == "REDIRECT":
            if not message:
                return c("REDIRECT requires a message. Usage: intervene REDIRECT t2 'Focus on X'", Colors.BRIGHT_RED)
            broadcast = f"## INTERVENTION: REDIRECT\n\n{target.upper()}, please adjust focus:\n\n{message}"
        elif intervention_type == "BRIDGE":
            broadcast = f"## INTERVENTION: BRIDGE\n\n{target.upper()}, coordinate with other terminals on current work.\n\n{message or 'Check reports from other terminals.'}"
        elif intervention_type == "CLARIFY":
            broadcast = f"## INTERVENTION: CLARIFY\n\n{target.upper()}, please provide clarification on your current progress.\n\n{message or ''}"
        elif intervention_type == "ACCELERATE":
            broadcast = f"## INTERVENTION: ACCELERATE\n\n{target.upper()}, please speed up current work. Skip non-essential polish.\n\n{message or ''}"
        elif intervention_type == "PAUSE":
            broadcast = f"## INTERVENTION: PAUSE\n\n{target.upper()}, please pause current work until further notice.\n\n{message or ''}"
        else:
            return c(f"Unknown intervention: {intervention_type}", Colors.BRIGHT_RED)

        # Send via message bus
        self.orchestrator.message_bus.send(
            sender="manager",
            recipient=target,  # type: ignore
            content=broadcast,
            msg_type="intervention",
            metadata={"intervention_type": intervention_type},
        )

        # Log the intervention
        self.orchestrator.event_logger.log_event("intervention", {
            "type": intervention_type,
            "target": target,
            "message": message,
        })

        return c(f"Intervention {intervention_type} sent to {target.upper()}", color, Colors.BOLD)

    def cmd_help(self) -> str:
        """Handle help command with categorized display."""
        lines = [c("Manager Chat Commands:", Colors.BOLD, Colors.WHITE), ""]

        # Group commands by category
        categories = {
            "Status & Monitoring": [
                ("status", "Show overall execution status"),
                ("status <t1-t5>", "Show specific terminal status"),
                ("quality", "Show quality gradients for all terminals"),
                ("flow", "Show current flow state (organic model)"),
                ("contracts", "Show all active interface contracts"),
            ],
            "Control": [
                ("pause", "Pause execution"),
                ("resume", "Resume execution"),
            ],
            "Task Management": [
                ("inject: <task>", "Inject a new task into the queue"),
                ("cancel <id>", "Cancel a pending task"),
                ("tasks", "List all tasks with status"),
            ],
            "Interventions": [
                ("intervene", "Show intervention types"),
                ("intervene <type> <target>", "Manual intervention"),
            ],
            "Info": [
                ("reports", "Show recent reports from terminals"),
                ("help", "Show this help message"),
                ("quit", "Exit chat (orchestrator continues)"),
            ],
        }

        for category, commands in categories.items():
            lines.append(c(f"  {category}:", Colors.BRIGHT_CYAN, Colors.BOLD))
            for cmd, desc in commands:
                lines.append(f"    {c(cmd.ljust(26), Colors.WHITE)} {c(desc, Colors.DIM)}")
            lines.append("")

        lines.append(c("  Natural Language:", Colors.BRIGHT_CYAN, Colors.BOLD))
        lines.append(f"    {c('Ask anything about the execution state.', Colors.DIM)}")
        lines.append(f"    {c('Example: \"What has T2 built?\" or \"Why is T1 slow?\"', Colors.DIM)}")

        return "\n".join(lines)

    # =========================================================================
    # Claude Integration for Natural Language
    # =========================================================================

    async def ask_claude(self, query: str) -> str:
        """
        Use Claude to answer natural language questions about execution.

        Args:
            query: User's natural language question

        Returns:
            Claude's response
        """
        # Gather context
        status = self.orchestrator.get_detailed_status()
        reports = self.orchestrator.report_manager.get_all_components()
        recent_history = self.history.get_recent(5)

        # Build prompt
        prompt = f"""You are the Manager Assistant for Archon, a multi-terminal orchestration system.
Answer the user's question concisely based on the current execution state.

## Current Execution State

{json.dumps(status, indent=2)}

## Terminal Components Created

{json.dumps(reports, indent=2)}

## Recent Chat History

{json.dumps(recent_history, indent=2)}

## User Question

{query}

## Instructions

- Be concise (2-4 sentences max)
- Reference specific terminals (T1=UI/UX, T2=Features, T3=Docs, T4=Strategy)
- If you don't have enough information, say so
- Provide actionable insights when possible
"""

        try:
            # Use claude --print for quick response
            result = subprocess.run(
                ["claude", "--print", "-p", prompt],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
            else:
                return "I couldn't process that question. Try rephrasing or use a specific command like 'status'."

        except subprocess.TimeoutExpired:
            return "Response timed out. Try a simpler question or use 'status' for quick info."
        except FileNotFoundError:
            return "Claude CLI not available. Use built-in commands like 'status', 'tasks', 'reports'."
        except Exception as e:
            return f"Error: {str(e)}"

    # =========================================================================
    # Main Processing
    # =========================================================================

    async def process_input(self, text: str) -> str:
        """
        Process user input and return response.

        Args:
            text: User's input text

        Returns:
            Response string
        """
        # Add to history
        self.history.add("user", text)

        # Parse command
        cmd, args = self.parse_command(text)

        # Execute command
        if cmd == "status":
            response = await self.cmd_status(args)
        elif cmd == "pause":
            response = await self.cmd_pause()
        elif cmd == "resume":
            response = await self.cmd_resume()
        elif cmd == "inject":
            response = await self.cmd_inject(args)
        elif cmd == "cancel":
            response = await self.cmd_cancel(args)
        elif cmd == "tasks":
            response = await self.cmd_tasks()
        elif cmd == "reports":
            response = await self.cmd_reports()
        # New organic commands
        elif cmd == "quality":
            response = await self.cmd_quality()
        elif cmd == "contracts":
            response = await self.cmd_contracts()
        elif cmd == "flow":
            response = await self.cmd_flow()
        elif cmd == "intervene":
            response = await self.cmd_intervene(args)
        elif cmd == "help":
            response = self.cmd_help()
        elif cmd == "quit":
            self._running = False
            response = "Exiting chat. Orchestrator continues in background."
        elif cmd == "query":
            # Natural language - use Claude
            response = await self.ask_claude(args)
        else:
            response = f"Unknown command: {cmd}. Type 'help' for available commands."

        # Add response to history
        self.history.add("manager", response)

        return response

    @property
    def is_running(self) -> bool:
        """Check if chat is still active."""
        return self._running

    def stop(self) -> None:
        """Stop the chat loop."""
        self._running = False


# =============================================================================
# Chat REPL
# =============================================================================

async def chat_repl(manager: ManagerChat) -> None:
    """
    Run the chat REPL loop.

    Args:
        manager: ManagerChat instance to use
    """
    # Print welcome message
    print()
    print(c("    ╭" + "─" * 48 + "╮", Colors.BRIGHT_CYAN))
    print(c("    │", Colors.BRIGHT_CYAN) + c("  ARCHON - Manager Chat", Colors.BRIGHT_WHITE, Colors.BOLD) + " " * 24 + c("│", Colors.BRIGHT_CYAN))
    print(c("    │", Colors.BRIGHT_CYAN) + c("  Organic Flow Control Interface", Colors.DIM) + " " * 15 + c("│", Colors.BRIGHT_CYAN))
    print(c("    ╰" + "─" * 48 + "╯", Colors.BRIGHT_CYAN))
    print()
    print(c("    Commands: status, quality, flow, contracts, intervene, help", Colors.DIM))
    print(c("    Type 'quit' to exit (orchestrator continues)", Colors.DIM))
    print()

    while manager.is_running:
        try:
            # Get user input
            user_input = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: input(f"{ChatColors.USER}> {ChatColors.RESET}")
            )

            if not user_input.strip():
                continue

            # Process input
            response = await manager.process_input(user_input)

            # Print response
            print()
            manager._print_manager(response)
            print()

        except EOFError:
            # Handle Ctrl+D
            manager.stop()
            print()
            manager._print_manager("Chat ended. Orchestrator continues.")
            break
        except KeyboardInterrupt:
            # Handle Ctrl+C - just continue (don't stop orchestrator)
            print()
            manager._print_manager("Use 'quit' to exit chat, or Ctrl+C again to stop orchestrator.")
            continue
        except Exception as e:
            print()
            manager._print_error(f"Error: {str(e)}")
            print()
