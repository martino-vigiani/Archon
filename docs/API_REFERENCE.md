# Archon API Reference

> Complete reference for both the **Live REST API** (JWT-authenticated, port 8000) and the **Dashboard API** (orchestration monitoring, port 8420).

| Service | Base URL | Auth | Purpose |
|---------|----------|------|---------|
| **Live REST API** | `http://localhost:8000/api/v1` | JWT Bearer | User management, resources, CRUD operations |
| **Dashboard API** | `http://localhost:8420` | None | Orchestration monitoring, terminal output, WebSocket |

---

## Table of Contents

- [Live REST API (port 8000)](#live-rest-api-port-8000)
  - [Authentication](#authentication)
    - [POST /auth/register](#post-apiv1authregister)
    - [POST /auth/login](#post-apiv1authlogin)
    - [POST /auth/refresh](#post-apiv1authrefresh)
    - [DELETE /auth/logout](#delete-apiv1authlogout)
  - [Users](#users)
    - [GET /users/me](#get-apiv1usersme)
    - [PUT /users/me](#put-apiv1usersme)
  - [Resources](#resources)
    - [GET /resources](#get-apiv1resources)
  - [Health](#health)
    - [GET /health](#get-apiv1health)
  - [Error Format](#live-api-error-format)
  - [API Client SDK](#api-client-sdk)
- [Dashboard API (port 8420)](#dashboard-api-endpoints)
  - [GET /api/status](#get-apistatus)
  - [GET /api/tasks](#get-apitasks)
  - [GET /api/tasks/{task_id}](#get-apitaskstask_id)
  - [GET /api/terminals](#get-apiterminals)
  - [GET /api/terminal-output/{terminal_id}](#get-apiterminal-outputterminal_id)
  - [POST /api/terminal-output/{terminal_id}](#post-apiterminal-outputterminal_id)
  - [GET /api/messages](#get-apimessages)
  - [GET /api/subagents](#get-apisubagents)
  - [GET /api/orchestrator-log](#get-apiorchestrator-log)
  - [GET /api/project](#get-apiproject)
  - [GET /api/artifacts](#get-apiartifacts)
  - [GET /api/events](#get-apievents)
  - [WebSocket /ws](#websocket-ws)
- [Python Module APIs](#python-module-apis)
  - [Orchestrator](#orchestrator)
  - [Planner](#planner)
  - [TaskQueue](#taskqueue)
  - [MessageBus](#messagebus)
  - [Terminal](#terminal)
  - [Config](#config)
- [Data Types](#data-types)

---

## Live REST API (port 8000)

JWT-authenticated REST API for user management and protected resources. Start with `python -m orchestrator.live_api` or `uvicorn orchestrator.live_api:app --reload`.

All endpoints use the `/api/v1` prefix. Protected endpoints require a `Bearer` token in the `Authorization` header.

### Authentication

#### POST /api/v1/auth/register

Register a new user account. The first user is automatically promoted to admin.

**Request:**

```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "alice@example.com",
    "password": "s3cur3P@ss!",
    "name": "Alice Chen"
  }'
```

**Response:** `201 Created`

```json
{
  "user": {
    "id": "a1b2c3d4e5f6...",
    "email": "alice@example.com",
    "name": "Alice Chen",
    "role": "admin",
    "created_at": "2026-02-20T14:00:00.000000",
    "updated_at": null
  },
  "tokens": {
    "access_token": "eyJhbGciOiJIUzI1NiIs...",
    "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
    "token_type": "bearer",
    "expires_in": 1800
  }
}
```

**Errors:**

| Code | Body | When |
|------|------|------|
| `409` | `{"error": {"code": "CONFLICT", "message": "A user with this email already exists."}}` | Email taken |
| `422` | `{"error": {"code": "VALIDATION_ERROR", ...}}` | Invalid input |

---

#### POST /api/v1/auth/login

Authenticate with email and password. Returns user profile and JWT token pair.

**Request:**

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "alice@example.com",
    "password": "s3cur3P@ss!"
  }'
```

**Response:** `200 OK` -- same shape as register response.

**Errors:**

| Code | Body | When |
|------|------|------|
| `401` | `{"error": {"code": "INVALID_CREDENTIALS", "message": "Email or password is incorrect."}}` | Wrong credentials |
| `403` | `{"error": {"code": "FORBIDDEN", "message": "Account is deactivated"}}` | Deactivated account |

---

#### POST /api/v1/auth/refresh

Exchange a valid refresh token for a new token pair. The old refresh token is revoked (rotation).

**Request:**

```bash
curl -X POST http://localhost:8000/api/v1/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{
    "refresh_token": "eyJhbGciOiJIUzI1NiIs..."
  }'
```

**Response:** `200 OK`

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

**Errors:**

| Code | Body | When |
|------|------|------|
| `401` | `{"error": {"code": "INVALID_TOKEN", ...}}` | Expired, revoked, or invalid refresh token |

---

#### DELETE /api/v1/auth/logout

Revoke the current session. Requires a valid access token.

**Request:**

```bash
curl -X DELETE http://localhost:8000/api/v1/auth/logout \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..."
```

**Response:** `200 OK`

```json
{
  "message": "Logged out successfully."
}
```

---

### Users

#### GET /api/v1/users/me

Get the current authenticated user's profile.

**Request:**

```bash
curl -s http://localhost:8000/api/v1/users/me \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..." | python -m json.tool
```

**Response:** `200 OK`

```json
{
  "id": "a1b2c3d4e5f6...",
  "email": "alice@example.com",
  "name": "Alice Chen",
  "role": "admin",
  "created_at": "2026-02-20T14:00:00.000000",
  "updated_at": "2026-02-20T15:30:00.000000"
}
```

---

#### PUT /api/v1/users/me

Update the current user's profile. Only provided fields are changed.

**Request:**

```bash
curl -X PUT http://localhost:8000/api/v1/users/me \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..." \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Alice C."
  }'
```

**Response:** `200 OK` -- updated user object.

**Errors:**

| Code | Body | When |
|------|------|------|
| `409` | `{"error": {"code": "CONFLICT", ...}}` | Email already taken by another user |

---

### Resources

#### GET /api/v1/resources

List protected resources with pagination. Requires authentication.

**Query Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `page` | int | `1` | Page number (1-indexed) |
| `per_page` | int | `20` | Items per page (1-100) |

**Request:**

```bash
curl -s "http://localhost:8000/api/v1/resources?page=1&per_page=5" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..." | python -m json.tool
```

**Response:** `200 OK`

```json
{
  "data": [
    {
      "id": "abc123",
      "title": "API Design Notes",
      "content": "RESTful patterns and endpoint conventions.",
      "owner_id": "a1b2c3d4e5f6...",
      "created_at": "2026-02-20T14:00:00.000000"
    }
  ],
  "meta": {
    "page": 1,
    "per_page": 5,
    "total": 5,
    "total_pages": 1
  }
}
```

---

### Health

#### GET /api/v1/health

Public health check. No authentication required.

```bash
curl -s http://localhost:8000/api/v1/health | python -m json.tool
```

**Response:** `200 OK`

```json
{
  "status": "healthy",
  "timestamp": "2026-02-20T14:30:00.000000+00:00"
}
```

---

### Live API Error Format

All Live API errors use a consistent nested format:

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable description.",
    "details": [
      {"field": "email", "message": "Invalid email format"}
    ]
  }
}
```

| HTTP Code | Error Codes | When |
|-----------|-------------|------|
| `401` | `UNAUTHORIZED`, `INVALID_CREDENTIALS`, `INVALID_TOKEN` | Missing/bad token, wrong password |
| `403` | `FORBIDDEN` | Insufficient role or deactivated account |
| `409` | `CONFLICT` | Duplicate email/username |
| `422` | `VALIDATION_ERROR` | Request body fails Pydantic validation |

---

### API Client SDK

The `orchestrator/api_client.py` module provides a typed async client for the Live API. Supports both real HTTP calls and mock mode.

```python
from orchestrator.api_client import APIClient

# Real mode (requires running server)
async with APIClient("http://localhost:8000/api/v1") as client:
    auth = await client.register("alice@example.com", "s3cur3P@ss!", "Alice")
    print(f"Logged in as {auth.user.name} ({auth.user.role.value})")

    me = await client.get_me()
    resources = await client.list_resources(page=1, per_page=10)
    print(f"Found {resources.meta.total} resources")

# Mock mode (no backend needed)
client = APIClient.mock()
auth = await client.login("alice@example.com", "password")
```

**Key methods:**

| Method | Description |
|--------|-------------|
| `register(email, password, name)` | Register and auto-login |
| `login(email, password)` | Login, returns `AuthResponse` |
| `refresh()` | Refresh access token |
| `logout()` | Revoke session |
| `get_me()` | Current user profile |
| `update_me(name=, email=)` | Update profile |
| `list_resources(page=, per_page=)` | Paginated resource list |
| `health()` | Health check |
| `get_token_status()` | Token introspection (for UI) |

The client automatically retries on `401` by refreshing the access token before failing.

---

## Dashboard API Endpoints

The dashboard is a FastAPI application that provides real-time monitoring of Archon's orchestration. Start it with `--dashboard` or run directly with `uvicorn orchestrator.dashboard:app`.

### GET /

Serve the dashboard HTML interface.

**Response:** `200 OK` — HTML page

```bash
curl http://localhost:8420/
```

---

### GET /api/status

Get the current orchestrator status including terminal states, task counts, and project info.

**Response:**

```json
{
  "state": "running",
  "terminals": {
    "t1": { "state": "busy", "current_task": "task_20260220_0001" },
    "t2": { "state": "idle", "current_task": null },
    "t3": { "state": "busy", "current_task": "task_20260220_0003" },
    "t4": { "state": "idle", "current_task": null },
    "t5": { "state": "busy", "current_task": "task_20260220_0005" }
  },
  "tasks": {
    "pending_count": 2,
    "in_progress_count": 3,
    "completed_count": 5,
    "failed_count": 0,
    "total_count": 10
  },
  "timestamp": "2026-02-20T14:30:00.000000",
  "project": {
    "name": "Archon",
    "path": "/Users/you/Tech/Archon",
    "type": "orchestrator",
    "status": "active"
  }
}
```

```bash
curl -s http://localhost:8420/api/status | python -m json.tool
```

---

### GET /api/tasks

Get all tasks grouped by queue status.

**Response:**

```json
{
  "pending": [
    {
      "id": "task_20260220_0006",
      "title": "Finalize all documentation",
      "description": "Complete documentation...",
      "assigned_to": "t3",
      "status": "pending",
      "priority": "medium",
      "dependencies": ["Create documentation structure"],
      "phase": 3,
      "quality_level": 0.0,
      "flow_state": "flowing",
      "created_at": "2026-02-20T14:00:00"
    }
  ],
  "in_progress": [ ... ],
  "completed": [ ... ],
  "failed": []
}
```

```bash
curl -s http://localhost:8420/api/tasks | python -m json.tool
```

---

### GET /api/tasks/{task_id}

Get a specific task by ID. Searches across all queues (pending, in_progress, completed).

**Path Parameters:**
- `task_id` (string, required) — The task identifier (e.g., `task_20260220_0001`)

**Response:** `200 OK` — Task object (same shape as items in `/api/tasks`)

**Error:** `404 Not Found` — `{"detail": "Task not found"}`

```bash
curl -s http://localhost:8420/api/tasks/task_20260220_0001 | python -m json.tool
```

---

### GET /api/terminals

Get terminal configurations including roles, descriptions, and available subagents.

**Response:**

```json
{
  "t1": {
    "id": "t1",
    "role": "UI/UX",
    "description": "Handles all user interface and user experience tasks",
    "subagents": ["swiftui-crafter", "react-crafter", "html-stylist", "design-system"]
  },
  "t2": {
    "id": "t2",
    "role": "Features",
    "description": "Implements core features, architecture, and data layer",
    "subagents": ["swift-architect", "node-architect", "python-architect", "swiftdata-expert", "database-expert", "ml-engineer"]
  },
  "t3": {
    "id": "t3",
    "role": "Docs/Marketing",
    "description": "Creates documentation and marketing materials",
    "subagents": ["tech-writer", "marketing-strategist"]
  },
  "t4": {
    "id": "t4",
    "role": "Ideas/Strategy",
    "description": "Handles product strategy, ideation, and monetization",
    "subagents": ["product-thinker", "monetization-expert"]
  },
  "t5": {
    "id": "t5",
    "role": "QA/Testing",
    "description": "Runs tests, validates outputs, verifies code quality and compilation",
    "subagents": ["test-genius", "swift-architect", "node-architect", "python-architect"]
  }
}
```

```bash
curl -s http://localhost:8420/api/terminals | python -m json.tool
```

---

### GET /api/terminal-output/{terminal_id}

Get the last output from a specific terminal's execution log.

**Path Parameters:**
- `terminal_id` (string, required) — One of: `t1`, `t2`, `t3`, `t4`, `t5`

**Query Parameters:**
- `max_lines` (int, default: 100) — Maximum number of lines to return

**Response:**

```json
{
  "terminal_id": "t1",
  "role": "UI/UX",
  "output": "--- [2026-02-20T14:15:00] ---\n## Summary\nCreated CounterView.swift with...",
  "timestamp": "2026-02-20T14:30:00.000000",
  "has_output": true
}
```

**Error:** `400 Bad Request` — Invalid terminal_id

```bash
# Get last 50 lines from T2
curl -s "http://localhost:8420/api/terminal-output/t2?max_lines=50" | python -m json.tool
```

---

### POST /api/terminal-output/{terminal_id}

Save terminal output (used internally by the orchestrator).

**Path Parameters:**
- `terminal_id` (string, required) — One of: `t1`, `t2`, `t3`, `t4`, `t5`

**Request Body:**

```json
{
  "content": "Terminal output text to save..."
}
```

**Response:**

```json
{
  "status": "saved",
  "terminal_id": "t2",
  "timestamp": "2026-02-20T14:30:00.000000"
}
```

```bash
curl -X POST http://localhost:8420/api/terminal-output/t2 \
  -H "Content-Type: application/json" \
  -d '{"content": "Build completed successfully"}'
```

---

### GET /api/messages

Get messages from all terminal inboxes and the broadcast channel.

**Response:**

```json
{
  "t1": "# Inbox\n\n---\n## Message: msg_20260220_0001\n...",
  "t2": "# Inbox\n\nNo messages yet.\n",
  "t3": "# Inbox\n\nNo messages yet.\n",
  "broadcast": "# Broadcast Channel\n\n## Phase 1 started..."
}
```

Messages are markdown-formatted text, not structured JSON. Each message in an inbox follows this format:

```markdown
---
## Message: msg_20260220143000_0001
**From:** t2 (via orchestrator)
**To:** t1
**Type:** status
**Time:** 2026-02-20T14:30:00

## Update from T2 (Features)
**Task completed:** Build core architecture
**Summary:** Created User and Habit models with SwiftData...
---
```

```bash
curl -s http://localhost:8420/api/messages | python -m json.tool
```

---

### GET /api/subagents

Get subagent invocation history and available subagents.

**Response:**

```json
{
  "invoked": [
    {
      "name": "swiftui-crafter",
      "terminal": "t1",
      "task": "Create UI components with mock data",
      "timestamp": "2026-02-20T14:15:00",
      "active": true,
      "id": "sa-0"
    }
  ],
  "available": [
    "database-expert",
    "design-system",
    "html-stylist",
    "marketing-strategist",
    "ml-engineer",
    "monetization-expert",
    "node-architect",
    "product-thinker",
    "python-architect",
    "react-crafter",
    "swift-architect",
    "swiftdata-expert",
    "swiftui-crafter",
    "tech-writer",
    "test-genius"
  ],
  "total_invocations": 1
}
```

```bash
curl -s http://localhost:8420/api/subagents | python -m json.tool
```

---

### GET /api/orchestrator-log

Get the orchestrator's decision log as structured entries. Useful for understanding why the manager took specific actions.

**Query Parameters:**
- `max_entries` (int, default: 50) — Maximum number of log entries to return

**Response:**

```json
{
  "entries": [
    {
      "timestamp": "14:30:00",
      "type": "routing",
      "message": "Assigned: Build core architecture -> t2",
      "raw": "[14:30:00] [TERMINAL] [t2] Assigned: Build core architecture"
    },
    {
      "timestamp": "14:29:00",
      "type": "state",
      "message": "FLOW STATE: FLOWING",
      "raw": "[14:29:00] [INFO] FLOW STATE: FLOWING"
    }
  ],
  "count": 2,
  "log_file": "/Users/you/Tech/Archon/.orchestra/orchestrator.log",
  "timestamp": "2026-02-20T14:30:00.000000"
}
```

Log entry types: `state`, `routing`, `decision`, `error`

```bash
# Get last 20 orchestrator decisions
curl -s "http://localhost:8420/api/orchestrator-log?max_entries=20" | python -m json.tool
```

---

### GET /api/project

Get current project information.

**Response:**

```json
{
  "name": "HabitTracker",
  "path": "/Users/you/Tech/Archon/Apps/HabitTracker",
  "type": "ios",
  "status": "active",
  "loaded_at": "2026-02-20T14:30:00.000000"
}
```

```bash
curl -s http://localhost:8420/api/project | python -m json.tool
```

---

### GET /api/artifacts

List files in the artifacts directory (`.orchestra/artifacts/`).

**Response:**

```json
[
  {
    "name": "counter_model.swift",
    "path": "/Users/you/Tech/Archon/.orchestra/artifacts/counter_model.swift",
    "size": 1234,
    "is_dir": false
  }
]
```

```bash
curl -s http://localhost:8420/api/artifacts | python -m json.tool
```

---

### GET /api/events

Get recent orchestrator events (last 50, newest first).

**Response:**

```json
[
  {
    "type": "task_completed",
    "timestamp": "2026-02-20T14:30:00",
    "details": {
      "terminal_id": "t2",
      "task_id": "task_20260220_0002",
      "task_title": "Build core architecture"
    }
  },
  {
    "type": "task_started",
    "timestamp": "2026-02-20T14:20:00",
    "details": {
      "terminal_id": "t2",
      "task_id": "task_20260220_0002",
      "task_title": "Build core architecture"
    }
  }
]
```

Event types: `orchestrator_started`, `orchestrator_stopped`, `plan_created`, `task_started`, `task_completed`, `task_failed`, `subagent_invoked`, `task_injected`, `task_cancelled`, `manager_action`

```bash
curl -s http://localhost:8420/api/events | python -m json.tool
```

---

### WebSocket /ws

Real-time updates via WebSocket. Sends consolidated state updates every 2 seconds (only when state changes).

**Connection:**

```javascript
const ws = new WebSocket("ws://localhost:8420/ws");
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log("Update:", data.type);
};
```

**Message Format:**

```json
{
  "type": "update",
  "timestamp": "2026-02-20T14:30:00.000000",
  "status": {
    "state": "running",
    "terminals": { ... },
    "tasks": { ... },
    "project": { ... }
  },
  "tasks": {
    "pending": [ ... ],
    "in_progress": [ ... ],
    "completed": [ ... ],
    "failed": []
  },
  "terminal_outputs": {
    "t1": "--- [2026-02-20T14:15:00] ---\n...",
    "t2": "",
    "t3": "",
    "t4": "",
    "t5": ""
  },
  "subagents": [ ... ],
  "orchestrator_log": [ ... ],
  "events": [ ... ]
}
```

**Testing with curl:**

```bash
# Install websocat for CLI WebSocket testing
brew install websocat

# Connect and receive updates
websocat ws://localhost:8420/ws
```

---

## Python Module APIs

### Orchestrator

**Module:** `orchestrator/orchestrator.py`

Central coordinator managing terminal workers, task distribution, and quality tracking.

#### Class: `Orchestrator`

```python
def __init__(
    self,
    config: Config | None = None,
    verbose: bool = True,
    retry_config: RetryConfig | None = None,
    continuous_mode: bool = False,
    enable_quality_check: bool = True,
    use_colors: bool = True,
    use_progress_bar: bool = True,
    max_quality_iterations: int = 1,
    use_organic_model: bool = False,
) -> None
```

**Key Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `run` | `async def run(self, task: str, project_context: str = "") -> dict` | Full orchestration workflow |
| `initialize` | `async def initialize(self) -> None` | Set up directories, clear state |
| `spawn_terminals` | `async def spawn_terminals(self) -> None` | Create all terminal workers |
| `plan_and_distribute` | `async def plan_and_distribute(self, task: str, ...) -> TaskPlan` | Plan and queue tasks |
| `run_task_loop` | `async def run_task_loop(self) -> None` | Main execution loop |
| `pause` | `async def pause(self) -> None` | Pause task execution |
| `resume` | `async def resume(self) -> None` | Resume after pause |
| `inject_task` | `async def inject_task(self, title, description, terminal_id, ...) -> Task` | Add task mid-execution |
| `cancel_task` | `async def cancel_task(self, task_id: str) -> bool` | Cancel a pending task |
| `get_detailed_status` | `def get_detailed_status(self) -> dict` | Comprehensive status for chat |
| `shutdown` | `async def shutdown(self) -> None` | Graceful shutdown |

**Example:**

```python
from orchestrator.config import Config
from orchestrator.orchestrator import Orchestrator

config = Config()
orch = Orchestrator(config=config, verbose=True)
result = await orch.run("Create an iOS habit tracker app")
print(f"Status: {result['status']}, Tasks: {result['tasks']['completed']}/{result['tasks']['total']}")
```

---

### Planner

**Module:** `orchestrator/planner.py`

Decomposes high-level tasks into terminal-specific subtasks using Claude Code CLI.

#### Class: `Planner`

```python
def __init__(self, config: Config, use_organic_model: bool = False) -> None
```

**Key Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `plan` | `async def plan(self, task: str, project_context: str = "") -> TaskPlan` | Create execution plan |

**Planning Modes:**
- **Legacy** — Phase-gated (0-3), parallel-first with soft dependencies
- **Organic** — Intent-based, quality gradients (0.0-1.0), no phase gates

**Example:**

```python
from orchestrator.planner import Planner, quick_plan

# Using convenience function
plan = await quick_plan("Build a REST API")
for task in plan.tasks:
    print(f"[{task.terminal}] {task.title} (phase {task.phase})")
```

---

### TaskQueue

**Module:** `orchestrator/task_queue.py`

Manages task lifecycle with file-based persistence to `.orchestra/tasks/`.

#### Class: `TaskQueue`

```python
def __init__(self, config: Config) -> None
```

**Properties:**

| Property | Type | Description |
|----------|------|-------------|
| `pending` | `list[Task]` | Tasks waiting to be assigned |
| `in_progress` | `list[Task]` | Tasks currently executing |
| `completed` | `list[Task]` | Finished tasks (success or failure) |

**Key Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `add_task` | `def add_task(self, title, description, priority, ...) -> Task` | Add a task to queue |
| `add_tasks` | `def add_tasks(self, tasks: list[dict]) -> list[Task]` | Add multiple tasks |
| `get_task` | `def get_task(self, task_id: str) -> Task \| None` | Find task by ID |
| `assign_task` | `def assign_task(self, task_id, terminal_id) -> Task \| None` | Assign to terminal |
| `complete_task` | `def complete_task(self, task_id, result, success, error) -> Task \| None` | Mark complete |
| `cancel_task` | `def cancel_task(self, task_id: str) -> Task \| None` | Cancel pending task |
| `get_next_task_for_terminal` | `def get_next_task_for_terminal(self, terminal_id, phase) -> Task \| None` | Get next available task |
| `get_flow_state` | `def get_flow_state(self) -> dict` | Organic flow health |
| `get_current_phase` | `def get_current_phase(self) -> int` | Legacy phase number |
| `get_status_summary` | `def get_status_summary(self) -> dict` | Task count summary |
| `is_all_done` | `def is_all_done(self) -> bool` | All tasks complete? |
| `update_task_quality` | `def update_task_quality(self, task_id, quality_level) -> Task \| None` | Update quality gradient |
| `mark_task_blocked` | `def mark_task_blocked(self, task_id, reason) -> Task \| None` | Block a task |
| `unblock_task` | `def unblock_task(self, task_id: str) -> Task \| None` | Unblock a task |
| `clear_all` | `def clear_all(self) -> None` | Reset all queues |

---

### MessageBus

**Module:** `orchestrator/message_bus.py`

File-based message passing between terminals using `.orchestra/messages/`.

#### Class: `MessageBus`

```python
def __init__(self, config: Config) -> None
```

**Key Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `send` | `def send(self, sender, recipient, content, msg_type, metadata) -> Message` | Send to terminal or broadcast |
| `broadcast_status` | `def broadcast_status(self, status: str, metadata) -> Message` | Broadcast to all terminals |
| `read_inbox` | `def read_inbox(self, terminal_id: TerminalID) -> str` | Read inbox contents |
| `read_broadcast` | `def read_broadcast(self) -> str` | Read broadcast channel |
| `clear_inbox` | `def clear_inbox(self, terminal_id: TerminalID) -> None` | Clear a terminal's inbox |
| `clear_all` | `def clear_all(self) -> None` | Clear all inboxes and broadcast |

**Message Types:** `request`, `response`, `broadcast`, `status`, `artifact`, `intervention`

---

### Terminal

**Module:** `orchestrator/terminal.py`

Wraps Claude Code CLI subprocess for task execution.

#### Class: `Terminal`

```python
def __init__(
    self,
    terminal_id: TerminalID,
    working_dir: Path,
    system_prompt: str | None = None,
    verbose: bool = True,
) -> None
```

**Key Properties:**

| Property | Type | Description |
|----------|------|-------------|
| `state` | `TerminalState` | Current state (IDLE, BUSY, ERROR, STOPPED) |
| `current_task_id` | `str \| None` | ID of currently executing task |

**Key Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `start` | `async def start(self) -> None` | Start the terminal subprocess |
| `execute_task` | `async def execute_task(self, prompt, task_id, timeout) -> TerminalOutput` | Execute a task |
| `stop` | `async def stop(self) -> None` | Stop the terminal |

---

### Config

**Module:** `orchestrator/config.py`

Configuration and terminal definitions.

#### Class: `Config`

```python
@dataclass
class Config:
    base_dir: Path          # Project root
    orchestra_dir: Path     # .orchestra/ runtime state
    templates_dir: Path     # Terminal prompt templates
    agents_dir: Path        # .claude/agents/ subagent definitions
    apps_dir: Path          # Apps/ generated projects
    terminals: dict[TerminalID, TerminalConfig]
    max_terminals: int = 5
    poll_interval: float = 2.0
    terminal_timeout: float = 600.0
    disable_testing: bool = False
```

**Key Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `ensure_dirs` | `def ensure_dirs(self) -> None` | Create required directories |
| `get_terminal_config` | `def get_terminal_config(self, terminal_id) -> TerminalConfig` | Get terminal config |
| `route_task_to_terminal` | `def route_task_to_terminal(self, description) -> TerminalID` | Keyword-based routing |
| `create_project_structure` | `def create_project_structure(self, name, ...) -> Path` | Create new project |
| `get_project_info` | `def get_project_info(self, path) -> ProjectMetadata \| None` | Read project metadata |
| `list_projects` | `def list_projects(self, status) -> list[tuple]` | List all projects |

---

## Data Types

### Enums

```python
TerminalID = Literal["t1", "t2", "t3", "t4", "t5"]

class TerminalState(Enum):
    IDLE = "idle"
    BUSY = "busy"
    ERROR = "error"
    STOPPED = "stopped"

class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"

class TaskPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class FlowState(str, Enum):
    FLOWING = "flowing"          # Work progressing normally
    BLOCKED = "blocked"          # Stopped due to dependency
    FLOURISHING = "flourishing"  # Exceeding expectations
    STALLED = "stalled"          # Slow/stuck without clear blocker
    CONVERGING = "converging"    # Approaching completion

MessageType = Literal["request", "response", "broadcast", "status", "artifact", "intervention"]
```

### Task

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
    phase: int                          # 0-3 (legacy)
    quality_level: float                # 0.0-1.0 (organic)
    flow_state: FlowState              # Organic flow health
    intent: str | None                 # High-level goal
    created_at: str
    started_at: str | None
    completed_at: str | None
    result: str | None
    error: str | None
    metadata: dict
```

### Message

```python
@dataclass
class Message:
    id: str
    sender: str                        # Terminal ID or "orchestrator"
    recipient: str                     # Terminal ID, "all", or "orchestrator"
    type: MessageType
    content: str
    timestamp: str
    metadata: dict
    read: bool
```

### TaskPlan

```python
@dataclass
class TaskPlan:
    original_task: str
    summary: str
    tasks: list[PlannedTask]
    execution_order: list[str]
    intents: list[Intent]              # Organic model
    planning_mode: str                 # "legacy" or "organic"
```

### TerminalConfig

```python
@dataclass
class TerminalConfig:
    id: TerminalID
    role: str
    description: str
    subagents: list[str]
    keywords: list[str]
```

---

## Error Handling

All API endpoints return JSON. Errors follow this pattern:

```json
{
  "detail": "Error description"
}
```

| HTTP Code | Meaning |
|-----------|---------|
| `200` | Success |
| `400` | Bad request (invalid terminal_id, etc.) |
| `404` | Resource not found (task_id doesn't exist) |
| `500` | Internal server error |

---

## See Also

- [Authentication Guide](./AUTH_GUIDE.md) — JWT flow, token lifecycle, role permissions
- [Deployment Guide](./DEPLOYMENT.md) — Docker, environment config, production checklist
- [Architecture & Security](./ARCHITECTURE_AND_SECURITY.md) — Security posture and hardening
- [Getting Started Guide](./GETTING_STARTED.md) — curl examples and first-run walkthrough
- [Setup Guide](./SETUP.md) — Installation and configuration
- [README](../README.md) — Overview and quick start
