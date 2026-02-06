"""
Report Manager for structured terminal output.

Each terminal writes structured reports after completing tasks.
The orchestrator uses these reports to coordinate between terminals.
"""

import json
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

from .config import Config, TerminalID


@dataclass
class Report:
    """Structured report from a terminal after completing a task."""

    # Identification
    id: str
    task_id: str
    terminal_id: TerminalID
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    # What was done
    summary: str = ""
    files_created: list[str] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
    components_created: list[str] = field(default_factory=list)  # Components, classes, functions exposed

    # Dependencies and connections
    dependencies_needed: list[dict] = field(default_factory=list)  # {"from": "t2", "what": "User model"}
    provides_to_others: list[dict] = field(default_factory=list)  # {"to": "t1", "what": "UserAPI endpoints"}

    # Next steps
    next_steps: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)

    # Raw output for reference
    raw_output: str = ""

    # Status
    success: bool = True
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "terminal_id": self.terminal_id,
            "timestamp": self.timestamp,
            "summary": self.summary,
            "files_created": self.files_created,
            "files_modified": self.files_modified,
            "components_created": self.components_created,
            "dependencies_needed": self.dependencies_needed,
            "provides_to_others": self.provides_to_others,
            "next_steps": self.next_steps,
            "blockers": self.blockers,
            "success": self.success,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Report":
        return cls(
            id=data.get("id", ""),
            task_id=data.get("task_id", ""),
            terminal_id=data.get("terminal_id", "t2"),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
            summary=data.get("summary", ""),
            files_created=data.get("files_created", []),
            files_modified=data.get("files_modified", []),
            components_created=data.get("components_created", []),
            dependencies_needed=data.get("dependencies_needed", []),
            provides_to_others=data.get("provides_to_others", []),
            next_steps=data.get("next_steps", []),
            blockers=data.get("blockers", []),
            raw_output=data.get("raw_output", ""),
            success=data.get("success", True),
            error=data.get("error"),
        )

    def to_markdown(self) -> str:
        """Format report as markdown for terminal consumption."""
        md = f"""# Report: {self.task_id}

**Terminal:** {self.terminal_id}
**Time:** {self.timestamp}
**Status:** {"Success" if self.success else f"Failed: {self.error}"}

## Summary

{self.summary}

"""
        if self.files_created:
            md += "## Files Created\n\n"
            for f in self.files_created:
                md += f"- `{f}`\n"
            md += "\n"

        if self.files_modified:
            md += "## Files Modified\n\n"
            for f in self.files_modified:
                md += f"- `{f}`\n"
            md += "\n"

        if self.components_created:
            md += "## Components/APIs Exposed\n\n"
            for c in self.components_created:
                md += f"- {c}\n"
            md += "\n"

        if self.provides_to_others:
            md += "## Available for Other Terminals\n\n"
            for p in self.provides_to_others:
                md += f"- **{p.get('to', 'all')}** can use: {p.get('what', '')}\n"
            md += "\n"

        if self.dependencies_needed:
            md += "## Dependencies Needed\n\n"
            for d in self.dependencies_needed:
                md += f"- Need from **{d.get('from', '?')}**: {d.get('what', '')}\n"
            md += "\n"

        if self.next_steps:
            md += "## Suggested Next Steps\n\n"
            for s in self.next_steps:
                md += f"- {s}\n"
            md += "\n"

        if self.blockers:
            md += "## Blockers\n\n"
            for b in self.blockers:
                md += f"- {b}\n"
            md += "\n"

        return md


# Prompt for parsing terminal output into structured report
REPORT_PARSER_PROMPT = '''Analyze this terminal output and extract a structured report.

## Terminal Output

{output}

## Task Context

Task: {task_title}
Terminal: {terminal_id} ({terminal_role})

## Instructions

Extract the following information and return ONLY a JSON object (no markdown, no explanation):

{{
  "summary": "1-2 sentence summary of what was accomplished",
  "files_created": ["list", "of", "file/paths/created.swift"],
  "files_modified": ["list", "of", "file/paths/modified.swift"],
  "components_created": ["ComponentName", "ClassName", "functionName", "APIEndpoint"],
  "provides_to_others": [
    {{"to": "t1|t2|t3|t4|all", "what": "Description of what this provides"}}
  ],
  "dependencies_needed": [
    {{"from": "t1|t2|t3|t4", "what": "Description of what is needed"}}
  ],
  "next_steps": ["Suggested next action 1", "Suggested next action 2"],
  "blockers": ["Any blocking issue"],
  "success": true
}}

Be specific about file paths and component names. JSON only, no other text.'''


class ReportManager:
    """
    Manages structured reports from terminals.

    Responsibilities:
    - Parse terminal output into structured reports
    - Store reports organized by terminal
    - Provide context from relevant reports to other terminals
    - Track what each terminal has produced/needs
    """

    def __init__(self, config: Config):
        self.config = config
        self._report_counter = 0
        self._ensure_dirs()

    @property
    def reports_dir(self) -> Path:
        return self.config.orchestra_dir / "reports"

    def _ensure_dirs(self) -> None:
        """Create report directories for each terminal."""
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        for tid in ["t1", "t2", "t3", "t4", "t5"]:
            (self.reports_dir / tid).mkdir(exist_ok=True)
        # Also create a summary directory
        (self.reports_dir / "summary").mkdir(exist_ok=True)

    def _generate_report_id(self) -> str:
        """Generate unique report ID."""
        self._report_counter += 1
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"report_{timestamp}_{self._report_counter:04d}"

    def parse_output_to_report(
        self,
        output: str,
        task_id: str,
        task_title: str,
        terminal_id: TerminalID,
        success: bool = True,
        error: str | None = None,
    ) -> Report:
        """
        Parse terminal output into a structured report using Claude.

        Args:
            output: Raw terminal output
            task_id: ID of the completed task
            task_title: Title of the task
            terminal_id: Which terminal produced this output
            success: Whether the task succeeded
            error: Error message if failed

        Returns:
            Structured Report object
        """
        report_id = self._generate_report_id()

        # If task failed, create minimal report
        if not success:
            return Report(
                id=report_id,
                task_id=task_id,
                terminal_id=terminal_id,
                summary=f"Task failed: {error or 'Unknown error'}",
                raw_output=output[:5000],  # Limit stored output
                success=False,
                error=error,
            )

        # Get terminal role for context
        terminal_config = self.config.get_terminal_config(terminal_id)

        # Use Claude to parse the output
        prompt = REPORT_PARSER_PROMPT.format(
            output=output[:8000],  # Limit input to avoid token issues
            task_title=task_title,
            terminal_id=terminal_id,
            terminal_role=terminal_config.role,
        )

        try:
            result = subprocess.run(
                ["claude", "--print", "-p", prompt],
                capture_output=True,
                text=True,
                timeout=60,
            )
            parsed = self._extract_json(result.stdout)

            if parsed:
                return Report(
                    id=report_id,
                    task_id=task_id,
                    terminal_id=terminal_id,
                    summary=parsed.get("summary", "Task completed"),
                    files_created=parsed.get("files_created", []),
                    files_modified=parsed.get("files_modified", []),
                    components_created=parsed.get("components_created", []),
                    provides_to_others=parsed.get("provides_to_others", []),
                    dependencies_needed=parsed.get("dependencies_needed", []),
                    next_steps=parsed.get("next_steps", []),
                    blockers=parsed.get("blockers", []),
                    raw_output=output[:5000],
                    success=parsed.get("success", True),
                )

        except Exception as e:
            print(f"[ReportManager] Error parsing output: {e}")

        # Fallback: create basic report from output analysis
        return self._fallback_parse(output, report_id, task_id, terminal_id)

    def _fallback_parse(
        self,
        output: str,
        report_id: str,
        task_id: str,
        terminal_id: TerminalID,
    ) -> Report:
        """Fallback parsing when Claude parsing fails."""
        # Simple regex-based extraction
        files_created = []
        files_modified = []

        # Look for file paths in output
        file_patterns = [
            r'(?:created?|wrote?|generated?)\s+[`"\']?([a-zA-Z0-9_/.-]+\.[a-zA-Z]+)[`"\']?',
            r'(?:modified?|updated?|edited?)\s+[`"\']?([a-zA-Z0-9_/.-]+\.[a-zA-Z]+)[`"\']?',
        ]

        for pattern in file_patterns[:1]:
            matches = re.findall(pattern, output, re.IGNORECASE)
            files_created.extend(matches[:10])

        for pattern in file_patterns[1:]:
            matches = re.findall(pattern, output, re.IGNORECASE)
            files_modified.extend(matches[:10])

        # Extract summary from first meaningful line
        lines = [l.strip() for l in output.split('\n') if l.strip() and not l.startswith('#')]
        summary = lines[0][:200] if lines else "Task completed"

        return Report(
            id=report_id,
            task_id=task_id,
            terminal_id=terminal_id,
            summary=summary,
            files_created=files_created,
            files_modified=files_modified,
            raw_output=output[:5000],
            success=True,
        )

    def _extract_json(self, text: str) -> dict | None:
        """Extract JSON from text that may contain other content."""
        if not text:
            return None

        # Remove markdown code blocks
        text = re.sub(r'```json\s*', '', text)
        text = re.sub(r'```\s*', '', text)
        text = text.strip()

        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Find JSON in text
        start = text.find('{')
        if start == -1:
            return None

        depth = 0
        for i, char in enumerate(text[start:], start):
            if char == '{':
                depth += 1
            elif char == '}':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i+1])
                    except json.JSONDecodeError:
                        break

        return None

    def save_report(self, report: Report) -> Path:
        """Save a report to disk."""
        # Save to terminal-specific directory
        terminal_dir = self.reports_dir / report.terminal_id
        report_file = terminal_dir / f"{report.id}.json"
        report_file.write_text(json.dumps(report.to_dict(), indent=2))

        # Also save markdown version
        md_file = terminal_dir / f"{report.id}.md"
        md_file.write_text(report.to_markdown())

        # Update summary index
        self._update_summary_index(report)

        return report_file

    def _update_summary_index(self, report: Report) -> None:
        """Update the summary index with latest report info."""
        summary_file = self.reports_dir / "summary" / "index.json"

        # Load existing summary
        summary = {}
        if summary_file.exists():
            try:
                summary = json.loads(summary_file.read_text())
            except json.JSONDecodeError:
                summary = {}

        # Update terminal's latest info
        if report.terminal_id not in summary:
            summary[report.terminal_id] = {
                "reports": [],
                "components": [],
                "files": [],
            }

        terminal_summary = summary[report.terminal_id]

        # Add report reference
        terminal_summary["reports"].append({
            "id": report.id,
            "task_id": report.task_id,
            "timestamp": report.timestamp,
            "summary": report.summary[:100],
        })

        # Keep only last 20 reports
        terminal_summary["reports"] = terminal_summary["reports"][-20:]

        # Track components
        for comp in report.components_created:
            if comp not in terminal_summary["components"]:
                terminal_summary["components"].append(comp)

        # Track files
        for f in report.files_created + report.files_modified:
            if f not in terminal_summary["files"]:
                terminal_summary["files"].append(f)

        # Save updated summary
        summary_file.write_text(json.dumps(summary, indent=2))

    def get_reports_for_terminal(
        self,
        terminal_id: TerminalID,
        limit: int = 10,
    ) -> list[Report]:
        """Get recent reports from a terminal."""
        terminal_dir = self.reports_dir / terminal_id
        reports = []

        if not terminal_dir.exists():
            return reports

        # Get JSON files sorted by name (which includes timestamp)
        json_files = sorted(terminal_dir.glob("*.json"), reverse=True)

        for json_file in json_files[:limit]:
            try:
                data = json.loads(json_file.read_text())
                reports.append(Report.from_dict(data))
            except (json.JSONDecodeError, IOError):
                continue

        return reports

    def get_context_for_terminal(
        self,
        target_terminal: TerminalID,
        task_description: str,
    ) -> str:
        """
        Gather relevant context from other terminals' reports for a task.

        This is what makes the orchestrator a smart manager - it understands
        what each terminal has done and provides relevant context to others.

        Args:
            target_terminal: The terminal that will receive the context
            task_description: Description of the task to be executed

        Returns:
            Markdown-formatted context string
        """
        context_parts = []

        # Get reports from all OTHER terminals
        for tid in ["t1", "t2", "t3", "t4", "t5"]:
            if tid == target_terminal:
                continue

            reports = self.get_reports_for_terminal(tid, limit=5)  # type: ignore
            if not reports:
                continue

            terminal_config = self.config.get_terminal_config(tid)  # type: ignore

            # Filter to relevant reports
            relevant_reports = self._filter_relevant_reports(
                reports,
                task_description,
                target_terminal,
            )

            if relevant_reports:
                context_parts.append(f"### From {tid.upper()} ({terminal_config.role})\n")

                for report in relevant_reports:
                    context_parts.append(f"**{report.summary}**\n")

                    if report.components_created:
                        context_parts.append("Available components: " + ", ".join(report.components_created[:5]) + "\n")

                    if report.files_created:
                        context_parts.append("Files: " + ", ".join(f"`{f}`" for f in report.files_created[:3]) + "\n")

                    # Check if this report provides something to target
                    for provides in report.provides_to_others:
                        if provides.get("to") in [target_terminal, "all"]:
                            context_parts.append(f"- Available for you: {provides.get('what', '')}\n")

                    context_parts.append("\n")

        if context_parts:
            return "## Context from Other Terminals\n\n" + "".join(context_parts)

        return ""

    def _filter_relevant_reports(
        self,
        reports: list[Report],
        task_description: str,
        target_terminal: TerminalID,
    ) -> list[Report]:
        """Filter reports to only those relevant to the task."""
        relevant = []
        task_lower = task_description.lower()

        for report in reports:
            # Check if report provides something to target terminal
            provides_to_target = any(
                p.get("to") in [target_terminal, "all"]
                for p in report.provides_to_others
            )

            # Check keyword overlap
            report_text = (report.summary + " ".join(report.components_created)).lower()
            keywords = ["model", "view", "api", "component", "service", "data", "user"]
            keyword_match = any(kw in report_text and kw in task_lower for kw in keywords)

            if provides_to_target or keyword_match:
                relevant.append(report)

        return relevant[:3]  # Limit to avoid context bloat

    def get_all_components(self) -> dict[TerminalID, list[str]]:
        """Get all components created by each terminal."""
        summary_file = self.reports_dir / "summary" / "index.json"

        if not summary_file.exists():
            return {}

        try:
            summary = json.loads(summary_file.read_text())
            return {
                tid: data.get("components", [])  # type: ignore
                for tid, data in summary.items()
            }
        except (json.JSONDecodeError, IOError):
            return {}

    def get_dependencies_graph(self) -> dict[TerminalID, list[dict]]:
        """Get dependency graph showing what each terminal needs from others."""
        dependencies: dict[TerminalID, list[dict]] = {
            "t1": [], "t2": [], "t3": [], "t4": [], "t5": []
        }

        for tid in ["t1", "t2", "t3", "t4", "t5"]:
            reports = self.get_reports_for_terminal(tid, limit=10)  # type: ignore
            for report in reports:
                for dep in report.dependencies_needed:
                    if dep not in dependencies[tid]:  # type: ignore
                        dependencies[tid].append(dep)  # type: ignore

        return dependencies

    def clear_reports(self, terminal_id: TerminalID | None = None) -> None:
        """Clear reports for a terminal or all terminals."""
        if terminal_id:
            terminal_dir = self.reports_dir / terminal_id
            if terminal_dir.exists():
                for f in terminal_dir.glob("*"):
                    f.unlink()
        else:
            # Clear all
            for tid in ["t1", "t2", "t3", "t4", "t5"]:
                self.clear_reports(tid)  # type: ignore
            # Also clear summary
            summary_dir = self.reports_dir / "summary"
            if summary_dir.exists():
                for f in summary_dir.glob("*"):
                    f.unlink()
