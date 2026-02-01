# Archon Architecture

> Technical deep-dive into the Archon multi-agent orchestration system.

---

## System Overview

Archon is built on a **hub-and-spoke architecture** with **3-phase parallel execution**. A central Python orchestrator coordinates 4 specialized Claude Code terminals that work **simultaneously** from the start, communicating via interface contracts.

### Key Innovation: Phase-Based Parallel Execution

Unlike sequential systems, Archon runs all terminals immediately:

```
PHASE 1: BUILD (All terminals start immediately - NO blocking)
  T1 ──→ UI with mock data + interface contracts
  T2 ──→ Architecture, models, services + tests
  T3 ──→ Documentation structure
  T4 ──→ MVP scope (broadcasts in 2 min)
              ↓
PHASE 2: INTEGRATE (When Phase 1 completes)
  T1 ──→ Connects UI to T2's real APIs
  T2 ──→ Matches T1's interface contracts
              ↓
PHASE 3: TEST & VERIFY (Final)
  T1 ──→ swift build verification
  T2 ──→ swift test, fix failures
  T3 ──→ Finalize docs
              ↓
        ✅ Working Software
```

Each terminal operates as an independent subprocess with its own context and specialization.

```
                    ┌─────────────────────────────────────────┐
                    │           ORCHESTRATOR (Hub)            │
                    │                                         │
                    │  ┌─────────┐  ┌──────────┐  ┌────────┐  │
                    │  │ Planner │  │TaskQueue │  │ Logger │  │
                    │  └────┬────┘  └────┬─────┘  └────┬───┘  │
                    │       │            │             │      │
                    │  ┌────┴────────────┴─────────────┴───┐  │
                    │  │           Message Bus             │  │
                    │  └───────────────┬───────────────────┘  │
                    └──────────────────┼──────────────────────┘
                                       │
           ┌───────────────┬───────────┴───────────┬───────────────┐
           │               │                       │               │
           ▼               ▼                       ▼               ▼
    ┌─────────────┐ ┌─────────────┐       ┌─────────────┐ ┌─────────────┐
    │ Terminal T1 │ │ Terminal T2 │       │ Terminal T3 │ │ Terminal T4 │
    │   UI/UX     │ │  Features   │       │    Docs     │ │  Strategy   │
    │             │ │             │       │             │ │             │
    │ 4 subagents │ │ 6 subagents │       │ 2 subagents │ │ 2 subagents │
    └──────┬──────┘ └──────┬──────┘       └──────┬──────┘ └──────┬──────┘
           │               │                     │               │
           └───────────────┴──────────┬──────────┴───────────────┘
                                      │
                                      ▼
                           ┌─────────────────────┐
                           │    .orchestra/      │
                           │   (File System)     │
                           │                     │
                           │ messages/ tasks/    │
                           │ artifacts/ events/  │
                           └─────────────────────┘
```

---

## Core Components

### 1. Orchestrator (`orchestrator.py`)

The central coordinator managing the entire execution lifecycle.

**Responsibilities:**
- Initialize and configure terminals
- Receive high-level tasks from user
- Invoke Planner for task decomposition
- Distribute tasks via TaskQueue
- Monitor terminal progress
- Handle retries and failures
- Maintain execution state

**Key Class: `Orchestrator`**

```python
class Orchestrator:
    def __init__(self, config: Config):
        self.config = config
        self.planner = Planner(config)
        self.task_queue = TaskQueue(config)
        self.message_bus = MessageBus(config)
        self.terminals: dict[TerminalID, Terminal] = {}
        self.logger = EventLogger(config)

    async def run(self, task: str) -> ExecutionResult:
        """Main execution loop."""
        # 1. Plan the task
        plan = await self.planner.create_plan(task)

        # 2. Add tasks to queue
        for subtask in plan.tasks:
            self.task_queue.add(subtask)

        # 3. Execute until complete
        while not self.task_queue.is_complete():
            await self._execute_ready_tasks()
            await self._check_terminal_status()
            await asyncio.sleep(POLL_INTERVAL)

        return self._compile_results()
```

**State Machine:**

```
IDLE ──start()──▶ PLANNING ──plan_ready──▶ EXECUTING
                                               │
                        ┌──────────────────────┤
                        │                      │
                        ▼                      ▼
                   RETRYING              COMPLETED
                        │                      │
                        └──────▶ FAILED ◀──────┘
```

---

### 2. Planner (`planner.py`)

Decomposes high-level tasks into executable subtasks.

**Strategy:**
1. Send task to Claude with planning prompt
2. Receive JSON plan with subtasks
3. Assign terminals based on keywords
4. Define dependencies between tasks
5. Return structured plan

**Plan Output Format:**

```python
@dataclass
class Plan:
    summary: str
    tasks: list[PlannedTask]
    execution_order: list[str]

@dataclass
class PlannedTask:
    id: str
    title: str
    description: str
    terminal: TerminalID
    priority: Priority
    dependencies: list[str]
```

**Keyword Routing Algorithm:**

```python
TERMINAL_KEYWORDS = {
    "t1": ["ui", "view", "component", "style", "design", "layout", "button"],
    "t2": ["api", "database", "model", "service", "auth", "logic", "backend"],
    "t3": ["readme", "docs", "documentation", "guide", "tutorial", "changelog"],
    "t4": ["product", "feature", "mvp", "pricing", "strategy", "roadmap"]
}

def route_task(description: str) -> TerminalID:
    scores = {t: 0 for t in TERMINAL_KEYWORDS}
    words = description.lower().split()

    for terminal, keywords in TERMINAL_KEYWORDS.items():
        for keyword in keywords:
            if keyword in words:
                scores[terminal] += 1

    return max(scores, key=scores.get) or "t2"  # Default to T2
```

---

### 3. Task Queue (`task_queue.py`)

Manages task lifecycle and persistence.

**Task States:**

```
                    ┌─────────┐
                    │ PENDING │
                    └────┬────┘
                         │
                    assign_to_terminal()
                         │
                         ▼
                  ┌─────────────┐
                  │ IN_PROGRESS │
                  └──────┬──────┘
                         │
           ┌─────────────┼─────────────┐
           │             │             │
      complete()     fail()       timeout()
           │             │             │
           ▼             ▼             ▼
    ┌───────────┐  ┌─────────┐  ┌─────────────┐
    │ COMPLETED │  │ FAILED  │  │   RETRYING  │
    └───────────┘  └─────────┘  └─────────────┘
```

**Phase-Based Execution:**

Tasks now have a `phase` field (1, 2, or 3). Phase 1 tasks have NO blocking dependencies - they all start immediately:

```python
def is_ready(self, completed_task_ids: set[str], current_phase: int = 1) -> bool:
    """Check if task is ready to execute."""
    # Phase 1 tasks are ALWAYS ready - parallel execution
    if self.phase == 1:
        return True

    # Phase 2+ tasks wait for their phase
    if self.phase > current_phase:
        return False

    # Once phase is reached, check soft dependencies
    return all(dep in completed_task_ids for dep in self.dependencies)

def get_current_phase(self) -> int:
    """Determine execution phase based on completed tasks."""
    # Phase 2 when ALL Phase 1 tasks complete
    # Phase 3 when ALL Phase 2 tasks complete
    ...
```

**Persistence:**

Tasks are persisted to JSON files for crash recovery:
- `.orchestra/tasks/pending.json`
- `.orchestra/tasks/in_progress.json`
- `.orchestra/tasks/completed.json`

---

### 4. Message Bus (`message_bus.py`)

Enables communication between terminals via filesystem.

**Why File-Based IPC?**
- **Inspectable**: Messages are human-readable markdown
- **Debuggable**: Easy to trace communication flow
- **Persistent**: Survives crashes and restarts
- **Simple**: No socket management or serialization

**Message Types:**

| Type | Use Case |
|------|----------|
| `request` | Ask another terminal for help |
| `response` | Reply to a request |
| `broadcast` | Announce to all terminals |
| `status` | Progress update |
| `artifact` | Share generated file |

**Message Format (Markdown):**

```markdown
---
## Message: msg_20250131180000_0001
**From:** t2
**To:** t1
**Type:** artifact
**Time:** 2025-01-31T18:00:00.000000

The data models are ready. Please use these for the UI components.

**Artifact:** `/path/to/Models.swift`
**Description:** SwiftData models for habits, categories, and reminders
---
```

**Polling Mechanism:**

Each terminal polls its inbox file every 2 seconds:

```python
async def poll_inbox(self, terminal_id: TerminalID):
    inbox_path = self.config.messages_dir / f"{terminal_id}_inbox.md"
    while True:
        messages = self._parse_inbox(inbox_path)
        for msg in messages:
            if not msg.read:
                await self._handle_message(msg)
                self._mark_read(msg)
        await asyncio.sleep(2)
```

---

### 5. Terminal (`terminal.py`)

Executes tasks via Claude Code CLI subprocess.

**Execution Model:**

```python
class Terminal:
    def __init__(self, config: TerminalConfig):
        self.id = config.id
        self.role = config.role
        self.subagents = config.subagents
        self.state = TerminalState.IDLE

    async def execute(self, task: Task) -> TerminalOutput:
        self.state = TerminalState.BUSY

        # Build prompt with system instructions and task
        prompt = self._build_prompt(task)

        # Execute via Claude Code CLI
        result = await self._run_claude(prompt)

        self.state = TerminalState.IDLE
        return result

    async def _run_claude(self, prompt: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            "claude", "--print", "-p", prompt,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        return stdout.decode()
```

**Subprocess Isolation:**

Each terminal runs in its own subprocess with:
- Separate context window
- Isolated tool access
- Independent error handling
- Own retry logic

---

### 6. Dashboard (`dashboard.py`)

Real-time web UI built with FastAPI.

**Endpoints:**

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Serve HTML dashboard |
| `/api/status` | GET | Orchestrator status |
| `/api/tasks` | GET | All tasks with status |
| `/api/tasks/{id}` | GET | Single task details |
| `/api/messages` | GET | Terminal inboxes |
| `/api/terminals` | GET | Terminal configurations |
| `/api/artifacts` | GET | Generated files |
| `/api/events` | GET | Recent events |
| `/ws` | WS | Real-time updates |

**WebSocket Protocol:**

```javascript
// Client connects
ws = new WebSocket("ws://localhost:8420/ws");

// Server pushes updates every 2 seconds
ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    updateUI(data);
};

// Data format
{
    "status": "executing",
    "terminals": {
        "t1": { "state": "busy", "current_task": "..." },
        ...
    },
    "tasks": { "pending": 2, "in_progress": 1, "completed": 3 },
    "recent_events": [...]
}
```

---

## Data Flow

### Task Execution Flow (3-Phase Parallel)

```
1. User submits: "Create habit tracker app"
                    │
                    ▼
2. Orchestrator receives task
                    │
                    ▼
3. Planner creates PARALLEL plan:
   PHASE 1 (no dependencies - all start immediately):
   ├── T4: Define MVP scope (broadcasts direction in 2 min)
   ├── T2: Build architecture and models (with tests)
   ├── T1: Create UI with mock data (+ interface contracts)
   └── T3: Create documentation structure

   PHASE 2 (integration):
   ├── T1: Connect UI to T2's real APIs
   └── T2: Match T1's interface contracts

   PHASE 3 (testing):
   ├── T1: Verify UI compilation
   ├── T2: Run all tests, fix failures
   └── T3: Finalize documentation
                    │
                    ▼
4. TaskQueue adds tasks with PHASES (not blocking dependencies)
                    │
                    ▼
5. PHASE 1: ALL terminals start immediately
   ├── T4 broadcasts MVP direction (within 2 min)
   ├── T2 builds foundation with tests
   ├── T1 creates UI + documents interface contracts
   └── T3 creates doc structure
   (All working in parallel, reading each other's reports)
                    │
                    ▼
6. PHASE 2: Integration (when Phase 1 completes)
   ├── T1 reads T2's APIs from .orchestra/reports/t2/
   ├── T2 reads T1's contracts from .orchestra/reports/t1/
   └── Both adapt to match each other
                    │
                    ▼
7. PHASE 3: Testing (when Phase 2 completes)
   ├── T1 runs: swift build
   ├── T2 runs: swift build && swift test
   └── Any failures trigger auto-fix
                    │
                    ▼
8. Orchestrator compiles results
   └── Returns ExecutionResult (verified & tested)
```

---

## Subagent System

### Architecture

Each subagent is a specialized prompt configuration:

```yaml
# .claude/agents/swiftui-crafter.yml
name: swiftui-crafter
model: opus           # Uses Claude Opus
color: orange         # CLI color coding
tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Bash

description: |
  Expert SwiftUI developer specializing in iOS/macOS UI.

prompt: |
  You are a senior SwiftUI specialist with expertise in:
  - Modern SwiftUI (iOS 17+) views and modifiers
  - State management (@State, @Binding, @Observable)
  - Animations and transitions
  - Accessibility (VoiceOver, Dynamic Type)
  - Design system integration

  Code Standards:
  - Use Swift 5.9+ features
  - Prefer composition over inheritance
  - Document public APIs with ///
  ...
```

### Model Assignment

| Model | Use Case | Subagents |
|-------|----------|-----------|
| **Opus** | Complex reasoning, architecture | swift-architect, node-architect, python-architect, ml-engineer, product-thinker, monetization-expert, swiftui-crafter, react-crafter |
| **Sonnet** | Focused tasks, documentation | html-stylist, design-system, swiftdata-expert, database-expert, tech-writer, marketing-strategist |

### Invocation Pattern

```python
# Terminal invokes appropriate subagent
def select_subagent(task: Task) -> str:
    """Select best subagent based on task content."""
    keywords = {
        "swiftui-crafter": ["swiftui", "view", "ios", "component"],
        "swift-architect": ["architecture", "mvvm", "structure"],
        ...
    }

    for agent, words in keywords.items():
        if any(w in task.description.lower() for w in words):
            return agent

    return self.default_agent
```

---

## File System Layout

### Runtime State (`.orchestra/`)

```
.orchestra/
├── messages/
│   ├── t1_inbox.md          # T1's incoming messages
│   ├── t2_inbox.md          # T2's incoming messages
│   ├── t3_inbox.md          # T3's incoming messages
│   ├── t4_inbox.md          # T4's incoming messages
│   └── broadcast.md         # All-terminal broadcasts
│
├── tasks/
│   ├── pending.json         # Tasks waiting to execute
│   ├── in_progress.json     # Currently executing tasks
│   └── completed.json       # Finished tasks
│
├── artifacts/
│   ├── habit-tracker-prd.md
│   ├── architecture.md
│   └── ...
│
├── status.json              # Current orchestrator state
├── events.json              # Event log (last 100)
└── last_plan.json           # Most recent plan
```

### Configuration (`.claude/`)

```
.claude/
├── CLAUDE.md                # Project instructions
├── settings.json            # Permissions, hooks
├── settings.local.json      # Local overrides (gitignored)
└── agents/
    ├── swiftui-crafter.yml
    ├── react-crafter.yml
    ├── html-stylist.yml
    ├── design-system.yml
    ├── swift-architect.yml
    ├── node-architect.yml
    ├── python-architect.yml
    ├── swiftdata-expert.yml
    ├── database-expert.yml
    ├── ml-engineer.yml
    ├── tech-writer.yml
    ├── marketing-strategist.yml
    ├── product-thinker.yml
    └── monetization-expert.yml
```

---

## Error Handling

### Retry Strategy

```python
MAX_RETRIES = 2
RETRY_DELAYS = [5, 15, 30]  # seconds

async def execute_with_retry(self, task: Task) -> TerminalOutput:
    for attempt in range(MAX_RETRIES + 1):
        try:
            result = await self.execute(task)
            if self._is_successful(result):
                return result
        except Exception as e:
            self.logger.log_error(task, e, attempt)

        if attempt < MAX_RETRIES:
            await asyncio.sleep(RETRY_DELAYS[attempt])

    return TerminalOutput(error=True, message="Max retries exceeded")
```

### Failure Modes

| Failure | Detection | Recovery |
|---------|-----------|----------|
| Timeout | No output after N seconds | Retry with increased timeout |
| CLI Error | Non-zero exit code | Retry with simplified prompt |
| Parse Error | Invalid output format | Retry with explicit format instructions |
| Dependency Failure | Upstream task failed | Skip or retry upstream first |

### Graceful Shutdown

```python
def setup_signal_handlers(self):
    signal.signal(signal.SIGINT, self._handle_shutdown)
    signal.signal(signal.SIGTERM, self._handle_shutdown)

def _handle_shutdown(self, signum, frame):
    self.logger.log("Graceful shutdown initiated")

    # Stop accepting new tasks
    self.task_queue.pause()

    # Wait for in-progress tasks
    for terminal in self.terminals.values():
        if terminal.state == TerminalState.BUSY:
            terminal.wait_current_task()

    # Persist state
    self.task_queue.save()
    self.message_bus.save()

    sys.exit(0)
```

---

## Performance Considerations

### Parallelism

- Default: 4 terminals (T1-T4)
- Configurable: 1-10 parallel terminals
- Subagent parallelism: Up to 10 per terminal

### Bottlenecks

| Component | Bottleneck | Mitigation |
|-----------|------------|------------|
| Planner | Claude API latency | Cache plans for similar tasks |
| File I/O | Message polling | Batched reads, 2s intervals |
| Terminal | Subprocess overhead | Reuse processes when possible |
| Dashboard | WebSocket broadcast | Throttle updates to 2s |

### Memory Management

- Event log limited to 100 entries
- Artifacts referenced by path (not loaded in memory)
- Task results summarized after completion

---

## Security Model

### Sandbox Boundaries

- Terminals run in isolated subprocesses
- Each terminal has defined tool access
- No direct network access (except via tools)
- File access limited to project directory

### Denied Operations

```json
{
  "permissions": {
    "deny": [
      "Read .env files",
      "Execute rm -rf",
      "Access credentials",
      "Modify system files"
    ]
  }
}
```

---

## Extensibility

### Adding a New Subagent

1. Create YAML definition in `.claude/agents/`
2. Define model, tools, and system prompt
3. Register in appropriate terminal configuration
4. Update routing keywords

### Custom Terminal Roles

1. Create new terminal prompt in `templates/terminal_prompts/`
2. Define role-specific keywords
3. Assign subagents to terminal
4. Update config.py with new TerminalConfig

### Plugin System (Roadmap)

Future support for:
- Custom tool providers
- External API integrations
- Custom planning strategies
- Third-party subagent libraries

---

## References

- [README](../README.md) - Quick start guide
- [API Reference](./API_REFERENCE.md) - Internal API documentation
- [Design Decisions](./DESIGN_DECISIONS.md) - Why we built it this way
- [Setup Guide](./SETUP.md) - Installation instructions
