# Archon API Reference

> Internal API documentation for the Archon orchestrator modules.

---

## Table of Contents

- [Orchestrator](#orchestrator)
- [Planner](#planner)
- [TaskQueue](#taskqueue)
- [MessageBus](#messagebus)
- [Terminal](#terminal)
- [Config](#config)
- [Logger](#logger)
- [Dashboard](#dashboard)
- [Data Types](#data-types)

---

## Orchestrator

**Module:** `orchestrator/orchestrator.py`

Central coordinator for multi-terminal task execution.

### Class: `Orchestrator`

```python
class Orchestrator:
    """Main orchestration engine for multi-agent task execution."""
```

#### Constructor

```python
def __init__(
    self,
    config: Config,
    dry_run: bool = False,
    verbose: bool = False
) -> None
```

**Parameters:**
- `config`: Configuration object with paths and terminal settings
- `dry_run`: If True, plan tasks but don't execute
- `verbose`: Enable detailed logging

#### Methods

##### `run`

```python
async def run(self, task: str) -> ExecutionResult
```

Execute a high-level task through the multi-terminal system.

**Parameters:**
- `task`: Natural language task description

**Returns:**
- `ExecutionResult` with status, artifacts, and terminal outputs

**Example:**
```python
orchestrator = Orchestrator(config)
result = await orchestrator.run("Create an iOS habit tracker app")
print(result.summary)
```

##### `run_continuous`

```python
async def run_continuous(self) -> None
```

Run in continuous mode, prompting for new tasks after each completion.

##### `stop`

```python
def stop(self) -> None
```

Gracefully shutdown all terminals and persist state.

---

## Planner

**Module:** `orchestrator/planner.py`

Task decomposition using Claude.

### Class: `Planner`

```python
class Planner:
    """Decomposes high-level tasks into executable subtasks."""
```

#### Constructor

```python
def __init__(self, config: Config) -> None
```

#### Methods

##### `create_plan`

```python
async def create_plan(self, task: str) -> Plan
```

Create an execution plan for a task.

**Parameters:**
- `task`: High-level task description

**Returns:**
- `Plan` object with subtasks and dependencies

**Example:**
```python
planner = Planner(config)
plan = await planner.create_plan("Build a REST API")
for task in plan.tasks:
    print(f"{task.terminal}: {task.title}")
```

##### `route_to_terminal`

```python
def route_to_terminal(self, description: str) -> TerminalID
```

Determine which terminal should handle a task based on keywords.

**Parameters:**
- `description`: Task description text

**Returns:**
- `TerminalID` (t1, t2, t3, or t4)

---

## TaskQueue

**Module:** `orchestrator/task_queue.py`

Work distribution and persistence.

### Class: `TaskQueue`

```python
class TaskQueue:
    """Manages task lifecycle with dependency resolution."""
```

#### Constructor

```python
def __init__(self, config: Config) -> None
```

#### Methods

##### `add`

```python
def add(self, task: Task) -> str
```

Add a new task to the queue.

**Parameters:**
- `task`: Task object to add

**Returns:**
- Task ID

##### `get_ready_tasks`

```python
def get_ready_tasks(self) -> list[Task]
```

Get tasks whose dependencies are all completed.

**Returns:**
- List of executable tasks

##### `assign`

```python
def assign(self, task_id: str, terminal: TerminalID) -> None
```

Assign a task to a terminal and mark as in_progress.

##### `complete`

```python
def complete(self, task_id: str, result: str) -> None
```

Mark a task as completed with its result.

##### `fail`

```python
def fail(self, task_id: str, error: str) -> None
```

Mark a task as failed with error message.

##### `is_complete`

```python
def is_complete(self) -> bool
```

Check if all tasks are completed.

**Returns:**
- True if no pending or in_progress tasks remain

##### `save`

```python
def save(self) -> None
```

Persist current state to JSON files.

##### `load`

```python
def load(self) -> None
```

Load state from JSON files.

---

## MessageBus

**Module:** `orchestrator/message_bus.py`

Inter-terminal communication.

### Class: `MessageBus`

```python
class MessageBus:
    """File-based message passing between terminals."""
```

#### Constructor

```python
def __init__(self, config: Config) -> None
```

#### Methods

##### `send`

```python
def send(
    self,
    sender: str,
    recipient: str,
    content: str,
    msg_type: MessageType = MessageType.REQUEST,
    metadata: dict | None = None
) -> str
```

Send a message to a terminal or broadcast.

**Parameters:**
- `sender`: Sender ID (terminal or "orchestrator")
- `recipient`: Recipient ID or "all" for broadcast
- `content`: Message content (markdown)
- `msg_type`: Type of message
- `metadata`: Optional additional data

**Returns:**
- Message ID

**Example:**
```python
bus = MessageBus(config)
bus.send(
    sender="t2",
    recipient="t1",
    content="Data models ready at /path/to/Models.swift",
    msg_type=MessageType.ARTIFACT,
    metadata={"path": "/path/to/Models.swift"}
)
```

##### `broadcast`

```python
def broadcast(
    self,
    sender: str,
    content: str,
    msg_type: MessageType = MessageType.BROADCAST
) -> str
```

Send a message to all terminals.

##### `read_inbox`

```python
def read_inbox(self, terminal_id: TerminalID) -> list[Message]
```

Read all messages in a terminal's inbox.

**Returns:**
- List of Message objects

##### `get_unread`

```python
def get_unread(self, terminal_id: TerminalID) -> list[Message]
```

Get only unread messages for a terminal.

##### `mark_read`

```python
def mark_read(self, message_id: str) -> None
```

Mark a message as read.

##### `clear_inbox`

```python
def clear_inbox(self, terminal_id: TerminalID) -> None
```

Clear all messages from a terminal's inbox.

---

## Terminal

**Module:** `orchestrator/terminal.py`

Task execution via Claude Code CLI.

### Class: `Terminal`

```python
class Terminal:
    """Executes tasks via Claude Code subprocess."""
```

#### Constructor

```python
def __init__(self, config: TerminalConfig) -> None
```

#### Properties

##### `state`

```python
@property
def state(self) -> TerminalState
```

Current terminal state (IDLE, BUSY, ERROR, STOPPED).

##### `current_task`

```python
@property
def current_task(self) -> Task | None
```

Currently executing task, if any.

#### Methods

##### `execute`

```python
async def execute(self, task: Task) -> TerminalOutput
```

Execute a task and return the output.

**Parameters:**
- `task`: Task to execute

**Returns:**
- `TerminalOutput` with content and status

##### `retry`

```python
async def retry(self, task: Task, attempt: int = 1) -> TerminalOutput
```

Retry a failed task with backoff.

**Parameters:**
- `task`: Task to retry
- `attempt`: Current attempt number

**Returns:**
- `TerminalOutput` with content and status

##### `stop`

```python
def stop(self) -> None
```

Stop the terminal and any running subprocess.

---

## Config

**Module:** `orchestrator/config.py`

Configuration management.

### Class: `Config`

```python
class Config:
    """Centralized configuration for the orchestrator."""
```

#### Constructor

```python
def __init__(self, base_dir: Path | None = None) -> None
```

**Parameters:**
- `base_dir`: Project root directory (defaults to cwd)

#### Properties

```python
@property
def base_dir(self) -> Path

@property
def orchestra_dir(self) -> Path

@property
def messages_dir(self) -> Path

@property
def tasks_dir(self) -> Path

@property
def artifacts_dir(self) -> Path

@property
def agents_dir(self) -> Path

@property
def templates_dir(self) -> Path
```

#### Methods

##### `get_terminal_config`

```python
def get_terminal_config(self, terminal_id: TerminalID) -> TerminalConfig
```

Get configuration for a specific terminal.

##### `get_all_terminals`

```python
def get_all_terminals(self) -> dict[TerminalID, TerminalConfig]
```

Get configurations for all terminals.

##### `ensure_directories`

```python
def ensure_directories(self) -> None
```

Create all required directories if they don't exist.

### Class: `TerminalConfig`

```python
@dataclass
class TerminalConfig:
    id: TerminalID
    role: str
    subagents: list[str]
    keywords: list[str]
    prompt_file: str
```

---

## Logger

**Module:** `orchestrator/logger.py`

Event logging for dashboard and debugging.

### Class: `EventLogger`

```python
class EventLogger:
    """Logs orchestrator events to JSON file."""
```

#### Constructor

```python
def __init__(self, config: Config, max_events: int = 100) -> None
```

#### Methods

##### `log`

```python
def log(
    self,
    event_type: str,
    data: dict | None = None
) -> None
```

Log an event.

**Parameters:**
- `event_type`: Type of event (e.g., "task_start", "terminal_busy")
- `data`: Additional event data

**Event Types:**
- `orchestrator_start`
- `orchestrator_stop`
- `task_start`
- `task_complete`
- `task_failed`
- `terminal_busy`
- `terminal_idle`
- `terminal_error`
- `subagent_invoked`
- `message_sent`
- `plan_created`

##### `get_recent`

```python
def get_recent(self, count: int = 50) -> list[Event]
```

Get most recent events.

**Parameters:**
- `count`: Number of events to return

**Returns:**
- List of Event objects, newest first

---

## Dashboard

**Module:** `orchestrator/dashboard.py`

FastAPI web UI for real-time monitoring.

### Function: `create_app`

```python
def create_app(config: Config) -> FastAPI
```

Create and configure the FastAPI application.

### Endpoints

#### `GET /`

Serve the HTML dashboard.

#### `GET /api/status`

Get current orchestrator status.

**Response:**
```json
{
    "status": "executing",
    "started_at": "2025-01-31T18:00:00",
    "tasks_pending": 2,
    "tasks_in_progress": 1,
    "tasks_completed": 5
}
```

#### `GET /api/tasks`

Get all tasks grouped by status.

**Response:**
```json
{
    "pending": [...],
    "in_progress": [...],
    "completed": [...]
}
```

#### `GET /api/tasks/{task_id}`

Get a specific task by ID.

#### `GET /api/messages`

Get all terminal inboxes.

**Response:**
```json
{
    "t1": [...],
    "t2": [...],
    "t3": [...],
    "t4": [...],
    "broadcast": [...]
}
```

#### `GET /api/terminals`

Get terminal configurations and states.

#### `GET /api/artifacts`

Get list of generated artifacts.

#### `GET /api/events`

Get recent events (last 50).

#### `WebSocket /ws`

Real-time updates via WebSocket.

**Message Format:**
```json
{
    "type": "update",
    "data": {
        "status": "...",
        "terminals": {...},
        "tasks": {...},
        "recent_events": [...]
    }
}
```

---

## Data Types

### Enums

#### `TerminalID`

```python
TerminalID = Literal["t1", "t2", "t3", "t4"]
```

#### `TerminalState`

```python
class TerminalState(Enum):
    IDLE = "idle"
    BUSY = "busy"
    ERROR = "error"
    STOPPED = "stopped"
```

#### `TaskStatus`

```python
class TaskStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
```

#### `TaskPriority`

```python
class TaskPriority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
```

#### `MessageType`

```python
class MessageType(Enum):
    REQUEST = "request"
    RESPONSE = "response"
    BROADCAST = "broadcast"
    STATUS = "status"
    ARTIFACT = "artifact"
```

### Dataclasses

#### `Task`

```python
@dataclass
class Task:
    id: str
    title: str
    description: str
    assigned_to: TerminalID | None
    status: TaskStatus
    priority: TaskPriority
    dependencies: list[str]
    created_at: str
    started_at: str | None
    completed_at: str | None
    result: str | None
    error: str | None
    metadata: dict
```

#### `Message`

```python
@dataclass
class Message:
    id: str
    sender: str
    recipient: str
    type: MessageType
    content: str
    timestamp: str
    metadata: dict
    read: bool
```

#### `Plan`

```python
@dataclass
class Plan:
    summary: str
    tasks: list[PlannedTask]
    execution_order: list[str]
```

#### `PlannedTask`

```python
@dataclass
class PlannedTask:
    id: str
    title: str
    description: str
    terminal: TerminalID
    priority: TaskPriority
    dependencies: list[str]
```

#### `TerminalOutput`

```python
@dataclass
class TerminalOutput:
    content: str
    started_at: str
    completed_at: str
    error: bool = False
    error_message: str | None = None
```

#### `ExecutionResult`

```python
@dataclass
class ExecutionResult:
    status: str  # "success" | "partial" | "failed"
    summary: str
    tasks_completed: int
    tasks_failed: int
    artifacts: list[str]
    terminal_outputs: dict[TerminalID, list[TerminalOutput]]
    duration_seconds: float
```

#### `Event`

```python
@dataclass
class Event:
    id: str
    type: str
    timestamp: str
    data: dict
```

---

## CLI Interface

**Module:** `orchestrator/__main__.py`

### Usage

```bash
python -m orchestrator [OPTIONS] [TASK]
```

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `TASK` | str | - | Task description (optional if --continuous) |
| `--dry-run` | flag | False | Plan only, no execution |
| `--dashboard` | flag | False | Start web dashboard |
| `--continuous` | flag | False | Loop for multiple tasks |
| `--parallel` | int | 4 | Number of terminals (1-10) |
| `--timeout` | int | 3600 | Total timeout in seconds |
| `--max-retries` | int | 2 | Retry attempts per task |
| `-v, --verbose` | flag | False | Detailed output |
| `-q, --quiet` | flag | False | Minimal output |

### Examples

```bash
# Basic execution
python -m orchestrator "Create a todo app"

# Dry run
python -m orchestrator --dry-run "Build a REST API"

# With dashboard
python -m orchestrator --dashboard "Create an iOS app"

# Continuous mode
python -m orchestrator --continuous --dashboard

# Controlled parallelism
python -m orchestrator --parallel 2 --verbose "Complex refactoring"
```

---

## Error Codes

| Code | Name | Description |
|------|------|-------------|
| 0 | SUCCESS | Task completed successfully |
| 1 | GENERAL_ERROR | Unspecified error |
| 2 | PLAN_FAILED | Could not create execution plan |
| 3 | TASK_FAILED | One or more tasks failed |
| 4 | TIMEOUT | Execution exceeded timeout |
| 5 | INTERRUPTED | User interrupted execution |

---

## See Also

- [Architecture Guide](./ARCHITECTURE.md)
- [Design Decisions](./DESIGN_DECISIONS.md)
- [Setup Guide](./SETUP.md)
- [README](../README.md)
