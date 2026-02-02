"""
Configuration for Archon Orchestrator.

Defines terminal roles, subagent mappings, system paths, and project management.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal, TypedDict


TerminalID = Literal["t1", "t2", "t3", "t4", "t5"]


class ProjectMetadata(TypedDict):
    """Type definition for project metadata."""

    name: str
    created_at: str
    updated_at: str
    version: str
    description: str
    type: str  # "ios", "web", "python", "node", "other"
    status: str  # "active", "archived", "template"
    tags: list[str]


@dataclass
class TerminalConfig:
    """Configuration for a single terminal."""

    id: TerminalID
    role: str
    description: str
    subagents: list[str]
    keywords: list[str]  # Keywords that route tasks to this terminal

    @property
    def prompt_file(self) -> str:
        """Return the prompt template filename."""
        role_map = {
            "t1": "t1_uiux.md",
            "t2": "t2_features.md",
            "t3": "t3_docs.md",
            "t4": "t4_ideas.md",
            "t5": "t5_qa.md",
        }
        return role_map[self.id]


# Terminal configurations
TERMINALS: dict[TerminalID, TerminalConfig] = {
    "t1": TerminalConfig(
        id="t1",
        role="UI/UX",
        description="Handles all user interface and user experience tasks",
        subagents=["swiftui-crafter", "react-crafter", "html-stylist", "design-system"],
        keywords=[
            "ui", "ux", "interface", "design", "component", "view", "screen",
            "layout", "style", "color", "font", "animation", "swiftui", "react",
            "css", "tailwind", "visual", "button", "form", "modal", "navigation",
            "responsive", "theme", "dark mode", "light mode", "accessibility"
        ],
    ),
    "t2": TerminalConfig(
        id="t2",
        role="Features",
        description="Implements core features, architecture, and data layer",
        subagents=[
            "swift-architect", "node-architect", "python-architect",
            "swiftdata-expert", "database-expert", "ml-engineer"
        ],
        keywords=[
            "feature", "implement", "function", "logic", "backend", "api",
            "database", "model", "schema", "architecture", "pattern", "mvvm",
            "service", "repository", "controller", "manager", "handler",
            "storage", "persistence", "sync", "network", "authentication",
            "authorization", "security", "performance", "cache", "queue",
            "algorithm", "ml", "ai", "training", "data", "migration"
        ],
    ),
    "t3": TerminalConfig(
        id="t3",
        role="Docs/Marketing",
        description="Creates documentation and marketing materials",
        subagents=["tech-writer", "marketing-strategist"],
        keywords=[
            "documentation", "docs", "readme", "guide", "tutorial", "api docs",
            "comment", "marketing", "copy", "landing", "app store", "description",
            "screenshot", "video", "press", "announcement", "blog", "social",
            "changelog", "release notes", "onboarding", "help", "faq"
        ],
    ),
    "t4": TerminalConfig(
        id="t4",
        role="Ideas/Strategy",
        description="Handles product strategy, ideation, and monetization",
        subagents=["product-thinker", "monetization-expert"],
        keywords=[
            "idea", "strategy", "product", "roadmap", "mvp", "feature priority",
            "user story", "requirement", "spec", "monetization", "pricing",
            "subscription", "freemium", "revenue", "business model", "market",
            "competitor", "analysis", "validation", "hypothesis", "experiment",
            "metric", "kpi", "growth", "retention", "acquisition"
        ],
    ),
    "t5": TerminalConfig(
        id="t5",
        role="QA/Testing",
        description="Runs tests, validates outputs, verifies code quality and compilation",
        subagents=["testing-genius", "swift-architect", "node-architect", "python-architect"],
        keywords=[
            "test", "testing", "verify", "validate", "check", "quality", "qa",
            "build", "compile", "run tests", "pytest", "swift test", "npm test",
            "coverage", "lint", "format", "audit", "security", "scan",
            "unit test", "integration test", "e2e", "assertion", "mock",
            "fixture", "snapshot", "regression", "benchmark", "performance",
            "edge case", "stress test", "chaos", "fuzzing", "property-based",
            "mutation testing", "test strategy", "test architecture"
        ],
    ),
}


# Standard project structure
PROJECT_SUBDIRS = ["src", "docs", "assets", "tests"]

# Standard .gitignore patterns for Archon projects
STANDARD_GITIGNORE_PATTERNS = [
    # OS files
    ".DS_Store",
    "Thumbs.db",
    "*.swp",
    "*.swo",
    "*~",

    # IDE/Editor
    ".idea/",
    ".vscode/",
    "*.xcuserdata/",
    "*.xcworkspace/",

    # Python
    "__pycache__/",
    "*.py[cod]",
    "*$py.class",
    ".Python",
    "*.egg-info/",
    ".eggs/",
    "dist/",
    "build/",
    ".venv/",
    "venv/",
    "env/",
    ".env",
    ".env.local",
    "*.egg",
    ".pytest_cache/",
    ".coverage",
    "htmlcov/",
    ".mypy_cache/",
    ".ruff_cache/",

    # Node.js
    "node_modules/",
    "npm-debug.log*",
    "yarn-debug.log*",
    "yarn-error.log*",
    ".npm/",
    ".yarn/",
    "package-lock.json",
    "yarn.lock",
    ".next/",
    "out/",

    # iOS/Swift
    "DerivedData/",
    "*.xcuserstate",
    "*.ipa",
    "*.dSYM.zip",
    "*.dSYM",
    "Pods/",
    ".build/",

    # Temporary files
    "*.tmp",
    "*.temp",
    "*.log",
    "*.bak",
    "*.backup",
    ".cache/",
    "tmp/",
    "temp/",

    # Secrets and credentials
    "*.pem",
    "*.key",
    "*.p12",
    "credentials.json",
    "secrets.json",
    ".secrets/",

    # Archon internal
    ".archon/cache/",
    ".archon/*.log",
]

# Patterns for temporary files to ignore during cleanup
TEMP_FILE_PATTERNS = [
    "*.tmp",
    "*.temp",
    "*.log",
    "*.bak",
    "*.backup",
    "*~",
    "*.swp",
    "*.swo",
    ".DS_Store",
    "Thumbs.db",
    "__pycache__",
    "*.pyc",
    "*.pyo",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    ".next",
    "DerivedData",
    ".build",
    ".cache",
]


@dataclass
class Config:
    """Main orchestrator configuration."""

    # Paths
    base_dir: Path = field(default_factory=lambda: Path.home() / "Tech" / "Archon")
    orchestra_dir: Path = field(default_factory=lambda: Path.home() / "Tech" / "Archon" / ".orchestra")
    templates_dir: Path = field(default_factory=lambda: Path.home() / "Tech" / "Archon" / "templates" / "terminal_prompts")
    agents_dir: Path = field(default_factory=lambda: Path.home() / "Tech" / "Archon" / ".claude" / "agents")
    apps_dir: Path = field(default_factory=lambda: Path.home() / "Tech" / "Archon" / "Apps")

    # Terminal settings
    terminals: dict[TerminalID, TerminalConfig] = field(default_factory=lambda: TERMINALS)
    max_terminals: int = 4

    # Timing
    poll_interval: float = 2.0  # Seconds between status checks
    terminal_timeout: float = 600.0  # Max seconds to wait for terminal response (10 min)
    message_check_interval: float = 1.0  # Seconds between message bus checks

    # Behavior
    auto_assign_tasks: bool = True
    verbose: bool = True
    disable_testing: bool = False  # --no-testing flag disables T5 terminal

    @property
    def messages_dir(self) -> Path:
        return self.orchestra_dir / "messages"

    @property
    def tasks_dir(self) -> Path:
        return self.orchestra_dir / "tasks"

    @property
    def artifacts_dir(self) -> Path:
        return self.orchestra_dir / "artifacts"

    @property
    def status_file(self) -> Path:
        return self.orchestra_dir / "status.json"

    def get_terminal_inbox(self, terminal_id: TerminalID) -> Path:
        return self.messages_dir / f"{terminal_id}_inbox.md"

    def get_broadcast_file(self) -> Path:
        return self.messages_dir / "broadcast.md"

    def ensure_dirs(self) -> None:
        """Create all required directories."""
        self.orchestra_dir.mkdir(parents=True, exist_ok=True)
        self.messages_dir.mkdir(exist_ok=True)
        self.tasks_dir.mkdir(exist_ok=True)
        self.artifacts_dir.mkdir(exist_ok=True)
        self.templates_dir.mkdir(parents=True, exist_ok=True)
        self.apps_dir.mkdir(parents=True, exist_ok=True)

    def get_terminal_config(self, terminal_id: TerminalID) -> TerminalConfig:
        """Get configuration for a specific terminal."""
        return self.terminals[terminal_id]

    def route_task_to_terminal(self, task_description: str) -> TerminalID:
        """Route a task to the most appropriate terminal based on keywords."""
        task_lower = task_description.lower()
        scores: dict[TerminalID, int] = {"t1": 0, "t2": 0, "t3": 0, "t4": 0}

        for tid, config in self.terminals.items():
            for keyword in config.keywords:
                if keyword in task_lower:
                    scores[tid] += 1

        # Return terminal with highest score, default to t2 (features)
        best = max(scores, key=lambda k: scores[k])
        return best if scores[best] > 0 else "t2"

    # -------------------------------------------------------------------------
    # Project Management
    # -------------------------------------------------------------------------

    def get_project_path(self, name: str) -> Path:
        """Get the full path for a project by name."""
        return self.apps_dir / name

    def create_project_structure(
        self,
        name: str,
        description: str = "",
        project_type: str = "other",
        tags: list[str] | None = None,
    ) -> Path:
        """
        Create the standard directory structure for a new Archon project.

        Args:
            name: Project name (will be used as directory name)
            description: Short project description
            project_type: Type of project ("ios", "web", "python", "node", "other")
            tags: Optional list of tags for categorization

        Returns:
            Path to the created project directory

        Raises:
            ValueError: If project name is invalid or already exists
        """
        # Validate name
        if not name or not name.strip():
            raise ValueError("Project name cannot be empty")

        # Sanitize name (allow alphanumeric, dash, underscore)
        sanitized = "".join(c for c in name if c.isalnum() or c in "-_")
        if not sanitized:
            raise ValueError(f"Invalid project name: {name}")

        project_path = self.apps_dir / sanitized

        if project_path.exists():
            raise ValueError(f"Project already exists: {project_path}")

        # Create main project directory
        project_path.mkdir(parents=True, exist_ok=True)

        # Create standard subdirectories
        for subdir in PROJECT_SUBDIRS:
            (project_path / subdir).mkdir(exist_ok=True)

        # Create .archon metadata directory
        archon_dir = project_path / ".archon"
        archon_dir.mkdir(exist_ok=True)

        # Create project.json metadata file
        now = datetime.now().isoformat()
        metadata: ProjectMetadata = {
            "name": sanitized,
            "created_at": now,
            "updated_at": now,
            "version": "0.1.0",
            "description": description,
            "type": project_type,
            "status": "active",
            "tags": tags or [],
        }

        metadata_file = archon_dir / "project.json"
        metadata_file.write_text(json.dumps(metadata, indent=2))

        # Create standard .gitignore
        gitignore_file = project_path / ".gitignore"
        gitignore_file.write_text("\n".join(STANDARD_GITIGNORE_PATTERNS) + "\n")

        # Create placeholder README
        readme_file = project_path / "README.md"
        readme_content = f"# {sanitized}\n\n{description}\n\n## Project Structure\n\n"
        readme_content += "```\n"
        readme_content += f"{sanitized}/\n"
        for subdir in PROJECT_SUBDIRS:
            readme_content += f"  {subdir}/\n"
        readme_content += "```\n\n"
        readme_content += f"Created with [Archon]({self.base_dir})\n"
        readme_file.write_text(readme_content)

        return project_path

    def get_project_info(self, path: str | Path) -> ProjectMetadata | None:
        """
        Read project information from .archon/project.json if it exists.

        Args:
            path: Path to the project directory

        Returns:
            ProjectMetadata dictionary if valid Archon project, None otherwise
        """
        project_path = Path(path)
        metadata_file = project_path / ".archon" / "project.json"

        if not metadata_file.exists():
            return None

        try:
            content = metadata_file.read_text()
            data = json.loads(content)
            # Validate required fields
            required_fields = ["name", "created_at", "updated_at", "version", "type", "status"]
            if not all(field in data for field in required_fields):
                return None
            return data
        except (json.JSONDecodeError, IOError):
            return None

    def update_project_info(self, path: str | Path, **updates: str | list[str]) -> bool:
        """
        Update project metadata.

        Args:
            path: Path to the project directory
            **updates: Fields to update (description, version, status, tags, etc.)

        Returns:
            True if update was successful, False otherwise
        """
        project_path = Path(path)
        metadata_file = project_path / ".archon" / "project.json"

        if not metadata_file.exists():
            return False

        try:
            data = json.loads(metadata_file.read_text())
            data.update(updates)
            data["updated_at"] = datetime.now().isoformat()
            metadata_file.write_text(json.dumps(data, indent=2))
            return True
        except (json.JSONDecodeError, IOError):
            return False

    def list_projects(self, status: str | None = None) -> list[tuple[str, ProjectMetadata]]:
        """
        List all Archon projects in the Apps directory.

        Args:
            status: Optional filter by status ("active", "archived", "template")

        Returns:
            List of (project_name, metadata) tuples
        """
        projects: list[tuple[str, ProjectMetadata]] = []

        if not self.apps_dir.exists():
            return projects

        for item in self.apps_dir.iterdir():
            if item.is_dir():
                info = self.get_project_info(item)
                if info:
                    if status is None or info.get("status") == status:
                        projects.append((item.name, info))

        # Sort by updated_at descending (most recent first)
        projects.sort(key=lambda x: x[1].get("updated_at", ""), reverse=True)
        return projects

    def is_archon_project(self, path: str | Path) -> bool:
        """Check if a directory is a valid Archon project."""
        return self.get_project_info(path) is not None

    # -------------------------------------------------------------------------
    # Project Cleanup
    # -------------------------------------------------------------------------

    def get_temp_file_patterns(self) -> list[str]:
        """Get list of temporary file patterns to ignore/clean."""
        return TEMP_FILE_PATTERNS.copy()

    def get_gitignore_patterns(self) -> list[str]:
        """Get standard .gitignore patterns for Archon projects."""
        return STANDARD_GITIGNORE_PATTERNS.copy()

    def identify_temp_files(self, path: str | Path) -> list[Path]:
        """
        Identify temporary files in a project directory.

        Args:
            path: Path to scan for temporary files

        Returns:
            List of paths to temporary files/directories
        """
        project_path = Path(path)
        temp_files: list[Path] = []

        if not project_path.exists():
            return temp_files

        for pattern in TEMP_FILE_PATTERNS:
            # Handle both file patterns and directory names
            if pattern.startswith("*"):
                # Glob pattern (e.g., *.tmp)
                temp_files.extend(project_path.rglob(pattern))
            else:
                # Exact name match (e.g., __pycache__)
                temp_files.extend(project_path.rglob(pattern))

        return temp_files

    def generate_gitignore(self, path: str | Path, extra_patterns: list[str] | None = None) -> Path:
        """
        Generate or update .gitignore file for a project.

        Args:
            path: Path to project directory
            extra_patterns: Additional patterns to include

        Returns:
            Path to the created/updated .gitignore file
        """
        project_path = Path(path)
        gitignore_file = project_path / ".gitignore"

        patterns = STANDARD_GITIGNORE_PATTERNS.copy()
        if extra_patterns:
            patterns.extend(extra_patterns)

        # Remove duplicates while preserving order
        seen: set[str] = set()
        unique_patterns: list[str] = []
        for p in patterns:
            if p not in seen:
                seen.add(p)
                unique_patterns.append(p)

        gitignore_file.write_text("\n".join(unique_patterns) + "\n")
        return gitignore_file
