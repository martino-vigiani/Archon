"""
Entry point for the Archon Orchestrator.

Usage:
    python -m orchestrator "Create an iOS app for habit tracking"
    python -m orchestrator --dashboard "Build a full-stack app"
    python -m orchestrator --chat --dashboard "Create a meditation app"
    python -m orchestrator --dry-run "Build a REST API"
    python -m orchestrator --project ./Apps/MyApp "Add dark mode"
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

<<<<<<< ours
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
    run_dry_run,
    run_orchestrator,
    run_with_chat,
    retry_failed_tasks,
=======
from .cli_display import (
    Colors,
    c,
    format_duration,
    get_terminal_color,
    get_terminal_name,
    print_organic_banner,
    print_separator,
    print_terminals_ready,
>>>>>>> theirs
)
from .config import Config
from .manager_chat import ManagerChat, chat_repl
from .orchestrator import Orchestrator
from .planner import Planner


# ============================================================================
# CLI Argument Parser
# ============================================================================
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

<<<<<<< ours
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
    parser.add_argument("--timeout", type=int, default=3600,
                        help="Maximum execution time in seconds (default: 3600)")
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
    parser.add_argument("--max-system-prompt-chars", type=int, default=4200, metavar="N",
                        help="Max chars for each system prompt after loading (default: 4200)")
=======
    parser.add_argument(
        "task",
        type=str,
        nargs="?",
        default=None,
        help="The high-level task to execute (optional in continuous mode or with --resume)",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose output with detailed flow information",
    )

    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Minimal output (errors and final summary only)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan the task but don't execute it",
    )

    parser.add_argument(
        "--config",
        type=str,
        help="Path to custom config file (JSON)",
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=3600,
        help="Maximum execution time in seconds (default: 3600)",
    )

    # New flags
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="Continuous mode: ask for new task after completion",
    )

    parser.add_argument(
        "--dashboard",
        action="store_true",
        help="Also start the web dashboard",
    )

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

    # Project-related flags
    parser.add_argument(
        "--project",
        type=str,
        metavar="PATH",
        help="Path to an existing project directory to work on",
    )

    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume the last interrupted task (reads from .orchestra/last_project.json)",
    )

    parser.add_argument(
        "--chat",
        action="store_true",
        help="Enable interactive Manager Chat mode (REPL during execution)",
    )

    parser.add_argument(
        "--no-testing",
        action="store_true",
        help="Disable T5 QA/Testing terminal (saves API limits)",
    )

    # Organic flow model flags
    parser.add_argument(
        "--quality-threshold",
        type=float,
        default=0.8,
        metavar="LEVEL",
        help="Minimum quality level before considering done (0.0-1.0, default: 0.8)",
    )

    parser.add_argument(
        "--verbose-flow",
        action="store_true",
        help="Show detailed flow state changes during execution",
    )
>>>>>>> theirs

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
    print(f"    {c('Timeout:', Colors.DIM)} {c(f'{args.timeout}s', Colors.BRIGHT_YELLOW)}")
<<<<<<< ours
    print(f"    {c('LLM Provider:', Colors.DIM)} {c(args.llm_provider, Colors.BRIGHT_CYAN)}")
    if args.llm_model:
        print(f"    {c('LLM Model:', Colors.DIM)} {c(args.llm_model, Colors.BRIGHT_CYAN)}")
    print(f"    {c('Prompt Mode:', Colors.DIM)} {c('compact' if not args.full_prompts else 'full', Colors.BRIGHT_CYAN)}")
    print(f"    {c('Continuous:', Colors.DIM)} {c('Yes' if args.continuous else 'No', Colors.BRIGHT_GREEN if args.continuous else Colors.DIM)}")
    print(f"    {c('Dashboard:', Colors.DIM)} {c('Yes' if args.dashboard else 'No', Colors.BRIGHT_GREEN if args.dashboard else Colors.DIM)}")
    print(f"    {c('Chat Mode:', Colors.DIM)} {c('Yes' if args.chat else 'No', Colors.BRIGHT_GREEN if args.chat else Colors.DIM)}")
    print(f"    {c('Verbose Flow:', Colors.DIM)} {c('Yes' if args.verbose_flow else 'No', Colors.BRIGHT_GREEN if args.verbose_flow else Colors.DIM)}")
=======
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
>>>>>>> theirs

    if project_path:
        print(f"    {c('Project:', Colors.DIM)} {c(str(project_path), Colors.BRIGHT_CYAN)}")
    print()


<<<<<<< ours
=======
# ============================================================================
# Project Management
# ============================================================================
def get_last_project_file(config: Config) -> Path:
    """Get the path to the last project state file."""
    return config.orchestra_dir / "last_project.json"


def save_project_state(
    config: Config,
    project_path: Path,
    task: str,
    status: str = "in_progress",
) -> None:
    """Save the current project state to last_project.json."""
    config.ensure_dirs()
    state_file = get_last_project_file(config)

    state = {
        "path": str(project_path.resolve()),
        "task": task,
        "timestamp": datetime.now().isoformat(),
        "status": status,
    }

    state_file.write_text(json.dumps(state, indent=2))


def load_project_state(config: Config) -> dict | None:
    """Load the last project state from last_project.json."""
    state_file = get_last_project_file(config)

    if not state_file.exists():
        return None

    try:
        return json.loads(state_file.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def update_project_status(config: Config, status: str) -> None:
    """Update the status of the current project state."""
    state = load_project_state(config)
    if state:
        state["status"] = status
        state["updated_at"] = datetime.now().isoformat()
        state_file = get_last_project_file(config)
        state_file.write_text(json.dumps(state, indent=2))


def validate_project_directory(project_arg: str) -> tuple[Path | None, str | None]:
    """
    Validate and resolve the project directory.

    Returns:
        Tuple of (resolved_path, error_message).
        If error_message is not None, resolved_path will be None.
    """
    # Expand ~ and resolve path
    project_path = Path(project_arg).expanduser()

    # If not absolute, treat as relative to current working directory
    if not project_path.is_absolute():
        project_path = Path.cwd() / project_path

    project_path = project_path.resolve()

    return project_path, None


def get_project_summary(project_path: Path) -> str:
    """
    Get a summary of the project's contents.

    Returns a string describing the main files and directories.
    """
    if not project_path.exists():
        return "Directory does not exist yet."

    if not project_path.is_dir():
        return f"Path exists but is not a directory: {project_path}"

    # Count files and find key files
    key_files = []
    key_patterns = [
        "Package.swift",
        "*.xcodeproj",
        "*.xcworkspace",  # Swift/iOS
        "package.json",
        "tsconfig.json",  # Node.js/TypeScript
        "pyproject.toml",
        "setup.py",
        "requirements.txt",  # Python
        "Cargo.toml",  # Rust
        "go.mod",  # Go
        "README.md",
        "README.txt",
        "README",
        ".gitignore",
        "Makefile",
        "Dockerfile",
    ]

    total_files = 0
    directories = []

    for item in project_path.iterdir():
        if item.name.startswith("."):
            continue  # Skip hidden files in listing

        if item.is_dir():
            directories.append(item.name)
        else:
            total_files += 1
            # Check if it's a key file
            for pattern in key_patterns:
                if pattern.startswith("*"):
                    if item.name.endswith(pattern[1:]):
                        key_files.append(item.name)
                        break
                elif item.name == pattern:
                    key_files.append(item.name)
                    break

    # Build summary
    lines = []

    if key_files:
        lines.append(f"  Key files: {', '.join(sorted(key_files)[:5])}")

    if directories:
        dir_list = sorted(directories)[:8]
        lines.append(f"  Directories: {', '.join(dir_list)}")
        if len(directories) > 8:
            lines.append(f"    ... and {len(directories) - 8} more")

    lines.append(f"  Total files (top level): {total_files}")

    # Detect project type
    project_type = detect_project_type(project_path)
    if project_type:
        lines.insert(0, f"  Project type: {project_type}")

    return "\n".join(lines) if lines else "  Empty directory"


def detect_project_type(project_path: Path) -> str | None:
    """Detect the type of project based on key files."""
    if not project_path.exists():
        return None

    checks = [
        (["Package.swift"], "Swift Package"),
        (["*.xcodeproj", "*.xcworkspace"], "Xcode Project"),
        (["package.json"], "Node.js"),
        (["pyproject.toml", "setup.py"], "Python"),
        (["Cargo.toml"], "Rust"),
        (["go.mod"], "Go"),
        (["Gemfile"], "Ruby"),
        (["pom.xml", "build.gradle"], "Java"),
    ]

    for patterns, project_type in checks:
        for pattern in patterns:
            if pattern.startswith("*"):
                # Glob pattern
                if list(project_path.glob(pattern)):
                    return project_type
            else:
                # Exact file
                if (project_path / pattern).exists():
                    return project_type

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


def get_project_context_for_planner(project_path: Path) -> str:
    """
    Generate context about an existing project for the planner.

    This scans the project and creates a summary the planner can use
    to make informed decisions about the existing codebase.
    """
    if not project_path.exists():
        return ""

    context_parts = []
    context_parts.append(f"## Existing Project: {project_path.name}")
    context_parts.append(f"Path: {project_path}")
    context_parts.append("")

    # Detect project type
    project_type = detect_project_type(project_path)
    if project_type:
        context_parts.append(f"Project Type: {project_type}")
        context_parts.append("")

    # List key directories
    dirs = []
    for item in sorted(project_path.iterdir()):
        if item.is_dir() and not item.name.startswith("."):
            dirs.append(item.name)

    if dirs:
        context_parts.append("Directories:")
        for d in dirs[:15]:
            context_parts.append(f"  - {d}/")
        if len(dirs) > 15:
            context_parts.append(f"  ... and {len(dirs) - 15} more")
        context_parts.append("")

    # Find and summarize key files
    key_files_content = []

    # Try to read README for context
    for readme_name in ["README.md", "README.txt", "README"]:
        readme_path = project_path / readme_name
        if readme_path.exists():
            try:
                content = readme_path.read_text()[:1000]  # First 1000 chars
                key_files_content.append(f"README excerpt:\n{content}")
            except OSError:
                pass
            break

    # Check for package.json (Node.js)
    package_json = project_path / "package.json"
    if package_json.exists():
        try:
            pkg = json.loads(package_json.read_text())
            key_files_content.append(
                f"package.json - name: {pkg.get('name', 'unknown')}, deps: {len(pkg.get('dependencies', {}))}"
            )
        except (OSError, json.JSONDecodeError):
            pass

    # Check for Package.swift (Swift)
    package_swift = project_path / "Package.swift"
    if package_swift.exists():
        key_files_content.append("Package.swift exists (Swift Package)")

    # Check for pyproject.toml (Python)
    pyproject = project_path / "pyproject.toml"
    if pyproject.exists():
        key_files_content.append("pyproject.toml exists (Python project)")

    if key_files_content:
        context_parts.append("Key Files:")
        for kf in key_files_content:
            context_parts.append(f"  {kf}")
        context_parts.append("")

    # List source files (limited)
    source_extensions = {".swift", ".py", ".ts", ".tsx", ".js", ".jsx", ".rs", ".go"}
    source_files = []

    for ext in source_extensions:
        files = list(project_path.rglob(f"*{ext}"))
        # Filter out common non-source directories
        files = [
            f
            for f in files
            if not any(
                part in f.parts
                for part in [
                    "node_modules",
                    ".build",
                    "build",
                    "dist",
                    "__pycache__",
                    ".git",
                    "venv",
                ]
            )
        ]
        source_files.extend(files)

    if source_files:
        # Show relative paths
        rel_files = [str(f.relative_to(project_path)) for f in source_files[:20]]
        context_parts.append(f"Source files ({len(source_files)} total):")
        for rf in rel_files:
            context_parts.append(f"  - {rf}")
        if len(source_files) > 20:
            context_parts.append(f"  ... and {len(source_files) - 20} more")

    return "\n".join(context_parts)


# ============================================================================
# Plan Display
# ============================================================================
def print_plan(plan) -> None:
    """Pretty print a task plan with colors."""
    print()
    print_separator("=", 60, Colors.BRIGHT_CYAN, indent=2)
    print(c("  TASK PLAN", Colors.BOLD, Colors.BRIGHT_WHITE))
    print_separator("=", 60, Colors.BRIGHT_CYAN, indent=2)
    print()
    print(f"  {c('Summary:', Colors.BOLD)} {plan.summary}")
    print()
    print(f"  {c(f'Tasks ({len(plan.tasks)}):', Colors.BOLD, Colors.BRIGHT_YELLOW)}")
    print_separator("-", 40, Colors.DIM, indent=2)

    for i, task in enumerate(plan.tasks, 1):
        deps_text = ", ".join(task.dependencies)
        deps = f" {c(f'(depends on: {deps_text})', Colors.DIM)}" if task.dependencies else ""
        term_color = get_terminal_color(task.terminal)

        print()
        print(
            f"  {c(str(i) + '.', Colors.BOLD)} [{c(task.terminal.upper(), term_color)}] {c(task.title, Colors.WHITE)}"
        )
        print(f"     {c('Priority:', Colors.DIM)} {task.priority}{deps}")
        desc_preview = (
            task.description[:80] + "..." if len(task.description) > 80 else task.description
        )
        print(f"     {c(desc_preview, Colors.DIM)}")

    print()
    print_separator("=", 60, Colors.BRIGHT_CYAN, indent=2)


# ============================================================================
# Summary Report
# ============================================================================
def print_detailed_summary(result: dict, events_file: Path, start_time: datetime):
    """Print a detailed execution summary with colors."""
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    print()
    print_separator("=", 60, Colors.BRIGHT_CYAN, indent=2)
    print(c("  EXECUTION SUMMARY", Colors.BOLD, Colors.BRIGHT_WHITE))
    print_separator("=", 60, Colors.BRIGHT_CYAN, indent=2)
    print()

    # Status
    status = result.get("status", "unknown")
    status_color = (
        Colors.BRIGHT_GREEN
        if status == "success"
        else Colors.BRIGHT_YELLOW if status == "partial" else Colors.BRIGHT_RED
    )
    print(f"  {c('Status:', Colors.BOLD)} {c(status.upper(), status_color, Colors.BOLD)}")
    print()

    # Time stats
    print(c("  Time", Colors.BOLD, Colors.BRIGHT_CYAN))
    print_separator("-", 25, Colors.DIM, indent=2)
    time_str = format_duration(duration)
    print(f"    Total Duration:    {c(time_str, Colors.BRIGHT_WHITE)}")
    print(f"    Started:           {c(start_time.strftime('%H:%M:%S'), Colors.DIM)}")
    print(f"    Finished:          {c(end_time.strftime('%H:%M:%S'), Colors.DIM)}")
    print()

    # Task stats
    tasks = result.get("tasks", {})
    print(c("  Tasks", Colors.BOLD, Colors.BRIGHT_CYAN))
    print_separator("-", 25, Colors.DIM, indent=2)
    print(f"    Total:             {c(str(tasks.get('total', 0)), Colors.BRIGHT_WHITE)}")
    print(f"    Completed:         {c(str(tasks.get('completed', 0)), Colors.BRIGHT_GREEN)}")
    print(
        f"    Failed:            {c(str(tasks.get('failed', 0)), Colors.BRIGHT_RED if tasks.get('failed', 0) > 0 else Colors.DIM)}"
    )
    print(
        f"    Pending:           {c(str(tasks.get('pending', 0)), Colors.BRIGHT_YELLOW if tasks.get('pending', 0) > 0 else Colors.DIM)}"
    )
    print()

    # Tasks per terminal
    completed_tasks = result.get("completed_tasks", [])
    failed_tasks = result.get("failed_tasks", [])
    all_tasks = completed_tasks + failed_tasks

    terminal_stats: dict[str, dict] = {}
    for task in all_tasks:
        term = task.get("terminal", "unknown")
        if term not in terminal_stats:
            terminal_stats[term] = {"completed": 0, "failed": 0, "tasks": []}
        if task in completed_tasks:
            terminal_stats[term]["completed"] += 1
        else:
            terminal_stats[term]["failed"] += 1
        terminal_stats[term]["tasks"].append(task.get("title", "Unknown"))

    if terminal_stats:
        print(c("  Tasks per Terminal", Colors.BOLD, Colors.BRIGHT_CYAN))
        print_separator("-", 25, Colors.DIM, indent=2)

        for term_id in ["t1", "t2", "t3", "t4", "t5"]:
            if term_id in terminal_stats:
                stats = terminal_stats[term_id]
                color = get_terminal_color(term_id)
                name = get_terminal_name(term_id)
                total = stats["completed"] + stats["failed"]
                print(
                    f"    {c(f'[{term_id.upper()}]', color)} {name}: {c(str(total), Colors.BRIGHT_WHITE)} tasks ({c(str(stats['completed']), Colors.BRIGHT_GREEN)} ok, {c(str(stats['failed']), Colors.BRIGHT_RED)} failed)"
                )
        print()

    # Subagents used (from events log)
    subagents_used = set()
    try:
        if events_file.exists():
            events = json.loads(events_file.read_text())
            for event in events:
                if event.get("type") == "subagent_invoked":
                    details = event.get("details", {})
                    subagent = details.get("subagent")
                    if subagent:
                        subagents_used.add(subagent)
    except (json.JSONDecodeError, FileNotFoundError):
        pass

    if subagents_used:
        print(c("  Subagents Used", Colors.BOLD, Colors.BRIGHT_CYAN))
        print(c("  " + "-" * 25, Colors.DIM))
        for subagent in sorted(subagents_used):
            print(f"    - {c(subagent, Colors.BRIGHT_MAGENTA)}")
        print()

    # Files modified (this would require tracking in the orchestrator)
    # For now, we just show a placeholder if we had this info
    files_created = result.get("files_created", [])
    files_modified = result.get("files_modified", [])

    if files_created or files_modified:
        print(c("  Files Changed", Colors.BOLD, Colors.BRIGHT_CYAN))
        print(c("  " + "-" * 25, Colors.DIM))
        if files_created:
            print(f"    Created:           {c(str(len(files_created)), Colors.BRIGHT_GREEN)}")
            for f in files_created[:5]:  # Show max 5
                print(f"      + {c(f, Colors.GREEN)}")
            if len(files_created) > 5:
                print(f"      ... and {len(files_created) - 5} more")
        if files_modified:
            print(f"    Modified:          {c(str(len(files_modified)), Colors.BRIGHT_YELLOW)}")
            for f in files_modified[:5]:  # Show max 5
                print(f"      ~ {c(f, Colors.YELLOW)}")
            if len(files_modified) > 5:
                print(f"      ... and {len(files_modified) - 5} more")
        print()

    # Failed tasks details
    if failed_tasks:
        print(c("  Failed Tasks", Colors.BOLD, Colors.BRIGHT_RED))
        print(c("  " + "-" * 25, Colors.DIM))
        for task in failed_tasks:
            print(f"    {c('X', Colors.BRIGHT_RED)} {task.get('title', 'Unknown')}")
            if task.get("error"):
                print(f"      {c(task['error'][:60], Colors.DIM)}")
        print()

    print(c("=" * 60, Colors.BRIGHT_CYAN))
    print()


# ============================================================================
# Interactive Menu
# ============================================================================
>>>>>>> theirs
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
<<<<<<< ours
=======
# Execution Functions
# ============================================================================
async def run_dry_run(
    task: str,
    config: Config,
    verbose: bool,
    project_path: Path | None = None,
) -> int:
    """Run in dry-run mode - plan only."""
    _ = verbose
    print()
    print(
        c("  [DRY RUN MODE] Planning task without execution...", Colors.BRIGHT_YELLOW, Colors.BOLD)
    )

    planner = Planner(config)

    # Get project context if working on an existing project
    project_context = ""
    if project_path and project_path.exists():
        project_context = get_project_context_for_planner(project_path)

    plan = planner.plan(task, project_context=project_context)

    print_plan(plan)

    # Save plan to file
    plan_file = config.orchestra_dir / "last_plan.json"
    config.ensure_dirs()

    plan_data = {
        "original_task": plan.original_task,
        "summary": plan.summary,
        "project_path": str(project_path) if project_path else None,
        "tasks": [
            {
                "title": t.title,
                "description": t.description,
                "terminal": t.terminal,
                "priority": t.priority,
                "dependencies": t.dependencies,
            }
            for t in plan.tasks
        ],
        "execution_order": plan.execution_order,
    }
    plan_file.write_text(json.dumps(plan_data, indent=2))
    print(f"  Plan saved to: {c(str(plan_file), Colors.DIM)}")

    return 0


async def run_orchestrator(
    task: str,
    config: Config,
    verbose: bool,
    timeout: int,
    max_retries: int = 2,
    project_path: Path | None = None,
) -> tuple[int, dict]:
    """Run the full orchestrator."""
    _ = max_retries
    _ = max_retries
    start_time = datetime.now()

    # Save project state before starting
    if project_path:
        save_project_state(config, project_path, task, status="in_progress")

    orchestrator = Orchestrator(config=config, verbose=verbose)

    # Get project context if working on an existing project
    project_context = ""
    if project_path and project_path.exists():
        project_context = get_project_context_for_planner(project_path)

    try:
        result = await asyncio.wait_for(
            orchestrator.run(task, project_context=project_context),
            timeout=timeout,
        )

        # Update project state on completion
        if project_path:
            status = result.get("status", "unknown")
            update_project_status(config, status)

        # Print detailed summary
        events_file = config.orchestra_dir / "events.json"
        print_detailed_summary(result, events_file, start_time)

        status = result.get("status", "unknown")
        exit_code = 0 if status == "success" else 1
        return exit_code, result

    except TimeoutError:
        print()
        time_str = format_duration(timeout)
        print(c(f"  Error: Execution timed out after {time_str}.", Colors.BRIGHT_RED, Colors.BOLD))
        print(c(f"  Increase with --timeout <seconds> (current: {timeout}s).", Colors.DIM))
        if project_path:
            update_project_status(config, "timeout")
        await orchestrator.shutdown()
        return 1, {"status": "timeout", "tasks": {"failed": 1}}
    except KeyboardInterrupt:
        print()
        print(c("  [INFO] Interrupted by user", Colors.BRIGHT_YELLOW))
        if project_path:
            update_project_status(config, "interrupted")
        await orchestrator.shutdown()
        return 130, {"status": "interrupted", "tasks": {}}


async def run_with_chat(
    task: str,
    config: Config,
    verbose: bool,
    timeout: int,
    max_retries: int = 2,
    project_path: Path | None = None,
) -> tuple[int, dict]:
    """
    Run the orchestrator with interactive Manager Chat.

    Both the orchestrator and the chat REPL run concurrently.
    """
    _ = max_retries
    start_time = datetime.now()

    # Save project state before starting
    if project_path:
        save_project_state(config, project_path, task, status="in_progress")

    orchestrator = Orchestrator(config=config, verbose=verbose)

    # Create Manager Chat
    manager = ManagerChat(orchestrator, config)

    # Get project context if working on an existing project
    project_context = ""
    if project_path and project_path.exists():
        project_context = get_project_context_for_planner(project_path)

    async def run_orchestrator_task():
        """Task wrapper for orchestrator.run()"""
        try:
            return await asyncio.wait_for(
                orchestrator.run(task, project_context=project_context),
                timeout=timeout,
            )
        except TimeoutError:
            return {"status": "timeout", "tasks": {"failed": 1}}
        except asyncio.CancelledError:
            return {"status": "cancelled", "tasks": {}}

    try:
        # Run both orchestrator and chat REPL concurrently
        orchestrator_task = asyncio.create_task(run_orchestrator_task())

        # Run chat REPL until it exits or orchestrator completes
        chat_task = asyncio.create_task(chat_repl(manager))

        # Wait for orchestrator to complete (chat can exit early)
        done, pending = await asyncio.wait(
            [orchestrator_task, chat_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        # If orchestrator finished first, stop the chat
        if orchestrator_task in done:
            manager.stop()
            # Give chat a moment to clean up
            if chat_task in pending:
                chat_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await chat_task
            result = orchestrator_task.result()
        else:
            # Chat exited - wait for orchestrator
            print(c("  Chat exited. Waiting for orchestrator to complete...", Colors.DIM))
            result = await orchestrator_task

        # Update project state on completion
        if project_path:
            status = result.get("status", "unknown")
            update_project_status(config, status)

        # Print detailed summary
        events_file = config.orchestra_dir / "events.json"
        print_detailed_summary(result, events_file, start_time)

        status = result.get("status", "unknown")
        exit_code = 0 if status == "success" else 1
        return exit_code, result

    except KeyboardInterrupt:
        print()
        print(c("  [INFO] Interrupted by user", Colors.BRIGHT_YELLOW))
        if project_path:
            update_project_status(config, "interrupted")
        await orchestrator.shutdown()
        return 130, {"status": "interrupted", "tasks": {}}


async def retry_failed_tasks(
    config: Config,
    verbose: bool,
    timeout: int,
    last_result: dict,
    project_path: Path | None = None,
) -> tuple[int, dict]:
    """Retry only the failed tasks from the last run."""
    failed_tasks = last_result.get("failed_tasks", [])

    if not failed_tasks:
        print(c("  No failed tasks to retry.", Colors.BRIGHT_YELLOW))
        return 0, last_result

    print()
    print(c(f"  Retrying {len(failed_tasks)} failed task(s)...", Colors.BRIGHT_YELLOW, Colors.BOLD))

    # Build a combined task from failed tasks
    task_descriptions = [t.get("title", "Unknown task") for t in failed_tasks]
    retry_task = "Retry the following tasks:\n" + "\n".join(f"- {t}" for t in task_descriptions)

    return await run_orchestrator(retry_task, config, verbose, timeout, project_path=project_path)


# ============================================================================
>>>>>>> theirs
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

    print_config_summary(args, project_path)

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

    if args.config:
        try:
            json.loads(Path(args.config).read_text())
<<<<<<< ours
=======
            # Apply custom config values here
>>>>>>> theirs
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
<<<<<<< ours
        print(c('    python -m orchestrator "Create an iOS app for habit tracking"', Colors.BRIGHT_WHITE))
        print(c('    python -m orchestrator --resume           # resume last session', Colors.BRIGHT_WHITE))
=======
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
        print(
            c(
                "    python -m orchestrator --help             # see all options",
                Colors.BRIGHT_WHITE,
            )
        )
>>>>>>> theirs
        return 1

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
