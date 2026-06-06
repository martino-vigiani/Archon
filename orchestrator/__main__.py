"""
Entry point for the Archon Orchestrator.

Usage:
    python -m orchestrator "Create an iOS app for habit tracking"
    python -m orchestrator --dashboard "Build a full-stack app"
    python -m orchestrator --chat --dashboard "Create a meditation app"
    python -m orchestrator --dry-run "Build a REST API"
    python -m orchestrator --project ./Apps/MyApp "Add dark mode"
    python -m orchestrator --timeout inf "Long-running migration"
    python -m orchestrator --resume
"""

import argparse
import asyncio
import contextlib
import json
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

from .config import Config
from .cli_display import (
    Colors,
    c,
    print_organic_banner,
    print_terminals_ready,
)
from .session import (
    load_project_state,
    validate_project_directory,
    get_project_summary,
    infer_project_path_from_task,
    run_dry_run,
    run_orchestrator,
    run_with_chat,
    retry_failed_tasks,
)
from .manager_chat import ManagerChat, chat_repl
from .orchestrator import Orchestrator
from .planner import Planner


# ============================================================================
# CLI Argument Parser
# ============================================================================
def parse_timeout_arg(value: str) -> int | None:
    """Parse timeout CLI arg. Supports infinite via inf/infinite/none/0."""
    normalized = value.strip().lower()
    if normalized in {"inf", "infinite", "none", "off", "0"}:
        return None

    try:
        timeout_seconds = int(normalized)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "Timeout must be an integer number of seconds or 'inf'"
        ) from exc

    if timeout_seconds <= 0:
        raise argparse.ArgumentTypeError(
            "Timeout must be > 0 seconds, or use 'inf' for no timeout"
        )

    return timeout_seconds


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="orchestrator",
        description="Archon - Organic Multi-Agent Orchestrator. Work flows. Quality emerges.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  %(prog)s "Create an iOS habit tracking app"
  %(prog)s --dashboard "Build a full-stack app"
  %(prog)s --chat --dashboard "Create a meditation app"
  %(prog)s --dry-run "Build a REST API"
  %(prog)s --project ./Apps/MyApp "Add dark mode"
  %(prog)s --timeout inf "Long-running migration"
  %(prog)s --no-testing "Quick prototype"
  %(prog)s --resume

terminals:
  T1 Craftsman   UI/UX         "Every pixel matters"
  T2 Architect   Backend       "Foundation that endures"
  T3 Narrator    Documentation "Clarity illuminates"
  T4 Strategist  Product       "Vision guides direction"
  T5 Skeptic     QA/Testing    "Trust but verify"
        """,
    )

    parser.add_argument("task", type=str, nargs="?", default=None,
                        help="The high-level task to execute")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Enable verbose output")
    parser.add_argument("-q", "--quiet", action="store_true",
                        help="Minimal output")
    parser.add_argument("--dry-run", action="store_true",
                        help="Plan the task but don't execute it")
    parser.add_argument("--config", type=str,
                        help="Path to custom config file (JSON)")
    parser.add_argument("--timeout", type=parse_timeout_arg, default=None, metavar="SECONDS|inf",
                        help="Maximum execution time in seconds; use 'inf' for no limit (default: inf)")
    parser.add_argument("--continuous", action="store_true",
                        help="Continuous mode: ask for new task after completion")
    parser.add_argument("--dashboard", action="store_true",
                        help="Also start the web dashboard")
    parser.add_argument("--max-retries", type=int, default=2, metavar="N",
                        help="Maximum retries for failed tasks (default: 2)")
    parser.add_argument("--parallel", type=int, default=4, metavar="N",
                        help="Number of parallel terminals (default: 4, max: 10)")
    parser.add_argument("--project", type=str, metavar="PATH",
                        help="Path to an existing project directory")
    parser.add_argument("--infer-project", action=argparse.BooleanOptionalAction, default=True,
                        help="Infer existing project path from task text (default: enabled)")
    parser.add_argument("--resume", action="store_true",
                        help="Resume the last interrupted task")
    parser.add_argument("--chat", action="store_true",
                        help="Enable interactive Manager Chat mode")
    parser.add_argument("--no-testing", action="store_true",
                        help="Disable T5 QA/Testing terminal (saves API limits)")
    parser.add_argument("--quality-threshold", type=float, default=0.8, metavar="LEVEL",
                        help="Minimum quality level (0.0-1.0, default: 0.8)")
    parser.add_argument("--verbose-flow", action="store_true",
                        help="Show detailed flow state changes")
    parser.add_argument("--llm-provider", choices=["claude", "codex"], default="claude",
                        help="Model runtime provider for planning/execution (default: claude)")
    parser.add_argument("--llm-command", type=str,
                        help="Override LLM CLI command (defaults: claude/codex)")
    parser.add_argument("--llm-model", type=str,
                        help="Model id to pass to the selected provider")
    parser.add_argument("--full-prompts", action="store_true",
                        help="Use full prompt templates (disables compact token-saving prompts)")
    parser.add_argument("--dynamic-agents", action="store_true",
                        help="Derive a task-shaped worker roster (w1, w2, ...) instead of fixed T1-T5")
    parser.add_argument("--model-tiering", action="store_true",
                        help="Pick a per-task model tier (cheap/standard/deep); may request a model your plan lacks")
    parser.add_argument("--no-effort-dial", action="store_true",
                        help="Disable per-task reasoning effort selection (effort dial is on by default)")
    parser.add_argument("--max-system-prompt-chars", type=int, default=4200, metavar="N",
                        help="Max chars for each system prompt after loading (default: 4200)")

    return parser.parse_args()


# ============================================================================
# Display Helpers (CLI-specific)
# ============================================================================
def print_config_summary(args: argparse.Namespace, project_path: Path | None = None):
    """Print current configuration."""
    print(c("    Configuration:", Colors.BOLD, Colors.WHITE))

    terminal_list = ["t1", "t2", "t3", "t4"]
    if not args.no_testing:
        terminal_list.append("t5")

    print(f"    {c('Terminals:', Colors.DIM)} {len(terminal_list)}")
    print()
    print_terminals_ready(terminal_list)

    print(f"    {c('Flow Model:', Colors.DIM)} {c('Organic', Colors.BRIGHT_GREEN)}")
    print(
        f"    {c('Quality Threshold:', Colors.DIM)} {c(f'{args.quality_threshold:.1f}', Colors.BRIGHT_YELLOW)}"
    )
    print(f"    {c('Max Retries:', Colors.DIM)} {c(str(args.max_retries), Colors.BRIGHT_YELLOW)}")
    timeout_display = "infinite" if args.timeout is None else f"{args.timeout}s"
    print(f"    {c('Timeout:', Colors.DIM)} {c(timeout_display, Colors.BRIGHT_YELLOW)}")
    print(f"    {c('LLM Provider:', Colors.DIM)} {c(args.llm_provider, Colors.BRIGHT_CYAN)}")
    if args.llm_model:
        print(f"    {c('LLM Model:', Colors.DIM)} {c(args.llm_model, Colors.BRIGHT_CYAN)}")
    print(f"    {c('Prompt Mode:', Colors.DIM)} {c('compact' if not args.full_prompts else 'full', Colors.BRIGHT_CYAN)}")
    print(f"    {c('Continuous:', Colors.DIM)} {c('Yes' if args.continuous else 'No', Colors.BRIGHT_GREEN if args.continuous else Colors.DIM)}")
    print(f"    {c('Dashboard:', Colors.DIM)} {c('Yes' if args.dashboard else 'No', Colors.BRIGHT_GREEN if args.dashboard else Colors.DIM)}")
    print(f"    {c('Chat Mode:', Colors.DIM)} {c('Yes' if args.chat else 'No', Colors.BRIGHT_GREEN if args.chat else Colors.DIM)}")
    print(f"    {c('Verbose Flow:', Colors.DIM)} {c('Yes' if args.verbose_flow else 'No', Colors.BRIGHT_GREEN if args.verbose_flow else Colors.DIM)}")

    if project_path:
        print(f"    {c('Project:', Colors.DIM)} {c(str(project_path), Colors.BRIGHT_CYAN)}")
    print()


def show_interactive_menu(has_failed_tasks: bool) -> str:
    """Show post-completion interactive menu."""
    print(c("  What would you like to do?", Colors.BOLD, Colors.WHITE))
    print()

    if has_failed_tasks:
        print(f"    [{c('r', Colors.BRIGHT_YELLOW)}] Retry failed tasks")
    print(f"    [{c('n', Colors.BRIGHT_GREEN)}] New task")
    print(f"    [{c('d', Colors.BRIGHT_CYAN)}] Open dashboard")
    print(f"    [{c('q', Colors.BRIGHT_RED)}] Quit")
    print()

    valid_choices = ["n", "d", "q"]
    if has_failed_tasks:
        valid_choices.append("r")

    while True:
        try:
            choice = input(c("  > ", Colors.BRIGHT_WHITE)).strip().lower()
            if choice in valid_choices:
                return choice
            print(
                c(
                    f"    Invalid choice. Please enter one of: {', '.join(valid_choices)}",
                    Colors.BRIGHT_RED,
                )
            )
        except (KeyboardInterrupt, EOFError):
            return "q"


def get_new_task() -> str | None:
    """Prompt user for a new task."""
    print()
    print(c("  Enter your task (or 'cancel' to go back):", Colors.BOLD, Colors.WHITE))
    try:
        task = input(c("  > ", Colors.BRIGHT_WHITE)).strip()
        if task.lower() == "cancel" or not task:
            return None
        return task
    except (KeyboardInterrupt, EOFError):
        return None


def ask_create_directory(project_path: Path) -> bool:
    """Ask the user if they want to create a non-existent directory."""
    print()
    print(c(f"  Directory does not exist: {project_path}", Colors.BRIGHT_YELLOW))
    print()
    try:
        response = input(c("  Create it? [y/N] ", Colors.BRIGHT_WHITE)).strip().lower()
        return response in ("y", "yes")
    except (KeyboardInterrupt, EOFError):
        return False


# ============================================================================
# Dashboard
# ============================================================================
def start_dashboard(config: Config):
    """Start the web dashboard in the background."""
    dashboard_script = config.base_dir / "orchestrator" / "dashboard.py"

    if not dashboard_script.exists():
        print(c("  [WARNING] Dashboard not found, skipping...", Colors.BRIGHT_YELLOW))
        return None

    print(c("  Starting dashboard...", Colors.DIM))

    try:
        log_file = config.orchestra_dir / "dashboard.log"
        config.orchestra_dir.mkdir(parents=True, exist_ok=True)
        log_fh = open(log_file, "w")

        # Use venv Python if available, otherwise fall back to sys.executable
        venv_python = config.base_dir / ".venv" / "bin" / "python"
        python_exe = str(venv_python) if venv_python.exists() else sys.executable

        process = subprocess.Popen(
            [python_exe, "-m", "orchestrator.dashboard"],
            stdout=log_fh,
            stderr=log_fh,
            cwd=str(config.base_dir),
            start_new_session=True,
        )
        time.sleep(2)

        # Check if process actually started
        if process.poll() is not None:
            log_fh.close()
            error_output = log_file.read_text().strip()
            dashboard_url = "http://localhost:8420"
            error_lower = error_output.lower()
            if "address already in use" in error_lower or "errno 48" in error_lower:
                print(
                    c(
                        "  [WARNING] Dashboard already running on port 8420, reusing existing instance.",
                        Colors.BRIGHT_YELLOW,
                    )
                )
                with contextlib.suppress(Exception):
                    webbrowser.open(dashboard_url)
                print(c(f"  Dashboard available at {dashboard_url}", Colors.BRIGHT_GREEN))
                return None

            print(c(f"  [ERROR] Dashboard crashed on startup:", Colors.BRIGHT_RED))
            if error_output:
                for line in error_output.split("\n")[-5:]:
                    print(c(f"    {line}", Colors.DIM))
            return None

        dashboard_url = "http://localhost:8420"
        webbrowser.open(dashboard_url)
        print(c(f"  Dashboard started at {dashboard_url}", Colors.BRIGHT_GREEN))
        return process
    except Exception as e:
        print(c(f"  [WARNING] Could not start dashboard: {e}", Colors.BRIGHT_YELLOW))
        return None


def open_dashboard():
    """Open the dashboard in browser."""
    dashboard_url = "http://localhost:8420"
    try:
        webbrowser.open(dashboard_url)
        print(c(f"  Opening {dashboard_url}", Colors.BRIGHT_CYAN))
    except Exception as e:
        print(c(f"  Could not open browser: {e}", Colors.BRIGHT_RED))


# ============================================================================
# Main
# ============================================================================
def main() -> int:
    args = parse_args()
    print_organic_banner()

    config = Config()
    project_path: Path | None = None

    # Handle --resume
    if args.resume:
        state = load_project_state(config)
        if not state:
            print(c("  Error: No previous session to resume.", Colors.BRIGHT_RED))
            print()
            print(c("  To start a new session:", Colors.DIM))
            print(c('    python -m orchestrator "Your task here"', Colors.BRIGHT_WHITE))
            return 1

        project_path = Path(state["path"])
        if not args.task:
            args.task = state.get("task")

        print(c("  [RESUME] Resuming previous session:", Colors.BRIGHT_CYAN, Colors.BOLD))
        print(f"    Project: {c(str(project_path), Colors.BRIGHT_WHITE)}")
        print(f"    Task: {c(state.get('task', 'N/A'), Colors.DIM)}")
        print(f"    Last status: {c(state.get('status', 'unknown'), Colors.BRIGHT_YELLOW)}")
        print()

    # Handle --project
    elif args.project:
        project_path, error = validate_project_directory(args.project)
        if error:
            print(c(f"  [ERROR] {error}", Colors.BRIGHT_RED))
            return 1

        if project_path and not project_path.exists():
            if ask_create_directory(project_path):
                try:
                    project_path.mkdir(parents=True, exist_ok=True)
                    print(c(f"  Created directory: {project_path}", Colors.BRIGHT_GREEN))
                except OSError as e:
                    print(c(f"  [ERROR] Could not create directory: {e}", Colors.BRIGHT_RED))
                    return 1
            else:
                print(c("  Aborted.", Colors.DIM))
                return 1

        if project_path and project_path.exists():
            print(c("  Project Directory:", Colors.BOLD, Colors.WHITE))
            print(c(f"  {project_path}", Colors.BRIGHT_CYAN))
            print()
            print(get_project_summary(project_path))
            print()

    # Validate parallel count
    if args.parallel < 1:
        args.parallel = 1
    elif args.parallel > 10:
        print(c("  [WARNING] Max parallel terminals is 10, using 10", Colors.BRIGHT_YELLOW))
        args.parallel = 10

    config.max_terminals = args.parallel
    config.disable_testing = args.no_testing
    config.llm_provider = args.llm_provider
    config.llm_command = args.llm_command or ("codex" if args.llm_provider == "codex" else "claude")
    config.llm_model = args.llm_model
    config.compact_prompts = not args.full_prompts
    config.max_system_prompt_chars = args.max_system_prompt_chars
    config.dynamic_agents = args.dynamic_agents
    config.model_tiering = args.model_tiering
    config.effort_dial = not args.no_effort_dial

    if args.config:
        try:
            json.loads(Path(args.config).read_text())
            print(c(f"  Loaded config from {args.config}", Colors.DIM))
        except Exception as e:
            print(c(f"  [WARNING] Could not load config: {e}", Colors.BRIGHT_YELLOW))

    verbose = not args.quiet

    # Dashboard
    dashboard_process = None
    if args.dashboard:
        dashboard_process = start_dashboard(config)

    # Get task
    if args.continuous and not args.task:
        print(c("  Continuous mode - waiting for task...", Colors.BRIGHT_CYAN))
        task = get_new_task()
        if not task:
            print(c("  No task provided. Exiting.", Colors.DIM))
            return 0
    else:
        task = args.task

    if not task:
        print(c("  Error: No task provided.", Colors.BRIGHT_RED))
        print()
        print(c("  Usage:", Colors.DIM))
        print(c('    python -m orchestrator "Create an iOS app for habit tracking"', Colors.BRIGHT_WHITE))
        print(c('    python -m orchestrator --resume           # resume last session', Colors.BRIGHT_WHITE))
        return 1

    if not project_path and args.infer_project:
        inferred_project = infer_project_path_from_task(task, Path.cwd())
        if inferred_project:
            project_path = inferred_project
            print(c("  [PROJECT] Inferred existing project from task text:", Colors.BRIGHT_CYAN))
            print(c(f"  {project_path}", Colors.BRIGHT_CYAN))
            print()
            print(get_project_summary(project_path))
            print()

    print_config_summary(args, project_path)

    print(f"  {c('Task:', Colors.BOLD)} {task}")
    print()

    # Dry run
    if args.dry_run:
        return asyncio.run(run_dry_run(task, config, verbose, project_path))

    # Chat mode
    if args.chat:
        exit_code, _ = asyncio.run(
            run_with_chat(task, config, verbose, args.timeout, args.max_retries, project_path)
        )
        return exit_code

    # Main execution loop
    last_result: dict = {}
    retry_count = 0
    exit_code = 0

    while True:
        exit_code, last_result = asyncio.run(
            run_orchestrator(task, config, verbose, args.timeout, args.max_retries, project_path)
        )

        tasks_info = last_result.get("tasks", {})
        has_failed = tasks_info.get("failed", 0) > 0

        if not args.continuous:
            choice = show_interactive_menu(has_failed)

            if choice == "q":
                print(c("  Goodbye!", Colors.BRIGHT_CYAN))
                break
            elif choice == "r" and has_failed:
                if retry_count < args.max_retries:
                    retry_count += 1
                    print(
                        c(f"  Retry attempt {retry_count}/{args.max_retries}", Colors.BRIGHT_YELLOW)
                    )
                    exit_code, last_result = asyncio.run(
                        retry_failed_tasks(config, verbose, args.timeout, last_result, project_path)
                    )
                    continue
                else:
                    print(c(f"  Maximum retries ({args.max_retries}) reached.", Colors.BRIGHT_RED))
            elif choice == "d":
                open_dashboard()
                continue
            elif choice == "n":
                new_task = get_new_task()
                if new_task:
                    task = new_task
                    retry_count = 0
                    continue
                else:
                    continue
            break

        # Continuous mode
        print()
        print(c("  Task completed. Ready for next task.", Colors.BRIGHT_GREEN))
        new_task = get_new_task()

        if new_task:
            task = new_task
            retry_count = 0
        else:
            print(c("  No task provided. Exiting continuous mode.", Colors.DIM))
            break

    if dashboard_process:
        with contextlib.suppress(Exception):
            dashboard_process.terminate()

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
