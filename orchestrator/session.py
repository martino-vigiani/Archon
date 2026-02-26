"""
Session management: project state, execution runners, and plan display.

Extracted from __main__.py to keep the CLI entry point thin.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path

from .config import Config
from .orchestrator import Orchestrator
from .planner import Planner
from .manager_chat import ManagerChat, chat_repl
from .cli_display import (
    Colors,
    c,
    print_separator,
    get_terminal_color,
    get_terminal_name,
    format_duration,
)


# ============================================================================
# Project State Management
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
    except (json.JSONDecodeError, IOError):
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
    project_path = Path(project_arg).expanduser()

    if not project_path.is_absolute():
        project_path = Path.cwd() / project_path

    project_path = project_path.resolve()

    return project_path, None


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
                if list(project_path.glob(pattern)):
                    return project_type
            else:
                if (project_path / pattern).exists():
                    return project_type

    return None


def get_project_summary(project_path: Path) -> str:
    """Get a summary of the project's contents."""
    if not project_path.exists():
        return "Directory does not exist yet."

    if not project_path.is_dir():
        return f"Path exists but is not a directory: {project_path}"

    key_files = []
    key_patterns = [
        "Package.swift", "*.xcodeproj", "*.xcworkspace",
        "package.json", "tsconfig.json",
        "pyproject.toml", "setup.py", "requirements.txt",
        "Cargo.toml",
        "go.mod",
        "README.md", "README.txt", "README",
        ".gitignore", "Makefile", "Dockerfile",
    ]

    total_files = 0
    directories = []

    for item in project_path.iterdir():
        if item.name.startswith('.'):
            continue

        if item.is_dir():
            directories.append(item.name)
        else:
            total_files += 1
            for pattern in key_patterns:
                if pattern.startswith("*"):
                    if item.name.endswith(pattern[1:]):
                        key_files.append(item.name)
                        break
                elif item.name == pattern:
                    key_files.append(item.name)
                    break

    lines = []

    if key_files:
        lines.append(f"  Key files: {', '.join(sorted(key_files)[:5])}")

    if directories:
        dir_list = sorted(directories)[:8]
        lines.append(f"  Directories: {', '.join(dir_list)}")
        if len(directories) > 8:
            lines.append(f"    ... and {len(directories) - 8} more")

    lines.append(f"  Total files (top level): {total_files}")

    project_type = detect_project_type(project_path)
    if project_type:
        lines.insert(0, f"  Project type: {project_type}")

    return "\n".join(lines) if lines else "  Empty directory"


def get_project_context_for_planner(project_path: Path) -> str:
    """Generate context about an existing project for the planner."""
    if not project_path.exists():
        return ""

    context_parts = []
    context_parts.append(f"## Existing Project: {project_path.name}")
    context_parts.append(f"Path: {project_path}")
    context_parts.append("")

    project_type = detect_project_type(project_path)
    if project_type:
        context_parts.append(f"Project Type: {project_type}")
        context_parts.append("")

    dirs = []
    for item in sorted(project_path.iterdir()):
        if item.is_dir() and not item.name.startswith('.'):
            dirs.append(item.name)

    if dirs:
        context_parts.append("Directories:")
        for d in dirs[:15]:
            context_parts.append(f"  - {d}/")
        if len(dirs) > 15:
            context_parts.append(f"  ... and {len(dirs) - 15} more")
        context_parts.append("")

    key_files_content = []

    for readme_name in ["README.md", "README.txt", "README"]:
        readme_path = project_path / readme_name
        if readme_path.exists():
            try:
                content = readme_path.read_text()[:1000]
                key_files_content.append(f"README excerpt:\n{content}")
            except IOError:
                pass
            break

    package_json = project_path / "package.json"
    if package_json.exists():
        try:
            pkg = json.loads(package_json.read_text())
            key_files_content.append(
                f"package.json - name: {pkg.get('name', 'unknown')}, "
                f"deps: {len(pkg.get('dependencies', {}))}"
            )
        except (json.JSONDecodeError, IOError):
            pass

    package_swift = project_path / "Package.swift"
    if package_swift.exists():
        key_files_content.append("Package.swift exists (Swift Package)")

    pyproject = project_path / "pyproject.toml"
    if pyproject.exists():
        key_files_content.append("pyproject.toml exists (Python project)")

    if key_files_content:
        context_parts.append("Key Files:")
        for kf in key_files_content:
            context_parts.append(f"  {kf}")
        context_parts.append("")

    source_extensions = {".swift", ".py", ".ts", ".tsx", ".js", ".jsx", ".rs", ".go"}
    source_files = []

    for ext in source_extensions:
        files = list(project_path.rglob(f"*{ext}"))
        files = [f for f in files if not any(
            part in f.parts for part in [
                "node_modules", ".build", "build", "dist", "__pycache__", ".git", "venv"
            ]
        )]
        source_files.extend(files)

    if source_files:
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
        deps = (
            f" {c(f'(depends on: {', '.join(task.dependencies)})', Colors.DIM)}"
            if task.dependencies else ""
        )
        term_color = get_terminal_color(task.terminal)

        print()
        print(
            f"  {c(str(i) + '.', Colors.BOLD)} "
            f"[{c(task.terminal.upper(), term_color)}] "
            f"{c(task.title, Colors.WHITE)}"
        )
        print(f"     {c('Priority:', Colors.DIM)} {task.priority}{deps}")
        desc_preview = (
            task.description[:80] + "..." if len(task.description) > 80
            else task.description
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

    status = result.get("status", "unknown")
    status_color = (
        Colors.BRIGHT_GREEN if status == "success"
        else Colors.BRIGHT_YELLOW if status == "partial"
        else Colors.BRIGHT_RED
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
    failed_count = tasks.get("failed", 0)
    print(
        f"    Failed:            "
        f"{c(str(failed_count), Colors.BRIGHT_RED if failed_count > 0 else Colors.DIM)}"
    )
    pending_count = tasks.get("pending", 0)
    print(
        f"    Pending:           "
        f"{c(str(pending_count), Colors.BRIGHT_YELLOW if pending_count > 0 else Colors.DIM)}"
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
                    f"    {c(f'[{term_id.upper()}]', color)} {name}: "
                    f"{c(str(total), Colors.BRIGHT_WHITE)} tasks "
                    f"({c(str(stats['completed']), Colors.BRIGHT_GREEN)} ok, "
                    f"{c(str(stats['failed']), Colors.BRIGHT_RED)} failed)"
                )
        print()

    # Subagents used
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

    # Files changed
    files_created = result.get("files_created", [])
    files_modified = result.get("files_modified", [])

    if files_created or files_modified:
        print(c("  Files Changed", Colors.BOLD, Colors.BRIGHT_CYAN))
        print(c("  " + "-" * 25, Colors.DIM))
        if files_created:
            print(f"    Created:           {c(str(len(files_created)), Colors.BRIGHT_GREEN)}")
            for f in files_created[:5]:
                print(f"      + {c(f, Colors.GREEN)}")
            if len(files_created) > 5:
                print(f"      ... and {len(files_created) - 5} more")
        if files_modified:
            print(f"    Modified:          {c(str(len(files_modified)), Colors.BRIGHT_YELLOW)}")
            for f in files_modified[:5]:
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
# Execution Runners
# ============================================================================

async def run_dry_run(
    task: str,
    config: Config,
    verbose: bool,
    project_path: Path | None = None,
) -> int:
    """Run in dry-run mode - plan only."""
    print()
    print(c("  [DRY RUN MODE] Planning task without execution...", Colors.BRIGHT_YELLOW, Colors.BOLD))

    planner = Planner(config)

    project_context = ""
    if project_path and project_path.exists():
        project_context = get_project_context_for_planner(project_path)

    plan = await planner.plan(task, project_context=project_context)

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
    start_time = datetime.now()

    if project_path:
        save_project_state(config, project_path, task, status="in_progress")

    orchestrator = Orchestrator(config=config, verbose=verbose)

    project_context = ""
    if project_path and project_path.exists():
        project_context = get_project_context_for_planner(project_path)

    try:
        result = await asyncio.wait_for(
            orchestrator.run(task, project_context=project_context),
            timeout=timeout,
        )

        if project_path:
            status = result.get("status", "unknown")
            update_project_status(config, status)

        events_file = config.orchestra_dir / "events.json"
        print_detailed_summary(result, events_file, start_time)

        status = result.get("status", "unknown")
        exit_code = 0 if status == "success" else 1
        return exit_code, result

    except asyncio.TimeoutError:
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
    """Run the orchestrator with interactive Manager Chat."""
    start_time = datetime.now()

    if project_path:
        save_project_state(config, project_path, task, status="in_progress")

    orchestrator = Orchestrator(config=config, verbose=verbose)
    manager = ManagerChat(orchestrator, config)

    project_context = ""
    if project_path and project_path.exists():
        project_context = get_project_context_for_planner(project_path)

    async def run_orchestrator_task():
        try:
            return await asyncio.wait_for(
                orchestrator.run(task, project_context=project_context),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            return {"status": "timeout", "tasks": {"failed": 1}}
        except asyncio.CancelledError:
            return {"status": "cancelled", "tasks": {}}

    try:
        orchestrator_task = asyncio.create_task(run_orchestrator_task())
        chat_task = asyncio.create_task(chat_repl(manager))

        done, pending = await asyncio.wait(
            [orchestrator_task, chat_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        if orchestrator_task in done:
            manager.stop()
            if chat_task in pending:
                chat_task.cancel()
                try:
                    await chat_task
                except asyncio.CancelledError:
                    pass
            result = orchestrator_task.result()
        else:
            print(c("  Chat exited. Waiting for orchestrator to complete...", Colors.DIM))
            result = await orchestrator_task

        if project_path:
            status = result.get("status", "unknown")
            update_project_status(config, status)

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

    task_descriptions = [t.get("title", "Unknown task") for t in failed_tasks]
    retry_task = "Retry the following tasks:\n" + "\n".join(f"- {t}" for t in task_descriptions)

    return await run_orchestrator(retry_task, config, verbose, timeout, project_path=project_path)
