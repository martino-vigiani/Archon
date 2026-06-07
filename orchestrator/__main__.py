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
import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

from . import sessions
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
        raise argparse.ArgumentTypeError("Timeout must be > 0 seconds, or use 'inf' for no timeout")

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

    parser.add_argument(
        "task", type=str, nargs="?", default=None, help="The high-level task to execute"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output")
    parser.add_argument("-q", "--quiet", action="store_true", help="Minimal output")
    parser.add_argument("--dry-run", action="store_true", help="Plan the task but don't execute it")
    parser.add_argument("--config", type=str, help="Path to custom config file (JSON)")
    parser.add_argument(
        "--timeout",
        type=parse_timeout_arg,
        default=None,
        metavar="SECONDS|inf",
        help="Maximum execution time in seconds; use 'inf' for no limit (default: inf)",
    )
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="Continuous mode: ask for new task after completion",
    )
    parser.add_argument("--dashboard", action="store_true", help="Also start the web dashboard")
    parser.add_argument(
        "--max-retries",
        type=int,
        default=2,
        metavar="N",
        help="Maximum retries for failed tasks (default: 2)",
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=4,
        metavar="N",
        help="Number of parallel terminals (default: 4, max: 10)",
    )
    parser.add_argument(
        "--project", type=str, metavar="PATH", help="Path to an existing project directory"
    )
    parser.add_argument(
        "--infer-project",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Infer existing project path from task text (default: enabled)",
    )
    parser.add_argument("--resume", action="store_true", help="Resume the last interrupted task")
    parser.add_argument("--chat", action="store_true", help="Enable interactive Manager Chat mode")
    parser.add_argument(
        "--no-testing",
        action="store_true",
        help="Disable T5 QA/Testing terminal (saves API limits)",
    )
    parser.add_argument(
        "--quality-threshold",
        type=float,
        default=0.8,
        metavar="LEVEL",
        help="Minimum quality level (0.0-1.0, default: 0.8)",
    )
    parser.add_argument(
        "--verbose-flow", action="store_true", help="Show detailed flow state changes"
    )
    parser.add_argument(
        "--llm-provider",
        choices=["claude", "codex"],
        default="claude",
        help="Model runtime provider for planning/execution (default: claude)",
    )
    parser.add_argument(
        "--llm-command", type=str, help="Override LLM CLI command (defaults: claude/codex)"
    )
    parser.add_argument("--llm-model", type=str, help="Model id to pass to the selected provider")
    parser.add_argument(
        "--full-prompts",
        action="store_true",
        help="Use full prompt templates (disables compact token-saving prompts)",
    )
    parser.add_argument(
        "--dynamic-agents",
        action="store_true",
        help="Derive a task-shaped worker roster (w1, w2, ...) instead of fixed T1-T5",
    )
    parser.add_argument(
        "--model-tiering",
        action="store_true",
        help="Pick a per-task model tier (cheap/standard/deep); may request a model your plan lacks",
    )
    parser.add_argument(
        "--no-effort-dial",
        action="store_true",
        help="Disable per-task reasoning effort selection (effort dial is on by default)",
    )
    parser.add_argument(
        "--max-system-prompt-chars",
        type=int,
        default=4200,
        metavar="N",
        help="Max chars for each system prompt after loading (default: 4200)",
    )
    parser.add_argument(
        "--session-id",
        type=str,
        default=None,
        metavar="ID",
        help="Session id for this run (default: from ARCHON_SESSION_ID env or minted from task)",
    )
    parser.add_argument(
        "--agent-count",
        type=int,
        default=None,
        metavar="N",
        help="Number of worker agents (maps to max_terminals; overrides --parallel)",
    )

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
    print(
        f"    {c('Prompt Mode:', Colors.DIM)} {c('compact' if not args.full_prompts else 'full', Colors.BRIGHT_CYAN)}"
    )
    print(
        f"    {c('Continuous:', Colors.DIM)} {c('Yes' if args.continuous else 'No', Colors.BRIGHT_GREEN if args.continuous else Colors.DIM)}"
    )
    print(
        f"    {c('Dashboard:', Colors.DIM)} {c('Yes' if args.dashboard else 'No', Colors.BRIGHT_GREEN if args.dashboard else Colors.DIM)}"
    )
    print(
        f"    {c('Chat Mode:', Colors.DIM)} {c('Yes' if args.chat else 'No', Colors.BRIGHT_GREEN if args.chat else Colors.DIM)}"
    )
    print(
        f"    {c('Verbose Flow:', Colors.DIM)} {c('Yes' if args.verbose_flow else 'No', Colors.BRIGHT_GREEN if args.verbose_flow else Colors.DIM)}"
    )

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


def resolve_session_id(args: argparse.Namespace, goal: str | None) -> str:
    """Resolve the session id for this run.

    Precedence: the ``--session-id`` flag, then the ``ARCHON_SESSION_ID``
    environment variable (set by the dashboard when it spawns an orchestrator
    process), then a freshly minted id derived from the goal text.

    Args:
        args: Parsed CLI namespace (read for ``session_id``).
        goal: The run's goal/task text used to derive a slug when minting.

    Returns:
        A non-empty session id of the form ``YYYYMMDD-HHMMSS-<slug>`` (or the
        explicitly supplied id).
    """
    explicit = getattr(args, "session_id", None)
    if explicit:
        return explicit
    env_session = os.environ.get("ARCHON_SESSION_ID")
    if env_session:
        return env_session
    return sessions.make_session_id(goal or "")


def _resume_config_from_registry(
    base_dir: Path, explicit_session_id: str | None
) -> tuple[str | None, Config]:
    """Pick the session to resume and build a config scoped to its namespace.

    Real runs persist ``last_project.json`` into the per-session namespaced
    directory (``<base>/.orchestra/runs/<session_id>/``), so a plain ``Config()``
    looking at the legacy ``.orchestra`` tree never finds prior state. This helper
    resolves which session to resume — an explicit ``--session-id`` /
    ``ARCHON_SESSION_ID`` if supplied, otherwise the newest entry in the registry
    — and returns a ``Config`` bound to that session so the caller can read its
    state and reuse the same id (no fresh, empty namespace is minted on resume).

    Args:
        base_dir: Repo/base root containing ``.orchestra`` (and the registry).
        explicit_session_id: A session id forced via flag/env, or ``None``.

    Returns:
        A ``(session_id, config)`` tuple. ``session_id`` is the namespaced id to
        reuse, or ``None`` when resuming a pre-registry legacy run (then ``config``
        is bound to the legacy ``.orchestra`` tree and a fresh id is minted at run
        start). When nothing can be resumed, ``config`` is a default
        :class:`Config` whose state load returns ``None``.
    """
    if explicit_session_id:
        return explicit_session_id, Config.for_session(explicit_session_id, base_dir=base_dir)

    registered = sessions.list_sessions(base_dir)
    if registered:
        last_session_id = registered[0].get("session_id")
        if last_session_id:
            return last_session_id, Config.for_session(last_session_id, base_dir=base_dir)

    # Back-compat: a pre-registry run may have left state on the legacy
    # (non-namespaced) ``.orchestra`` tree. Fall back to it so old sessions still
    # resume; its session id is unknown, so a fresh id is minted at run start.
    legacy_config = Config(base_dir=base_dir)
    if load_project_state(legacy_config):
        return None, legacy_config

    return None, Config(base_dir=base_dir)


def apply_args_to_config(config: Config, args: argparse.Namespace) -> Config:
    """Apply CLI-derived settings onto a Config in place and return it.

    Maps the runtime flags (parallelism, provider, prompt mode, execution
    modes) onto ``config``. ``--agent-count`` takes precedence over
    ``--parallel`` for ``max_terminals`` when supplied.

    Args:
        config: The config to mutate.
        args: Parsed CLI namespace.

    Returns:
        The same ``config`` object, mutated for convenience chaining.
    """
    agent_count = getattr(args, "agent_count", None)
    config.max_terminals = agent_count if agent_count is not None else args.parallel
    config.disable_testing = args.no_testing
    config.llm_provider = args.llm_provider
    config.llm_command = args.llm_command or ("codex" if args.llm_provider == "codex" else "claude")
    config.llm_model = args.llm_model
    config.compact_prompts = not args.full_prompts
    config.max_system_prompt_chars = args.max_system_prompt_chars
    config.dynamic_agents = args.dynamic_agents
    config.model_tiering = args.model_tiering
    config.effort_dial = not args.no_effort_dial
    return config


# ============================================================================
# Main
# ============================================================================
def main() -> int:
    args = parse_args()
    print_organic_banner()

    # When a session id is supplied explicitly (flag) or by the dashboard that
    # spawned us (ARCHON_SESSION_ID env), namespace the whole run — including the
    # dashboard log path — to that session's directory. Otherwise stay on the
    # legacy ``.orchestra`` tree and mint an id from the task later.
    explicit_session_id = getattr(args, "session_id", None) or os.environ.get("ARCHON_SESSION_ID")
    config = Config.for_session(explicit_session_id) if explicit_session_id else Config()
    project_path: Path | None = None
    # Set to the resumed session id so the main loop reuses it instead of
    # minting a fresh (empty) namespace below.
    resumed_session_id: str | None = None

    # Handle --resume
    if args.resume:
        # Real runs persist ``last_project.json`` into the *namespaced* session
        # dir (``Config.for_session``), not the legacy ``.orchestra``. Resolve the
        # most-recent session from the registry FIRST, rebind the config to that
        # session, and only then read its state — so resume targets the same
        # namespace the prior run wrote to.
        resumed_session_id, config = _resume_config_from_registry(
            config.base_dir, explicit_session_id
        )

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
        if resumed_session_id:
            print(f"    Session: {c(resumed_session_id, Colors.BRIGHT_WHITE)}")
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

    # Validate --agent-count (clamped to the same 1..10 range as --parallel).
    if args.agent_count is not None:
        if args.agent_count < 1:
            args.agent_count = 1
        elif args.agent_count > 10:
            print(c("  [WARNING] Max agent count is 10, using 10", Colors.BRIGHT_YELLOW))
            args.agent_count = 10

    apply_args_to_config(config, args)

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
        print(
            c(
                '    python -m orchestrator "Create an iOS app for habit tracking"',
                Colors.BRIGHT_WHITE,
            )
        )
        print(
            c(
                "    python -m orchestrator --resume           # resume last session",
                Colors.BRIGHT_WHITE,
            )
        )
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

    # Dry run (does not execute terminals → keep the default, non-namespaced config).
    if args.dry_run:
        return asyncio.run(run_dry_run(task, config, verbose, project_path))

    # Real orchestration: resolve a session id and rebuild the config scoped to
    # the per-session namespaced directory (so ARCHON_ORCHESTRA_DIR / per-session
    # isolation applies). Carry over all CLI-derived settings.
    #
    # On --resume, REUSE the session id + config resolved from the registry above
    # so we continue in the prior run's namespace instead of minting a fresh
    # (empty) one. ``config`` is already bound to that session here.
    if resumed_session_id:
        session_id = resumed_session_id
        config = apply_args_to_config(config, args)
    else:
        session_id = resolve_session_id(args, task)
        config = apply_args_to_config(
            Config.for_session(session_id, base_dir=config.base_dir), args
        )
    # Best-effort: register this session so the dashboard can discover it. Never
    # let registry I/O crash the run.
    with contextlib.suppress(Exception):
        sessions.register_session(
            config.base_dir,
            {
                "session_id": session_id,
                "goal": task,
                "project_path": str(project_path) if project_path else None,
                "pid": os.getpid(),
                "status": "starting",
                "orchestra_dir": str(config.orchestra_dir),
            },
        )

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
