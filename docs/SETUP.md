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
| Claude Code CLI | Latest | `claude --version` |
| Claude Max | Active | Check subscription |

### Optional

| Tool | Purpose |
|------|---------|
| git | Version control |
| Black | Python formatting |
| Ruff | Python linting |

---

## Quick Start

```bash
# Clone and enter directory
git clone https://github.com/martinovigiani/archon.git
cd archon

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run your first task
python -m orchestrator "Create a simple todo app"
```

---

## Detailed Installation

### Step 1: Clone Repository

```bash
git clone https://github.com/martinovigiani/archon.git
cd archon
```

Or download and extract the ZIP file.

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
- `fastapi>=0.109.0` - Web framework for dashboard
- `uvicorn>=0.27.0` - ASGI server
- `websockets>=12.0` - WebSocket support
- `tqdm>=4.66.0` - Progress bars (optional)

### Step 4: Verify Claude Code

```bash
# Check Claude Code is installed
claude --version

# If not installed, follow:
# https://claude.ai/code/install
```

### Step 5: Directory Structure

After installation, verify this structure:

```
archon/
├── .claude/
│   ├── CLAUDE.md           ✓ Project instructions
│   ├── settings.json       ✓ Permissions
│   └── agents/             ✓ 14 subagent definitions
│       ├── swiftui-crafter.yml
│       └── ... (13 more)
├── orchestrator/           ✓ Python core
│   ├── __main__.py
│   ├── orchestrator.py
│   └── ... (8 more)
├── templates/              ✓ Terminal prompts
│   └── terminal_prompts/
├── .orchestra/             ✓ Created on first run
├── requirements.txt        ✓ Dependencies
└── README.md               ✓ Documentation
```

---

## Configuration

### Claude Settings

**File:** `.claude/settings.json`

```json
{
  "permissions": {
    "allow": [
      "Read",
      "Write",
      "Edit",
      "Bash",
      "Glob",
      "Grep",
      "WebFetch"
    ],
    "deny": [
      "Read .env",
      "Read credentials"
    ]
  },
  "model": "opus",
  "hooks": {
    "post_tool": [
      {
        "tool": "Write",
        "pattern": "*.py",
        "command": "black {file}"
      }
    ]
  }
}
```

### Local Overrides

**File:** `.claude/settings.local.json` (not committed to git)

```json
{
  "model": "sonnet",
  "verbose": true,
  "subagents": {
    "max_parallel": 5
  }
}
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ARCHON_PARALLEL` | Number of terminals | 4 |
| `ARCHON_TIMEOUT` | Execution timeout (seconds) | 3600 |
| `ARCHON_DASHBOARD_PORT` | Dashboard port | 8420 |
| `ARCHON_VERBOSE` | Enable verbose logging | false |

```bash
# Example usage
export ARCHON_PARALLEL=2
export ARCHON_VERBOSE=true
python -m orchestrator "your task"
```

---

## First Run

### Test Installation

```bash
# Simple test - dry run
python -m orchestrator --dry-run "Test task"
```

Expected output:
```
Archon - Multi-Agent Orchestrator
==================================

Planning task: Test task

Plan created:
├── T4: Define requirements
├── T2: Design architecture
└── T3: Write documentation

[Dry run - execution skipped]
```

### Run with Dashboard

```bash
python -m orchestrator --dashboard "Create a hello world app"
```

Open browser: **http://localhost:8420**

You'll see:
- Terminal status (T1-T4)
- Task queue (pending/in_progress/completed)
- Message bus activity
- Event timeline

### Run a Real Task

```bash
# iOS app
python -m orchestrator "Create a SwiftUI habit tracker with streaks"

# Backend
python -m orchestrator "Build a REST API for user management"

# Full stack
python -m orchestrator "Create a todo app with React frontend and Node backend"
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
2. If missing, install from [claude.ai/code](https://claude.ai/code)
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

# Or use different port
ARCHON_DASHBOARD_PORT=8421 python -m orchestrator --dashboard "task"
```

### Claude API Errors

**Error:**
```
Error: API rate limit exceeded
```

**Solution:**
1. Check Claude Max subscription is active
2. Reduce parallelism: `--parallel 2`
3. Add delays between tasks (automatic retry handles this)

### Subagent Not Responding

**Symptoms:**
- Task stuck in "in_progress"
- No output from terminal

**Debug:**
```bash
# Check terminal inbox
cat .orchestra/messages/t1_inbox.md

# Check events log
cat .orchestra/events.json | python -m json.tool

# Run with verbose
python -m orchestrator -v "task"
```

**Solutions:**
1. Verify agent YAML syntax: `python -c "import yaml; yaml.safe_load(open('.claude/agents/swiftui-crafter.yml'))"`
2. Check model availability (opus/sonnet)
3. Reduce task complexity

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

# Or update PATH
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

# 2. Virtual environment
echo $VIRTUAL_ENV
# Expected: /path/to/archon/.venv

# 3. Dependencies
pip list | grep -E "fastapi|uvicorn|websockets"
# Expected: All three packages listed

# 4. Claude Code
claude --version
# Expected: Version number

# 5. Project structure
ls -la .claude/agents/ | wc -l
# Expected: 14 (agents)

# 6. Dry run
python -m orchestrator --dry-run "Test"
# Expected: Plan output without execution

# 7. Dashboard
python -m orchestrator.dashboard &
curl http://localhost:8420/api/status
# Expected: JSON response
```

---

## Next Steps

1. **Read the README**: [README.md](../README.md)
2. **Understand Architecture**: [ARCHITECTURE.md](ARCHITECTURE.md)
3. **Review API**: [API_REFERENCE.md](API_REFERENCE.md)
4. **Learn Design Rationale**: [DESIGN_DECISIONS.md](DESIGN_DECISIONS.md)

### Quick Reference

```bash
# Basic execution
python -m orchestrator "task"

# With options
python -m orchestrator \
    --dashboard \           # Web UI
    --parallel 4 \          # Terminals
    --verbose \             # Detailed output
    "your task here"

# Continuous mode
python -m orchestrator --continuous

# Dry run (planning only)
python -m orchestrator --dry-run "task"
```

---

## Getting Help

- **Issues**: [GitHub Issues](https://github.com/martinovigiani/archon/issues)
- **Discussions**: [GitHub Discussions](https://github.com/martinovigiani/archon/discussions)

---

## See Also

- [README](../README.md) - Overview and quick start
- [Architecture Guide](./ARCHITECTURE.md) - System design deep-dive
- [API Reference](./API_REFERENCE.md) - Internal API documentation
- [Design Decisions](./DESIGN_DECISIONS.md) - Rationale behind choices

---

<p align="center">
  <sub>Happy orchestrating!</sub>
</p>
