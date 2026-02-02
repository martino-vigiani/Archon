"""
Task Planner using Claude Code CLI to split high-level tasks into subtasks.

## Planning Models

### Legacy Model (deprecated but supported):
PARALLEL-FIRST PLANNING: All terminals start immediately.
Dependencies are soft (informational), not blocking.
Uses phase (0-3) to gate execution.

### Organic Flow Model (v2.0):
INTENT-BASED PLANNING: Broadcast high-level intent, let terminals interpret.
- Instead of rigid task assignments, broadcast goals and let terminals self-organize
- Quality is a gradient (0.0-1.0) not binary completion
- Flow state tracks health of work, not phase progression
"""

import json
import re
import subprocess
from dataclasses import dataclass, field

from .config import Config, TerminalID


@dataclass
class PlannedTask:
    """
    A task planned for a specific terminal.

    Supports both legacy phase model and organic flow model.
    """

    title: str
    description: str
    terminal: TerminalID
    priority: str
    dependencies: list[str]  # Soft dependencies - informational only

    # Legacy field (kept for backward compatibility)
    phase: int  # 0 = planning, 1 = build, 2 = integration, 3 = testing

    # Organic Flow fields (v2.0)
    intent: str | None = None  # High-level intent/goal for organic planning
    quality_target: float = 1.0  # Target quality level (0.0-1.0)

    required_subagents: list[str] = field(default_factory=list)  # Suggested subagents


@dataclass
class Intent:
    """
    High-level intent for organic flow planning (v2.0).

    Instead of assigning rigid tasks, we broadcast intents that
    terminals interpret and execute autonomously.
    """
    goal: str  # What we want to achieve
    context: str  # Background information
    suggested_terminals: list[TerminalID]  # Which terminals might handle this
    priority: str = "medium"
    quality_threshold: float = 0.8  # Minimum quality to consider complete


@dataclass
class TaskPlan:
    """
    Complete plan for executing a high-level task.

    Supports both legacy task-based planning and organic intent-based planning.
    """

    original_task: str
    summary: str
    tasks: list[PlannedTask]
    execution_order: list[str]

    # Organic Flow additions (v2.0)
    intents: list[Intent] = field(default_factory=list)  # High-level intents
    planning_mode: str = "legacy"  # "legacy" or "organic"


# New parallel-first planner prompt
PLANNER_PROMPT = '''You are a PARALLEL task planner. All 5 terminals work SIMULTANEOUSLY.

## Terminals (All Start Immediately)

T1 - UI/UX: Creates UI with mock data, defines interfaces for T2
T2 - Features: Builds architecture, exposes APIs, writes unit tests
T3 - Docs: Creates documentation progressively
T4 - Strategy: Provides direction fast (2 min), then detailed docs
T5 - QA/Testing: Validates code, runs tests, verifies builds, checks quality

## CRITICAL: Parallel Execution Rules

1. ALL terminals start in Phase 1 - NO BLOCKING DEPENDENCIES
2. Terminals work with assumptions and mock data
3. Phase 2 tasks refine/integrate after initial work
4. Phase 3 is final testing, validation, and polish

## Task to Plan

{task}
{project_context}

## Output Format

Return ONLY JSON (no markdown):

{{
  "summary": "Brief plan summary",
  "tasks": [
    {{
      "title": "Task title",
      "description": "Detailed description with specific deliverables",
      "terminal": "t1|t2|t3|t4|t5",
      "priority": "critical|high|medium|low",
      "phase": 1,
      "dependencies": []
    }}
  ],
  "execution_order": ["task1", "task2"]
}}

## Required Task Structure

PHASE 0 (Planning & Contracts - First 2-5 minutes):
- T4: "Broadcast MVP scope and direction" (priority: critical, phase: 0)
- T1: "Define interface contracts" (priority: critical, phase: 0)
- T5: "Setup monitoring infrastructure" (priority: high, phase: 0)

PHASE 1 (Parallel Build - All terminals start immediately):
- T2: "Build core architecture and models" (priority: critical, phase: 1)
- T1: "Create UI components with mock data" (priority: critical, phase: 1)
- T3: "Create documentation structure" (priority: high, phase: 1)

PHASE 2 (Integration - after Phase 1):
- T2: "Integrate with T1's interface contracts" (phase: 2)
- T1: "Connect UI to T2's real APIs" (phase: 2)

PHASE 3 (Final - testing, validation, polish):
- T5: "Run all tests and verify build" (priority: critical, phase: 3)
- T5: "Validate output quality and completeness" (priority: high, phase: 3)
- T1: "Verify UI compilation and previews" (phase: 3)
- T3: "Finalize documentation" (phase: 3)

Return 8-14 tasks covering all phases. JSON only.'''


PLANNER_PROMPT_WITH_PROJECT = '''You are a PARALLEL task planner for an EXISTING PROJECT.

## Terminals (All Start Immediately)

T1 - UI/UX: Creates UI with mock data, defines interfaces for T2
T2 - Features: Builds architecture, exposes APIs, writes unit tests
T3 - Docs: Updates documentation progressively
T4 - Strategy: Provides direction fast, refines based on codebase
T5 - QA/Testing: Validates code, runs tests, verifies builds, checks quality

## CRITICAL: Parallel Execution Rules

1. Phase 0 tasks run first (2-5 minutes) - planning and contracts
2. ALL terminals start in Phase 1 after Phase 0 - NO BLOCKING DEPENDENCIES
3. Terminals read existing code and work with it
4. Phase 2 tasks integrate new code with existing
5. Phase 3 is final testing and validation by T5

## Existing Project

{project_context}

## Task to Plan

{task}

## Guidelines for Existing Projects

1. RESPECT existing architecture - enhance, don't replace
2. Read existing files before modifying
3. Follow existing patterns and naming conventions
4. Update existing tests, don't just add new ones
5. T5 MUST validate all changes compile and tests pass

## Output Format

Return ONLY JSON (no markdown):

{{
  "summary": "Brief plan summary",
  "tasks": [
    {{
      "title": "Task title",
      "description": "Specific changes to make, files to modify",
      "terminal": "t1|t2|t3|t4|t5",
      "priority": "critical|high|medium|low",
      "phase": 0,
      "dependencies": [],
      "required_subagents": ["subagent-name"]
    }}
  ],
  "execution_order": ["task1", "task2"]
}}

IMPORTANT: Always include Phase 0 tasks and at least one T5 task in Phase 3 to validate the build.

Return 6-12 tasks. JSON only.'''


class Planner:
    """
    Task planner supporting both legacy and organic flow models.

    LEGACY MODEL:
    - Parallel-first: All terminals start immediately
    - Dependencies are soft (informational), not blocking
    - Phase-gated execution (0-3)

    ORGANIC FLOW MODEL (v2.0):
    - Intent-based: Broadcast goals, let terminals interpret
    - Quality is a gradient (0.0-1.0)
    - Flow state tracks health, not phase progression
    """

    def __init__(self, config: Config, use_organic_model: bool = False):
        self.config = config
        self.use_organic_model = use_organic_model

    def plan(self, task: str, project_context: str = "") -> TaskPlan:
        """
        Create an execution plan.

        LEGACY MODEL:
        All Phase 1 tasks start immediately.
        Phase 2 starts when any Phase 1 task completes.
        Phase 3 starts when all Phase 2 tasks complete.

        ORGANIC FLOW MODEL (v2.0):
        Broadcasts intents and lets terminals self-organize.
        Quality gradients replace binary completion.
        """
        # If organic model enabled, use intent-based planning
        if self.use_organic_model:
            return self._plan_organic(task, project_context)

        # Legacy planning
        if project_context:
            prompt = PLANNER_PROMPT_WITH_PROJECT.format(
                task=task,
                project_context=project_context,
            )
        else:
            prompt = PLANNER_PROMPT.format(task=task, project_context="")

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
            print("[Planner] Claude timed out, using parallel fallback plan")
            return self._parallel_fallback_plan(task)
        except FileNotFoundError:
            print("[Planner] Claude CLI not found, using parallel fallback plan")
            return self._parallel_fallback_plan(task)
        except Exception as e:
            print(f"[Planner] Error running Claude: {e}, using parallel fallback plan")
            return self._parallel_fallback_plan(task)

        plan_data = self._extract_json(output)

        if not plan_data:
            print(f"[Planner] Could not parse JSON, using parallel fallback plan")
            return self._parallel_fallback_plan(task)

        planned_tasks = []
        for task_data in plan_data.get("tasks", []):
            terminal = task_data.get("terminal", "t2").lower()
            if terminal not in ["t1", "t2", "t3", "t4", "t5"]:
                terminal = "t2"

            # Skip T5 tasks if testing is disabled
            if terminal == "t5" and self.config.disable_testing:
                continue

            planned_tasks.append(PlannedTask(
                title=task_data.get("title", "Untitled"),
                description=task_data.get("description", ""),
                terminal=terminal,
                priority=task_data.get("priority", "medium"),
                dependencies=task_data.get("dependencies", []),
                phase=task_data.get("phase", 1),
                required_subagents=task_data.get("required_subagents", []),
            ))

        if not planned_tasks:
            return self._parallel_fallback_plan(task)

        # Sort by phase, then priority
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        planned_tasks.sort(key=lambda t: (t.phase, priority_order.get(t.priority, 2)))

        return TaskPlan(
            original_task=task,
            summary=plan_data.get("summary", "Parallel execution plan created"),
            tasks=planned_tasks,
            execution_order=[t.title for t in planned_tasks],
            planning_mode="legacy",
        )

    def _plan_organic(self, task: str, project_context: str = "") -> TaskPlan:
        """
        Create an organic flow execution plan (v2.0).

        Instead of rigid task assignments with phases, this:
        1. Broadcasts high-level intents
        2. Lets terminals interpret and self-organize
        3. Uses quality gradients instead of binary completion
        4. Tracks flow state instead of phase progression
        """
        task_lower = task.lower()
        is_mobile = any(w in task_lower for w in ["ios", "app", "mobile", "iphone", "ipad", "swiftui"])

        # Create high-level intents instead of rigid tasks
        intents = [
            Intent(
                goal="Establish project direction and scope",
                context=f"Task: {task}",
                suggested_terminals=["t4"],
                priority="critical",
                quality_threshold=0.9,
            ),
            Intent(
                goal="Create user interface with clear data contracts",
                context=f"Build UI for: {task}. Define what data you need from backend.",
                suggested_terminals=["t1"],
                priority="critical",
                quality_threshold=0.8,
            ),
            Intent(
                goal="Build core architecture and data services",
                context=f"Implement backend for: {task}. Check T1's contracts.",
                suggested_terminals=["t2"],
                priority="critical",
                quality_threshold=0.8,
            ),
            Intent(
                goal="Document the project progressively",
                context=f"Create docs for: {task}. Update as work progresses.",
                suggested_terminals=["t3"],
                priority="medium",
                quality_threshold=0.7,
            ),
        ]

        if not self.config.disable_testing:
            intents.append(Intent(
                goal="Validate quality and ensure tests pass",
                context=f"QA for: {task}. Monitor builds and test results.",
                suggested_terminals=["t5"],
                priority="high",
                quality_threshold=0.9,
            ))

        # Convert intents to tasks for backward compatibility
        # In organic model, these are more like "suggested work" than rigid assignments
        planned_tasks = []

        for i, intent in enumerate(intents):
            terminal = intent.suggested_terminals[0] if intent.suggested_terminals else "t2"
            planned_tasks.append(PlannedTask(
                title=intent.goal,
                description=intent.context,
                terminal=terminal,
                priority=intent.priority,
                dependencies=[],  # No rigid dependencies in organic model
                phase=1,  # All work starts in "flow" state
                intent=intent.goal,
                quality_target=intent.quality_threshold,
                required_subagents=self._suggest_subagents(intent.goal, is_mobile),
            ))

        return TaskPlan(
            original_task=task,
            summary=f"Organic flow plan: {len(intents)} intents broadcast",
            tasks=planned_tasks,
            execution_order=[t.title for t in planned_tasks],
            intents=intents,
            planning_mode="organic",
        )

    def _suggest_subagents(self, goal: str, is_mobile: bool) -> list[str]:
        """Suggest subagents based on the intent goal."""
        goal_lower = goal.lower()

        if "ui" in goal_lower or "interface" in goal_lower:
            return ["swiftui-crafter"] if is_mobile else ["react-crafter"]
        if "architecture" in goal_lower or "backend" in goal_lower:
            return ["swift-architect"] if is_mobile else ["node-architect"]
        if "document" in goal_lower:
            return ["tech-writer"]
        if "direction" in goal_lower or "scope" in goal_lower:
            return ["product-thinker"]
        if "quality" in goal_lower or "test" in goal_lower:
            return ["testing-genius"]

        return []

    def _extract_json(self, text: str) -> dict | None:
        """Extract JSON object from text."""
        if not text:
            return None

        text = re.sub(r'```json\s*', '', text)
        text = re.sub(r'```\s*', '', text)
        text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

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

    def _parallel_fallback_plan(self, task: str) -> TaskPlan:
        """
        Fallback plan that ensures parallel execution.

        Phase 0 runs first (planning & contracts).
        All Phase 1 tasks have NO dependencies - they all start immediately.
        """
        task_lower = task.lower()
        is_mobile = any(w in task_lower for w in ["ios", "app", "mobile", "iphone", "ipad", "swiftui"])

        tasks = []

        # PHASE 0: Planning & Contracts
        tasks.append(PlannedTask(
            title="Broadcast MVP scope and direction",
            description=f"""Immediately analyze and broadcast within 2 minutes:
1. MVP scope (3-5 core features maximum)
2. Visual direction for T1 (style, colors, vibe)
3. Technical direction for T2 (architecture approach)
4. Marketing angle for T3

Write to .orchestra/messages/broadcast.md so all terminals can read it.

Task context: {task}""",
            terminal="t4",
            priority="critical",
            dependencies=[],
            phase=0,
            required_subagents=["product-thinker"],
        ))

        tasks.append(PlannedTask(
            title="Define interface contracts",
            description=f"""Create interface contracts in .orchestra/contracts/:
1. Identify key data models the UI will need
2. Document expected interfaces/APIs
3. Create contract files for T2 to implement

Example contract: UserDisplayData.json
{{
    "name": "UserDisplayData",
    "defined_by": "t1",
    "status": "proposed",
    "definition": {{"fields": ["id", "name", "email"]}}
}}

Task context: {task}""",
            terminal="t1",
            priority="critical",
            dependencies=[],
            phase=0,
            required_subagents=["swiftui-crafter"],
        ))

        if not self.config.disable_testing:
            tasks.append(PlannedTask(
                title="Setup QA monitoring infrastructure",
                description="""Setup monitoring in .orchestra/qa/:
1. Create directory structure
2. Initialize build tracking
3. Setup contract monitoring
4. Prepare for continuous validation

See templates/terminal_prompts/t5_qa.md for Phase 0 instructions.""",
                terminal="t5",
                priority="high",
                dependencies=[],
                phase=0,
                required_subagents=["testing-genius"],
            ))

        # PHASE 1: All start immediately, NO dependencies
        tasks.append(PlannedTask(
            title="Build core architecture and data models",
            description=f"""Start immediately with architecture:
1. Create data models based on task requirements
2. Build service layer with clear public APIs
3. Set up persistence (SwiftData/CoreData for iOS, or appropriate)
4. Write unit tests for core logic
5. Document all public interfaces for T1

Don't wait for T4 - infer requirements from task description.
If T1 has created interface contracts, match them.

Task context: {task}""",
            terminal="t2",
            priority="critical",
            dependencies=[],  # NO dependencies
            phase=1,
            required_subagents=["swift-architect"] if is_mobile else ["node-architect"],
        ))

        tasks.append(PlannedTask(
            title="Create UI components with mock data",
            description=f"""Start immediately with UI:
1. Define visual design system (colors, typography, spacing)
2. Create all main screens/views with placeholder data
3. Implement navigation structure
4. Add loading states and error states
5. Document interface contracts (what data each view expects)

Don't wait for T2 - use mock data and document assumptions.
T2 will implement interfaces matching your contracts.

Task context: {task}""",
            terminal="t1",
            priority="critical",
            dependencies=[],  # NO dependencies
            phase=1,
            required_subagents=["swiftui-crafter"] if is_mobile else ["react-crafter"],
        ))

        tasks.append(PlannedTask(
            title="Create documentation structure",
            description=f"""Start immediately with docs:
1. Create README.md skeleton
2. Set up docs/ folder structure
3. Draft installation instructions
4. Create CHANGELOG.md
{"5. Draft App Store description" if is_mobile else "5. Draft API documentation structure"}

Fill in what you can, mark placeholders for what you can't.

Task context: {task}""",
            terminal="t3",
            priority="high",
            dependencies=[],  # NO dependencies
            phase=1,
            required_subagents=["tech-writer"],
        ))

        # PHASE 2: Integration (soft dependencies)
        tasks.append(PlannedTask(
            title="Integrate T1 interfaces with T2 implementations",
            description="""Check T1's interface contracts and ensure T2's models match:
1. Read .orchestra/reports/t1/ for interface expectations
2. Adapt models/services if needed to match T1's contracts
3. Replace any mock implementations with real ones
4. Ensure all T1-facing APIs are complete""",
            terminal="t2",
            priority="high",
            dependencies=["Build core architecture and data models"],
            phase=2,
            required_subagents=["swift-architect"] if is_mobile else ["node-architect"],
        ))

        tasks.append(PlannedTask(
            title="Connect UI to real data services",
            description="""Replace mock data with T2's real implementations:
1. Read .orchestra/reports/t2/ for available APIs
2. Wire UI components to actual services
3. Test all data flows work correctly
4. Verify loading and error states with real scenarios""",
            terminal="t1",
            priority="high",
            dependencies=["Create UI components with mock data"],
            phase=2,
            required_subagents=["swiftui-crafter"] if is_mobile else ["react-crafter"],
        ))

        # PHASE 3: Testing and finalization
        if not self.config.disable_testing:
            tasks.append(PlannedTask(
                title="Run all tests and verify build",
                description="""Final verification:
1. Run swift build / npm run build
2. Run swift test / npm test
3. Fix any compilation errors
4. Fix any failing tests
5. Ensure no warnings in production code

Do NOT mark complete until all tests pass.""",
                terminal="t5",
                priority="critical",
                dependencies=["Integrate T1 interfaces with T2 implementations"],
                phase=3,
                required_subagents=["testing-genius"],
            ))

            tasks.append(PlannedTask(
                title="Validate output quality and completeness",
                description="""Quality validation:
1. Verify all contract requirements met
2. Check code quality metrics
3. Validate documentation completeness
4. Ensure all phase objectives achieved

Do NOT mark complete until validation passes.""",
                terminal="t5",
                priority="high",
                dependencies=["Run all tests and verify build"],
                phase=3,
                required_subagents=["testing-genius"],
            ))

        tasks.append(PlannedTask(
            title="Verify UI compilation and previews",
            description="""Final UI verification:
1. Ensure all views compile without errors
2. Verify SwiftUI previews work (if applicable)
3. Check for any layout issues
4. Verify all navigation paths work

Do NOT mark complete until build succeeds.""",
            terminal="t1",
            priority="high",
            dependencies=["Connect UI to real data services"],
            phase=3,
            required_subagents=["swiftui-crafter"] if is_mobile else ["react-crafter"],
        ))

        tasks.append(PlannedTask(
            title="Finalize all documentation",
            description="""Complete documentation:
1. Fill in all placeholder sections
2. Add code examples from T2's final APIs
3. Verify all links work
4. Ensure README accurately reflects the final product""",
            terminal="t3",
            priority="medium",
            dependencies=["Create documentation structure"],
            phase=3,
            required_subagents=["tech-writer"],
        ))

        return TaskPlan(
            original_task=task,
            summary=f"4-phase execution plan: Phase 0 (planning), Phase 1 (parallel build), Phase 2 (integration), Phase 3 (testing)",
            tasks=tasks,
            execution_order=[t.title for t in tasks],
        )


def quick_plan(task: str, project_context: str = "") -> TaskPlan:
    """Convenience function for quick planning."""
    config = Config()
    planner = Planner(config)
    return planner.plan(task, project_context=project_context)
