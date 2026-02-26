# Archon Setup Guide

> Complete installation and configuration guide for Archon.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Quick Start](#quick-start)
3. [Detailed Installation](#detailed-installation)
4. [Configuration](#configuration)
5. [First Run](#first-run)
6. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required

| Requirement | Version | Check Command |
|-------------|---------|---------------|
| Python | 3.11+ | `python --version` |
| pip | Latest | `pip --version` |
| Model CLI runtime | Latest | `claude --version` or `codex --version` |
| Provider access | Active | Check account/subscription for selected runtime |

### Optional

| Tool | Purpose |
|------|---------|
| git | Version control |
| Black | Python formatting (`pip install black`) |
| Ruff | Python linting (`pip install ruff`) |
| websocat | CLI WebSocket testing (`brew install websocat`) |

---

## Quick Start

```bash
# Clone and enter directory
git clone https://github.com/martino-vigiani/Archon.git
cd Archon

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run your first task
python -m orchestrator "Create a simple todo app"

# Optional: run with Codex runtime
python -m orchestrator --llm-provider codex --llm-model gpt-5.3-codex "Create a simple todo app"
```

---

## Detailed Installation

### Step 1: Clone Repository

```bash
git clone https://github.com/martino-vigiani/Archon.git
cd Archon
```

Or download and extract the ZIP file from GitHub.

### Step 2: Python Environment

**macOS/Linux:**
```bash
# Create virtual environment
python -m venv .venv

# Activate it
source .venv/bin/activate

# Verify Python version
python --version  # Should be 3.11+
```

**Windows:**
```powershell
# Create virtual environment
python -m venv .venv

# Activate it
.venv\Scripts\activate

# Verify Python version
python --version
```

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

**Dependencies installed:**

| Package | Version | Purpose |
|---------|---------|---------|
| `fastapi` | >=0.109.0 | Web framework for dashboard |
| `uvicorn` | >=0.27.0 | ASGI server |
| `websockets` | >=12.0 | WebSocket support |
| `pydantic` | >=2.5.0 | Data validation |
| `bcrypt` | >=4.1.0 | Authentication utilities |
| `PyJWT` | >=2.8.0 | JWT token handling |
| `tqdm` | >=4.66.0 | Progress bars (optional) |

### Step 4: Verify Runtime CLI

```bash
# Check default runtime
claude --version

# Optional Codex runtime
codex --version
```

### Step 5: Verify Directory Structure

After installation, verify this structure:

```
Archon/
├── .claude/
│   ├── CLAUDE.md              # Project instructions
│   ├── settings.json          # Permissions
│   └── agents/                # 20 subagent definitions (.md format)
│       ├── swiftui-crafter.md
│       ├── react-crafter.md
│       ├── swift-architect.md
│       ├── python-architect.md
│       ├── node-architect.md
│       ├── database-expert.md
│       ├── swiftdata-expert.md
│       ├── design-system.md
│       ├── dashboard-architect.md
│       ├── web-ui-designer.md
│       ├── html-stylist.md
│       ├── tech-writer.md
│       ├── test-genius.md
│       ├── ml-engineer.md
│       ├── marketing-strategist.md
│       ├── product-thinker.md
│       ├── monetization-expert.md
│       ├── claude-code-toolsmith.md
│       ├── prompt-craftsman.md
│       └── cli-ux-master.md
├── orchestrator/              # Python core (19 modules)
│   ├── __init__.py
│   ├── __main__.py            # CLI entry point
│   ├── orchestrator.py        # Main coordinator
│   ├── planner.py             # Intent broadcasting
│   ├── terminal.py            # Claude Code subprocess wrapper
│   ├── task_queue.py          # Flow-based work management
│   ├── message_bus.py         # Inter-terminal communication
│   ├── config.py              # Configuration and terminal definitions
│   ├── cli_display.py         # Colors, terminal badges, quality bars
│   ├── dashboard.py           # FastAPI web UI (localhost:8420)
│   ├── session.py             # Session management and execution runners
│   ├── manager_chat.py        # Interactive chat REPL
│   ├── manager_intelligence.py # Intervention decisions
│   ├── sync_manager.py        # Heartbeat coordination
│   ├── contract_manager.py    # Interface negotiation
│   ├── report_manager.py      # Quality gradient tracking
│   ├── validator.py           # Continuous validation
│   ├── logger.py              # Event logging system
│   └── api_client.py          # API client utilities
├── static/                    # Dashboard frontend
│   ├── index.html
│   └── js/
│       ├── dashboard-interactions.js
│       └── websocket-integration.js
├── templates/                 # Terminal prompts
│   └── terminal_prompts/
├── tests/                     # Test suite
├── docs/                      # Documentation
├── .orchestra/                # Created on first run (runtime data)
├── requirements.txt           # Python dependencies
├── pyproject.toml             # Project metadata
└── README.md                  # Project overview
```

---

## Configuration

### CLI Flags

All configuration can be passed via command-line flags:

| Flag | Description | Default |
|------|-------------|---------|
| `--dashboard` | Start web UI at localhost:8420 | off |
| `--chat` | Interactive Manager Chat mode | off |
| `--continuous` | Keep running, prompt for new tasks | off |
| `--dry-run` | Show plan without executing | off |
| `--project PATH` | Work on existing project directory | current dir |
| `--no-testing` | Disable T5 QA terminal (saves API limits) | off |
| `--max-retries N` | Retry failed tasks | 2 |
| `--timeout N` | Max execution time (seconds) | 3600 |
| `--parallel N` | Number of parallel terminals (1-10) | 4 |
| `--quality-threshold` | Minimum quality level (0.0-1.0) | 0.8 |
| `--resume` | Resume last interrupted session | off |
| `--verbose-flow` | Show detailed flow state changes | off |
| `--llm-provider` | Runtime provider (`claude` or `codex`) | `claude` |
| `--llm-command` | Override runtime command binary | provider default |
| `--llm-model` | Runtime model id | provider default |
| `--full-prompts` | Disable compact prompt templates | off |
| `--max-system-prompt-chars N` | Cap system prompt size for token efficiency | 4200 |
| `-v, --verbose` | Verbose output | off |
| `-q, --quiet` | Minimal output | off |
| `--config PATH` | Path to custom config file (JSON) | none |

### Custom Config File

You can pass a JSON config file with `--config`:

```bash
python -m orchestrator --config my_config.json "task"
```

### Terminal Personalities

Archon runs 5 terminals, each with a distinct personality:

| Terminal | Personality | Home Domain | Superpower |
|----------|-------------|-------------|------------|
| **T1** | The Craftsman | UI/UX | Makes anything beautiful |
| **T2** | The Architect | Backend/Systems | Makes anything reliable |
| **T3** | The Narrator | Documentation | Explains anything clearly |
| **T4** | The Strategist | Product/Vision | Sees the whole board |
| **T5** | The Skeptic | QA/Testing | Finds any flaw |

Use `--no-testing` to disable T5 when prototyping to save API limits.

### Runtime Directory (`.orchestra/`)

Created automatically on first run. Contains:

```
.orchestra/
├── tasks/
│   ├── pending.json       # Queued tasks
│   ├── in_progress.json   # Active tasks
│   └── completed.json     # Finished tasks
├── messages/
│   ├── t1_inbox.md        # T1 message inbox
│   ├── t2_inbox.md        # T2 message inbox
│   ├── t3_inbox.md        # T3 message inbox
│   ├── t4_inbox.md        # T4 message inbox
│   ├── t5_inbox.md        # T5 message inbox
│   └── broadcast.md       # Broadcast messages
├── terminal_output/
│   ├── t1.txt             # T1 output log
│   ├── t2.txt             # T2 output log
│   ├── t3.txt             # T3 output log
│   ├── t4.txt             # T4 output log
│   └── t5.txt             # T5 output log
├── artifacts/             # Generated artifacts
├── status.json            # Current orchestrator state
├── events.json            # Event timeline
├── orchestrator.log       # Decision log
└── last_project.json      # Last project info (for --resume)
```

---

## First Run

### Test Installation

```bash
# Simple test - dry run (no API calls to terminals)
python -m orchestrator --dry-run "Test task"
```

Expected output:
```
  TASK PLAN
  ============================================================

  Summary: 4-phase execution plan...

  1. [T4] Broadcast MVP scope and direction
     Priority: critical
  2. [T1] Define interface contracts
     Priority: critical
  3. [T2] Build core architecture and data models
     Priority: critical
  ...

  [Dry run - execution skipped]
```

### Run with Dashboard

```bash
python -m orchestrator --dashboard "Create a hello world app"
```

Open browser: **http://localhost:8420**

You'll see:
- Terminal status for all 5 terminals (T1-T5)
- Task queue (pending / in progress / completed)
- Message bus activity
- Event timeline
- Orchestrator decision log

### Interactive Chat Mode

```bash
python -m orchestrator --chat --dashboard "Build a habit tracking app"
```

Chat commands:
```
> status              # Overall system health
> status t1           # Check T1 (The Craftsman)
> tasks               # List all tasks
> pause               # Pause execution
> resume              # Resume execution
> inject: Add login   # Inject a new task mid-run
> cancel <task_id>    # Cancel a pending task
> reports             # Show terminal reports
> help                # All commands
```

### Run a Real Task

```bash
# iOS app
python -m orchestrator "Create a SwiftUI habit tracker with streaks"

# Backend
python -m orchestrator "Build a REST API for user management"

# Full stack
python -m orchestrator "Create a todo app with React frontend and Node backend"

# Existing project
python -m orchestrator --project ./Apps/MyApp "Add dark mode"
```

---

## Troubleshooting

### Claude Code Not Found

**Error:**
```
FileNotFoundError: [Errno 2] No such file or directory: 'claude'
```

**Solution:**
1. Verify installation: `which claude` (macOS/Linux) or `where claude` (Windows)
2. If missing, install from https://github.com/anthropics/claude-code
3. Ensure it's in PATH:
   ```bash
   export PATH="$PATH:/path/to/claude"
   ```

### Permission Denied

**Error:**
```
PermissionError: [Errno 13] Permission denied: '.orchestra/messages/t1_inbox.md'
```

**Solution:**
```bash
# Fix permissions on .orchestra directory
chmod -R 755 .orchestra

# Or delete and let Archon recreate
rm -rf .orchestra
```

### Port Already in Use

**Error:**
```
uvicorn.error: ERROR: [Errno 48] Address already in use
```

**Solution:**
```bash
# Find process using port 8420
lsof -i :8420

# Kill it
kill -9 <PID>
```

### Rate Limit Hit

**Error:**
```
Error: API rate limit exceeded
```

**Solution:**
1. Archon detects rate limits automatically and stops gracefully
2. Use `--no-testing` to reduce API calls (disables T5)
3. Reduce parallelism: `--parallel 2`
4. Upgrade to Claude Max 5x for higher limits
5. Wait for the reset time shown in the error

### Task Stuck in Progress

**Symptoms:**
- Task stuck in "in_progress" state
- No output from a terminal

**Debug:**
```bash
# Check terminal output via dashboard API
curl -s http://localhost:8420/api/terminal-output/t2 | python -m json.tool

# Check orchestrator decisions
curl -s http://localhost:8420/api/orchestrator-log | python -m json.tool

# Check events log
curl -s http://localhost:8420/api/events | python -m json.tool

# Run with verbose output
python -m orchestrator -v "task"
```

### Python Version Issues

**Error:**
```
SyntaxError: invalid syntax (using match statement or | union)
```

**Solution:**
```bash
# Verify Python version
python --version  # Must be 3.11+

# If wrong version, use specific python
python3.11 -m orchestrator "task"

# Or update alias
alias python=python3.11
```

### Virtual Environment Issues

**Error:**
```
ModuleNotFoundError: No module named 'fastapi'
```

**Solution:**
```bash
# Ensure venv is activated
source .venv/bin/activate  # macOS/Linux
# or
.venv\Scripts\activate  # Windows

# Reinstall dependencies
pip install -r requirements.txt
```

---

## Verification Checklist

Run through this checklist to verify your installation:

```bash
# 1. Python version
python --version
# Expected: Python 3.11.x or higher

# 2. Virtual environment active
echo $VIRTUAL_ENV
# Expected: /path/to/Archon/.venv

# 3. Dependencies installed
pip list | grep -E "fastapi|uvicorn|websockets|pydantic"
# Expected: All four packages listed

# 4. Claude Code available
claude --version
# Expected: Version number

# 5. Subagents present (20 agents, .md format)
ls .claude/agents/*.md | wc -l
# Expected: 20

# 6. Orchestrator modules
ls orchestrator/*.py | wc -l
# Expected: 19

# 7. Dry run works
python -m orchestrator --dry-run "Test"
# Expected: Plan output without execution

# 8. Dashboard starts
python -m orchestrator.dashboard &
curl -s http://localhost:8420/api/status | python -m json.tool
# Expected: JSON response with state, terminals, tasks
kill %1  # Stop background dashboard
```

---

## Next Steps

- **[Getting Started](./GETTING_STARTED.md)** -- Your first run in 5 minutes
- **[API Reference](./API_REFERENCE.md)** -- Full endpoint and module documentation
- **[Architecture](./ARCHITECTURE.md)** -- How the organic flow model works
- **[README](../README.md)** -- Philosophy and terminal personalities

---

<p align="center">
  <sub>Happy orchestrating!</sub>
</p>
