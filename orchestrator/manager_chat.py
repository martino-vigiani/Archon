"""
Manager Chat - Interactive REPL for communicating with Archon during execution.

Provides:
- Real-time status queries
- Execution control (pause/resume)
- Task injection
- Natural language Q&A via Claude
"""

import asyncio
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .orchestrator import Orchestrator

from .config import Config, TerminalID


# =============================================================================
# ANSI Colors for Chat Output
# =============================================================================

class ChatColors:
    """Colors for chat interface."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # Manager colors
    MANAGER = "\033[96m"      # Cyan
    USER = "\033[97m"         # White
    SUCCESS = "\033[92m"      # Green
    WARNING = "\033[93m"      # Yellow
    ERROR = "\033[91m"        # Red
    INFO = "\033[94m"         # Blue

    # Terminal colors
    T1 = "\033[96m"   # Cyan - UI/UX
    T2 = "\033[95m"   # Magenta - Features
    T3 = "\033[93m"   # Yellow - Docs
    T4 = "\033[94m"   # Blue - Strategy

    @classmethod
    def disable(cls):
        """Disable colors for non-TTY output."""
        for attr in dir(cls):
            if not attr.startswith('_') and attr != 'disable':
                setattr(cls, attr, "")


# Disable colors if not a TTY
if not sys.stdout.isatty():
    ChatColors.disable()


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

    # Built-in commands
    COMMANDS = {
        "status": "Show overall execution status",
        "status t1": "Show T1 (UI/UX) terminal status",
        "status t2": "Show T2 (Features) terminal status",
        "status t3": "Show T3 (Docs) terminal status",
        "status t4": "Show T4 (Strategy) terminal status",
        "pause": "Pause execution (current tasks will complete)",
        "resume": "Resume execution",
        "inject: <task>": "Inject a new task into the queue",
        "cancel <task_id>": "Cancel a pending task",
        "tasks": "List all tasks with status",
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
        return {
            "t1": ChatColors.T1,
            "t2": ChatColors.T2,
            "t3": ChatColors.T3,
            "t4": ChatColors.T4,
        }.get(terminal_id, ChatColors.INFO)

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

        # Simple commands
        lower = text.lower()
        if lower in ["status", "pause", "resume", "tasks", "reports", "help", "quit", "exit", "q"]:
            return lower if lower not in ["exit", "q"] else "quit", ""

        # Natural language query
        return "query", text

    # =========================================================================
    # Command Handlers
    # =========================================================================

    async def cmd_status(self, args: str = "") -> str:
        """Handle status command."""
        status = self.orchestrator.get_detailed_status()

        if args and args.lower() in ["t1", "t2", "t3", "t4"]:
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

        for tid in ["t1", "t2", "t3", "t4"]:
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
        terminal_names = {"t1": "UI/UX", "t2": "Features", "t3": "Docs", "t4": "Strategy"}

        for tid in ["t1", "t2", "t3", "t4"]:
            reports = self.orchestrator.report_manager.get_reports_for_terminal(tid, limit=2)
            if reports:
                color = self._get_terminal_color(tid)
                lines.append(f"{color}[{tid.upper()}] {terminal_names.get(tid, '')}{ChatColors.RESET}")

                for report in reports:
                    lines.append(f"  {report.summary[:70]}...")
                    if report.components_created:
                        lines.append(f"    Components: {', '.join(report.components_created[:4])}")

                lines.append("")

        if len(lines) == 2:  # Only header
            lines.append("No reports yet.")

        return "\n".join(lines)

    def cmd_help(self) -> str:
        """Handle help command."""
        lines = ["Available Commands:", ""]

        for cmd, desc in self.COMMANDS.items():
            lines.append(f"  {ChatColors.BOLD}{cmd}{ChatColors.RESET}")
            lines.append(f"    {ChatColors.DIM}{desc}{ChatColors.RESET}")

        lines.append("")
        lines.append("You can also ask natural language questions about the execution.")
        lines.append("Example: \"What has T2 built so far?\" or \"Why is T1 taking so long?\"")

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
    print(f"{ChatColors.BOLD}{'=' * 50}{ChatColors.RESET}")
    print(f"{ChatColors.MANAGER}  ARCHON - Manager Chat Mode{ChatColors.RESET}")
    print(f"{ChatColors.BOLD}{'=' * 50}{ChatColors.RESET}")
    print()
    print(f"{ChatColors.DIM}Type 'help' for available commands.{ChatColors.RESET}")
    print(f"{ChatColors.DIM}Type 'quit' to exit chat (orchestrator continues).{ChatColors.RESET}")
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
