"""
Task Planner using Claude Code CLI to split high-level tasks into subtasks.

Uses a temporary Claude Code instance for planning - no API key needed,
uses your Claude Max subscription.
"""

import json
import re
import subprocess
from dataclasses import dataclass

from .config import Config, TerminalID


@dataclass
class PlannedTask:
    """A task planned for a specific terminal."""

    title: str
    description: str
    terminal: TerminalID
    priority: str
    dependencies: list[str]


@dataclass
class TaskPlan:
    """Complete plan for executing a high-level task."""

    original_task: str
    summary: str
    tasks: list[PlannedTask]
    execution_order: list[str]  # Task titles in order


PLANNER_PROMPT = '''You are a task planner. Analyze this task and break it down for 4 specialized terminals.

## Terminals

T1 - UI/UX: UI components, screens, layouts, styling, design systems
T2 - Features: Business logic, data models, APIs, database, architecture, ML
T3 - Docs/Marketing: README, API docs, marketing copy, App Store descriptions
T4 - Ideas/Strategy: Product requirements, MVP scope, pricing, business model

## Task to Plan

{task}
{project_context}
## Output

Return ONLY a JSON object (no markdown, no explanation, no code blocks):

{{"summary": "Brief plan summary", "tasks": [{{"title": "Task title", "description": "What to do", "terminal": "t1|t2|t3|t4", "priority": "critical|high|medium|low", "dependencies": []}}], "execution_order": ["task1", "task2"]}}

Return 3-8 tasks distributed across terminals. JSON only, nothing else.'''


PLANNER_PROMPT_WITH_PROJECT = '''You are a task planner. Analyze this task and break it down for 4 specialized terminals.

IMPORTANT: You are working on an EXISTING PROJECT. Consider the existing codebase, architecture, and patterns when planning tasks.

## Terminals

T1 - UI/UX: UI components, screens, layouts, styling, design systems
T2 - Features: Business logic, data models, APIs, database, architecture, ML
T3 - Docs/Marketing: README, API docs, marketing copy, App Store descriptions
T4 - Ideas/Strategy: Product requirements, MVP scope, pricing, business model

## Existing Project Context

{project_context}

## Task to Plan

{task}

## Planning Guidelines for Existing Projects

1. RESPECT existing architecture and patterns - don't redesign what already works
2. Identify where new code should integrate with existing code
3. Consider existing dependencies and don't introduce conflicts
4. Update existing files rather than creating duplicates
5. Maintain consistency with existing code style

## Output

Return ONLY a JSON object (no markdown, no explanation, no code blocks):

{{"summary": "Brief plan summary", "tasks": [{{"title": "Task title", "description": "What to do - be specific about which existing files to modify", "terminal": "t1|t2|t3|t4", "priority": "critical|high|medium|low", "dependencies": []}}], "execution_order": ["task1", "task2"]}}

Return 3-8 tasks distributed across terminals. JSON only, nothing else.'''


class Planner:
    """
    Uses Claude Code CLI for planning - no API key needed.
    """

    def __init__(self, config: Config):
        self.config = config

    def plan(self, task: str, project_context: str = "") -> TaskPlan:
        """
        Analyze a high-level task and create a plan using Claude Code.

        Args:
            task: High-level task description
            project_context: Optional context about an existing project

        Returns:
            TaskPlan with distributed subtasks
        """
        # Choose the appropriate prompt based on whether we have project context
        if project_context:
            prompt = PLANNER_PROMPT_WITH_PROJECT.format(
                task=task,
                project_context=project_context,
            )
        else:
            prompt = PLANNER_PROMPT.format(task=task, project_context="")

        # Use claude CLI with --print flag for non-interactive single response
        try:
            result = subprocess.run(
                ["claude", "--print", "-p", prompt],
                capture_output=True,
                text=True,
                timeout=120,
            )
            output = result.stdout

            if not output and result.stderr:
                output = result.stderr

        except subprocess.TimeoutExpired:
            print("[Planner] Claude timed out, using fallback plan")
            return self._simple_plan(task)
        except FileNotFoundError:
            print("[Planner] Claude CLI not found, using fallback plan")
            return self._simple_plan(task)
        except Exception as e:
            print(f"[Planner] Error running Claude: {e}, using fallback plan")
            return self._simple_plan(task)

        # Parse the JSON from output
        plan_data = self._extract_json(output)

        if not plan_data:
            print(f"[Planner] Could not parse JSON from output, using fallback plan")
            print(f"[Planner] Output was: {output[:300]}...")
            return self._simple_plan(task)

        # Build TaskPlan
        planned_tasks = []
        for task_data in plan_data.get("tasks", []):
            terminal = task_data.get("terminal", "t2").lower()
            if terminal not in ["t1", "t2", "t3", "t4"]:
                terminal = "t2"

            planned_tasks.append(PlannedTask(
                title=task_data.get("title", "Untitled"),
                description=task_data.get("description", ""),
                terminal=terminal,  # type: ignore
                priority=task_data.get("priority", "medium"),
                dependencies=task_data.get("dependencies", []),
            ))

        if not planned_tasks:
            return self._simple_plan(task)

        return TaskPlan(
            original_task=task,
            summary=plan_data.get("summary", "Plan created"),
            tasks=planned_tasks,
            execution_order=plan_data.get("execution_order", [t.title for t in planned_tasks]),
        )

    def _extract_json(self, text: str) -> dict | None:
        """Extract JSON object from text that may contain other content."""
        if not text:
            return None

        # Remove markdown code blocks
        text = re.sub(r'```json\s*', '', text)
        text = re.sub(r'```\s*', '', text)
        text = text.strip()

        # Try direct parse first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to find JSON object in the text
        # Look for { ... } pattern
        json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
        matches = re.findall(json_pattern, text, re.DOTALL)

        for match in matches:
            try:
                data = json.loads(match)
                if "tasks" in data or "summary" in data:
                    return data
            except json.JSONDecodeError:
                continue

        # Try more aggressive extraction - find outermost braces
        start = text.find('{')
        if start == -1:
            return None

        # Count braces to find matching end
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

    def _simple_plan(self, task: str) -> TaskPlan:
        """Simple fallback plan when Claude Code isn't available."""
        task_lower = task.lower()

        tasks = []

        # T4 always starts with strategy
        tasks.append(PlannedTask(
            title="Define product requirements",
            description=f"Analyze the task and define MVP scope, features, and success metrics for: {task}",
            terminal="t4",
            priority="critical",
            dependencies=[],
        ))

        # T2 for architecture
        tasks.append(PlannedTask(
            title="Design architecture",
            description=f"Design the technical architecture, data models, and APIs for: {task}",
            terminal="t2",
            priority="high",
            dependencies=["Define product requirements"],
        ))

        # T1 for UI
        if any(word in task_lower for word in ["app", "ui", "interface", "screen", "design"]):
            tasks.append(PlannedTask(
                title="Create UI components",
                description=f"Design and implement the user interface for: {task}",
                terminal="t1",
                priority="high",
                dependencies=["Design architecture"],
            ))

        # T2 for implementation
        tasks.append(PlannedTask(
            title="Implement core features",
            description=f"Implement the core functionality and business logic for: {task}",
            terminal="t2",
            priority="high",
            dependencies=["Design architecture"],
        ))

        # T3 for docs
        tasks.append(PlannedTask(
            title="Create documentation",
            description=f"Write README, setup guide, and user documentation for: {task}",
            terminal="t3",
            priority="medium",
            dependencies=["Implement core features"],
        ))

        return TaskPlan(
            original_task=task,
            summary=f"Simple plan for: {task}",
            tasks=tasks,
            execution_order=[t.title for t in tasks],
        )


def quick_plan(task: str, project_context: str = "") -> TaskPlan:
    """Convenience function for quick planning."""
    config = Config()
    planner = Planner(config)
    return planner.plan(task, project_context=project_context)
