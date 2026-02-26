# Getting Started with Archon

> From zero to your first orchestrated project in 5 minutes.

---

## Prerequisites

Before you begin, make sure you have:

1. **Python 3.11+** — `python --version`
2. **Claude Code CLI** — `claude --version` ([install here](https://github.com/anthropics/claude-code))
3. **Active Claude subscription** — Pro, Max, or Team (Max 5x recommended for parallel usage)

---

## Install

```bash
git clone https://github.com/martino-vigiani/Archon.git
cd Archon
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

---

## Your First Run

### Dry Run (See the Plan)

See what Archon would do without executing anything:

```bash
python -m orchestrator --dry-run "Create a simple counter app"
```

You'll see a task plan showing which terminal handles each piece of work:

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
  4. [T1] Create UI components with mock data
     Priority: critical
  ...
```

### Execute with Dashboard

Run a real task with the web dashboard for monitoring:

```bash
python -m orchestrator --dashboard "Create a SwiftUI counter app"
```

This:
1. Opens `http://localhost:8420` in your browser
2. Plans the task across 5 terminals
3. Executes all phases (planning, building, integration, testing)
4. Shows real-time progress in the dashboard

### Interactive Chat Mode

Guide the orchestration in real-time:

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

---

## Monitoring with the Dashboard API

When the dashboard is running (`--dashboard`), you can query the API directly.

### Check Overall Status

```bash
curl -s http://localhost:8420/api/status | python -m json.tool
```

Response:
```json
{
  "state": "running",
  "terminals": {
    "t1": {"state": "busy", "current_task": "task_20260220_0001"},
    "t2": {"state": "busy", "current_task": "task_20260220_0002"},
    "t3": {"state": "idle", "current_task": null},
    "t4": {"state": "idle", "current_task": null},
    "t5": {"state": "busy", "current_task": "task_20260220_0005"}
  },
  "tasks": {
    "pending_count": 3,
    "in_progress_count": 3,
    "completed_count": 4,
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

### List All Tasks

```bash
curl -s http://localhost:8420/api/tasks | python -m json.tool
```

### Get a Specific Task

```bash
curl -s http://localhost:8420/api/tasks/task_20260220_0001 | python -m json.tool
```

### View Terminal Configurations

```bash
curl -s http://localhost:8420/api/terminals | python -m json.tool
```

### Read Terminal Output

See what a specific terminal has been doing:

```bash
# Last 50 lines of T2's output
curl -s "http://localhost:8420/api/terminal-output/t2?max_lines=50" | python -m json.tool
```

### Check Inter-Terminal Messages

```bash
curl -s http://localhost:8420/api/messages | python -m json.tool
```

### View Orchestrator Decisions

See why the manager made specific routing or intervention decisions:

```bash
curl -s "http://localhost:8420/api/orchestrator-log?max_entries=20" | python -m json.tool
```

### List Subagent Invocations

```bash
curl -s http://localhost:8420/api/subagents | python -m json.tool
```

### View Event Timeline

```bash
curl -s http://localhost:8420/api/events | python -m json.tool
```

### Real-Time Updates via WebSocket

```bash
# Install websocat for CLI WebSocket testing
brew install websocat

# Connect to real-time feed
websocat ws://localhost:8420/ws
```

---

## Common Workflows

### Build a New App

```bash
# iOS app
python -m orchestrator --dashboard "Create a SwiftUI habit tracker with streaks and daily reminders"

# Web app
python -m orchestrator --dashboard "Create a React todo app with Next.js and Tailwind"

# Backend API
python -m orchestrator --dashboard "Build a REST API for user management with Node.js"
```

### Work on an Existing Project

```bash
python -m orchestrator --project ./Apps/MyApp "Add dark mode support"
```

### Save API Limits

Disable T5 (QA/Testing) when prototyping:

```bash
python -m orchestrator --no-testing "Quick prototype of a calculator"
```

### Resume After Interruption

```bash
python -m orchestrator --resume
```

### Continuous Mode

Keep working on new tasks without restarting:

```bash
python -m orchestrator --dashboard --continuous
```

---

## Understanding the Output

After execution, Archon prints a summary:

```
  EXECUTION SUMMARY
  ============================================================

  Status: SUCCESS

  Time
  -------------------------
    Total Duration:    2m 34s
    Started:           14:30:00
    Finished:          14:32:34

  Tasks
  -------------------------
    Total:             10
    Completed:         10
    Failed:            0
    Pending:           0

  Tasks per Terminal
  -------------------------
    [T1] Craftsman: 3 tasks (3 ok, 0 failed)
    [T2] Architect: 3 tasks (3 ok, 0 failed)
    [T3] Narrator: 2 tasks (2 ok, 0 failed)
    [T4] Strategist: 1 tasks (1 ok, 0 failed)
    [T5] Skeptic: 1 tasks (1 ok, 0 failed)
```

### Exit Codes

| Code | Meaning |
|------|---------|
| `0` | All tasks completed successfully |
| `1` | Some tasks failed or timed out |
| `130` | Interrupted by user (Ctrl+C) |

---

## Troubleshooting

### "claude: command not found"

Install Claude Code CLI: https://github.com/anthropics/claude-code

### Rate Limit Hit

Archon detects rate limits automatically and stops gracefully. Solutions:
- Use `--no-testing` to reduce API calls
- Upgrade to Claude Max 5x for higher limits
- Wait for the reset time shown in the error

### Dashboard Won't Start

Check if port 8420 is in use:

```bash
lsof -i :8420
kill -9 <PID>  # Kill the process using the port
```

### Task Stuck in Progress

Check the terminal's output:

```bash
curl -s http://localhost:8420/api/terminal-output/t2 | python -m json.tool
```

Check the orchestrator log for errors:

```bash
curl -s http://localhost:8420/api/orchestrator-log | python -m json.tool
```

---

## Next Steps

- **[API Reference](./API_REFERENCE.md)** — Full endpoint documentation
- **[Architecture](./ARCHITECTURE.md)** — How the organic flow model works
- **[Setup Guide](./SETUP.md)** — Advanced configuration
- **[README](../README.md)** — Philosophy and terminal personalities

---

## Quick Reference Card

```bash
# Run with dashboard
python -m orchestrator --dashboard "Your task"

# Interactive mode
python -m orchestrator --chat --dashboard "Your task"

# Dry run (plan only)
python -m orchestrator --dry-run "Your task"

# Existing project
python -m orchestrator --project ./path "Add feature"

# API status check
curl -s http://localhost:8420/api/status | python -m json.tool

# All tasks
curl -s http://localhost:8420/api/tasks | python -m json.tool

# Terminal output
curl -s http://localhost:8420/api/terminal-output/t1 | python -m json.tool

# Real-time WebSocket
websocat ws://localhost:8420/ws
```
