<p align="center">
  <h1 align="center">ARCHON</h1>
  <p align="center">
    <strong>Multi-Agent Development Orchestrator</strong>
  </p>
  <p align="center">
    Autonomous software development through coordinated AI agents
  </p>
</p>

<p align="center">
  <a href="#features"><img src="https://img.shields.io/badge/Agents-14-blue" alt="14 Agents"></a>
  <a href="#terminals"><img src="https://img.shields.io/badge/Terminals-4-green" alt="4 Terminals"></a>
  <a href="#requirements"><img src="https://img.shields.io/badge/Python-3.11+-yellow" alt="Python 3.11+"></a>
  <a href="#requirements"><img src="https://img.shields.io/badge/Claude_Code-required-orange" alt="Claude Code"></a>
  <a href="#license"><img src="https://img.shields.io/badge/License-MIT-lightgrey" alt="MIT License"></a>
</p>

---

## Overview

Archon is a **multi-agent orchestration system** that coordinates 4 parallel Claude Code terminals to build software autonomously. Each terminal specializes in a different aspect of development and has access to domain-specific subagents.

Give Archon a task like *"Create an iOS app for speed testing"* and watch as it:

1. **Plans** - Breaks down the task into parallel workstreams
2. **Delegates** - Assigns work to specialized terminals and subagents
3. **Coordinates** - Manages inter-terminal communication
4. **Delivers** - Produces a complete, working application

### Philosophy

Archon embraces a **maximally agentic** approach:

- **Delegate to Specialists** - Use the right subagent for each task
- **Parallelize Aggressively** - Run up to 10 subagents simultaneously
- **Act Autonomously** - Make decisions, don't ask for permission on trivial matters
- **Maintain Clean Context** - Offload exploration to subagents
- **Prioritize Quality** - Better to do it right than do it fast

---

## Features

- **4 Parallel Terminals** - Simultaneous execution across UI, features, docs, and strategy
- **14 Specialized Subagents** - Domain experts for every aspect of development
- **File-Based Message Bus** - Reliable inter-terminal communication
- **Real-Time Dashboard** - Web UI to monitor progress at `localhost:8420`
- **Dry Run Mode** - Preview execution plans before running
- **Continuous Mode** - Loop indefinitely for ongoing development sessions
- **Configurable Parallelism** - Scale from 1 to 10 parallel agents
- **Artifact Sharing** - Automatic sharing of components between terminals

---

## Architecture

```
                           ┌─────────────────────────┐
                           │         USER            │
                           │   "Create an iOS app"   │
                           └───────────┬─────────────┘
                                       │
                                       ▼
                           ┌─────────────────────────┐
                           │      ORCHESTRATOR       │
                           │    (Python Core)        │
                           │  ┌─────────────────┐    │
                           │  │  Planner        │    │
                           │  │  Task Queue     │    │
                           │  │  Message Bus    │    │
                           │  └─────────────────┘    │
                           └───────────┬─────────────┘
                                       │
              ┌────────────────────────┼────────────────────────┐
              │                        │                        │
              ▼                        ▼                        ▼
    ┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
    │   TERMINAL T1   │      │   TERMINAL T2   │      │   TERMINAL T3   │
    │     UI/UX       │      │    Features     │      │      Docs       │
    │                 │      │                 │      │                 │
    │ ┌─────────────┐ │      │ ┌─────────────┐ │      │ ┌─────────────┐ │
    │ │swiftui-     │ │      │ │swift-       │ │      │ │tech-writer  │ │
    │ │crafter      │ │      │ │architect    │ │      │ │             │ │
    │ ├─────────────┤ │      │ ├─────────────┤ │      │ ├─────────────┤ │
    │ │react-       │ │      │ │node-        │ │      │ │marketing-   │ │
    │ │crafter      │ │      │ │architect    │ │      │ │strategist   │ │
    │ ├─────────────┤ │      │ ├─────────────┤ │      │ └─────────────┘ │
    │ │html-stylist │ │      │ │python-      │ │      └────────┬────────┘
    │ ├─────────────┤ │      │ │architect    │ │               │
    │ │design-      │ │      │ ├─────────────┤ │               │
    │ │system       │ │      │ │swiftdata-   │ │      ┌────────┴────────┐
    │ └─────────────┘ │      │ │expert       │ │      │   TERMINAL T4   │
    └────────┬────────┘      │ ├─────────────┤ │      │    Strategy     │
             │               │ │database-    │ │      │                 │
             │               │ │expert       │ │      │ ┌─────────────┐ │
             │               │ ├─────────────┤ │      │ │product-     │ │
             │               │ │ml-engineer  │ │      │ │thinker      │ │
             │               │ └─────────────┘ │      │ ├─────────────┤ │
             │               └────────┬────────┘      │ │monetization-│ │
             │                        │               │ │expert       │ │
             │                        │               │ └─────────────┘ │
             │                        │               └────────┬────────┘
             │                        │                        │
             └────────────────────────┼────────────────────────┘
                                      │
                                      ▼
                           ┌─────────────────────────┐
                           │    .orchestra/          │
                           │   (Runtime State)       │
                           │  ┌─────────────────┐    │
                           │  │  messages/      │    │
                           │  │  state/         │    │
                           │  │  artifacts/     │    │
                           │  └─────────────────┘    │
                           └─────────────────────────┘
```

### Communication Flow

Terminals communicate through a **file-based message bus**:

```
Terminal T1 ──request──▶ .orchestra/messages/t2_inbox.md ──▶ Terminal T2
                                                              │
                                                              │
Terminal T1 ◀──response── .orchestra/messages/t1_inbox.md ◀──┘

                    ┌──────────────────────────────────┐
All Terminals ◀───▶ │  .orchestra/messages/broadcast.md  │
                    └──────────────────────────────────┘
```

---

## Terminals

| Terminal | Role | Description | Subagents |
|----------|------|-------------|-----------|
| **T1** | UI/UX | Visual interfaces, styling, design systems | swiftui-crafter, react-crafter, html-stylist, design-system |
| **T2** | Features | Business logic, architecture, data layer | swift-architect, node-architect, python-architect, swiftdata-expert, database-expert, ml-engineer |
| **T3** | Docs | Documentation, marketing copy | tech-writer, marketing-strategist |
| **T4** | Strategy | Product vision, monetization | product-thinker, monetization-expert |

---

## Subagents

### UI/UX Specialists (T1)

| Agent | Model | Description |
|-------|-------|-------------|
| `swiftui-crafter` | Opus | SwiftUI views, modifiers, iOS 17+ features, accessibility |
| `react-crafter` | Opus | React/Next.js components, hooks, state management |
| `html-stylist` | Sonnet | HTML/CSS/Tailwind, responsive design, animations |
| `design-system` | Sonnet | Design tokens, color palettes, typography scales |

### Architecture & Features (T2)

| Agent | Model | Description |
|-------|-------|-------------|
| `swift-architect` | Opus | iOS/macOS architecture, MVVM, Clean Architecture |
| `node-architect` | Opus | Node.js/TypeScript backend, Express, NestJS |
| `python-architect` | Opus | Python apps, FastAPI, CLI tools, async patterns |
| `swiftdata-expert` | Opus | SwiftData/CoreData models, queries, migrations |
| `database-expert` | Opus | SQL, PostgreSQL, Prisma, database design |
| `ml-engineer` | Opus | Machine learning, model training, AI features |

### Documentation & Marketing (T3)

| Agent | Model | Description |
|-------|-------|-------------|
| `tech-writer` | Sonnet | README, API docs, tutorials, architecture docs |
| `marketing-strategist` | Sonnet | App Store copy, positioning, competitive analysis |

### Strategy & Business (T4)

| Agent | Model | Description |
|-------|-------|-------------|
| `product-thinker` | Opus | Feature ideation, MVP scope, roadmaps, PRDs |
| `monetization-expert` | Opus | Pricing strategy, business models, revenue |

---

## Installation

### Prerequisites

- **Python 3.11+**
- **Claude Code CLI** (`claude` command available in PATH)
- **Claude Max subscription** (for parallel terminal execution)

### Setup

```bash
# 1. Clone the repository
git clone https://github.com/martinovigiani/archon.git
cd archon

# 2. Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Verify Claude Code is available
claude --version
```

### Directory Structure After Setup

```
Archon/
├── .claude/
│   ├── settings.json          # Claude Code configuration
│   ├── settings.local.json    # Local overrides (gitignored)
│   └── agents/                # 14 subagent definitions
│       ├── swiftui-crafter.yml
│       ├── react-crafter.yml
│       └── ... (12 more)
├── orchestrator/              # Python core
│   ├── __init__.py
│   ├── __main__.py            # CLI entry point
│   ├── orchestrator.py        # Central coordinator
│   ├── planner.py             # Task planning with Claude
│   ├── task_queue.py          # Task management
│   ├── message_bus.py         # Inter-terminal messaging
│   ├── terminal.py            # Subprocess execution
│   └── dashboard.py           # FastAPI web UI
├── templates/
│   └── terminal_prompts/      # System prompts for T1-T4
├── .orchestra/                # Runtime state (created on run)
│   ├── messages/
│   ├── state/
│   └── artifacts/
├── Apps/                      # Generated projects
├── requirements.txt
└── README.md
```

---

## Usage

### Basic Execution

```bash
# Run a task
python -m orchestrator "Create an iOS app for habit tracking"

# Dry run - see the plan without executing
python -m orchestrator --dry-run "Create a todo app"

# With real-time dashboard
python -m orchestrator --dashboard "Create a speed test app"
```

### CLI Options

| Flag | Description | Default |
|------|-------------|---------|
| `--dry-run` | Show execution plan without running | Off |
| `--dashboard` | Start web dashboard at localhost:8420 | Off |
| `--continuous` | Loop indefinitely, prompt for new tasks | Off |
| `--max-retries N` | Retry failed tasks N times | 2 |
| `--parallel N` | Number of parallel terminals | 4 |
| `--timeout N` | Total timeout in seconds | 3600 |
| `-v, --verbose` | Detailed output | Off |
| `-q, --quiet` | Minimal output | Off |

### Examples

```bash
# Create an iOS app with all 4 terminals
python -m orchestrator "Create a meditation timer app with SwiftUI"

# Backend-focused task with verbose output
python -m orchestrator -v "Build a REST API for user authentication"

# Long-running session with continuous mode
python -m orchestrator --continuous --dashboard

# Controlled parallelism for complex tasks
python -m orchestrator --parallel 2 --max-retries 3 "Refactor the payment system"
```

### Dashboard

The web dashboard provides real-time visibility into:

- Terminal status and current tasks
- Message bus activity
- Generated artifacts
- Execution timeline

```bash
# Start dashboard standalone
python -m orchestrator.dashboard

# Or with orchestrator
python -m orchestrator --dashboard "your task"
```

Access at: **http://localhost:8420**

---

## Configuration

### Claude Settings (`.claude/settings.json`)

```json
{
  "permissions": {
    "allow": ["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
    "deny": []
  },
  "model": "opus",
  "subagents": {
    "max_parallel": 10
  }
}
```

### Local Overrides (`.claude/settings.local.json`)

Personal settings that won't be committed:

```json
{
  "model": "sonnet",
  "verbose": true
}
```

### Agent Configuration

Each subagent is defined in `.claude/agents/<name>.yml`:

```yaml
name: swiftui-crafter
color: orange
model: opus
tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Bash
description: |
  Expert SwiftUI developer for iOS/macOS UI components.
prompt: |
  You are a senior SwiftUI specialist...
```

---

## Code Standards

### Python

- **Version:** Python 3.11+
- **Typing:** Type hints on all functions
- **Formatter:** Black
- **Linter:** Ruff
- **Docstrings:** Google style
- **Async:** Use `async/await` for I/O operations

```python
async def fetch_user(user_id: str) -> User | None:
    """Fetch a user by ID.

    Args:
        user_id: The unique identifier for the user.

    Returns:
        The User object if found, None otherwise.
    """
    ...
```

### Swift (Generated Projects)

- **Version:** Swift 5.9+
- **UI:** SwiftUI
- **Data:** SwiftData
- **Pattern:** MVVM
- **Docs:** `///` for public APIs

```swift
/// A view displaying the user's profile information.
struct ProfileView: View {
    @State private var user: User?

    var body: some View {
        ...
    }
}
```

### TypeScript (Generated Projects)

- **Mode:** Strict
- **Linting:** ESLint + Prettier
- **Validation:** Zod for inputs
- **Errors:** Explicit handling

```typescript
import { z } from 'zod';

const UserSchema = z.object({
  id: z.string().uuid(),
  name: z.string().min(1),
  email: z.string().email(),
});

type User = z.infer<typeof UserSchema>;
```

---

## Contributing

We welcome contributions! Here's how to get started:

### Development Setup

```bash
# Fork and clone
git clone https://github.com/martinovigiani/archon.git
cd archon

# Create feature branch
git checkout -b feature/your-feature

# Install dev dependencies
pip install -r requirements-dev.txt

# Run tests
pytest

# Run linters
black .
ruff check .
```

### Guidelines

1. **One feature per branch** - Keep PRs focused
2. **Write tests** - Especially for orchestrator logic
3. **Follow code standards** - Black + Ruff for Python
4. **Update docs** - If you change behavior, update README
5. **Commit messages** - Clear, descriptive, atomic

### Adding a New Subagent

1. Create `.claude/agents/your-agent.yml`
2. Define `name`, `model`, `tools`, `description`, `prompt`
3. Add to appropriate terminal in `templates/terminal_prompts/`
4. Update CLAUDE.md with the new agent
5. Test with a relevant task

### Pull Request Process

1. Ensure tests pass
2. Update documentation
3. Request review from maintainers
4. Squash and merge

---

## Roadmap

- [ ] **v0.2** - Enhanced planning with task dependencies
- [ ] **v0.3** - Artifact caching for faster re-runs
- [ ] **v0.4** - Plugin system for custom subagents
- [ ] **v0.5** - Multi-project workspace support
- [ ] **v1.0** - Production-ready release

---

## Troubleshooting

### Claude Code not found

```bash
# Ensure claude is in PATH
which claude

# If not installed, follow Claude Code installation guide
```

### Permission denied errors

```bash
# Ensure .orchestra directory is writable
chmod -R 755 .orchestra
```

### Dashboard not starting

```bash
# Check if port 8420 is in use
lsof -i :8420

# Kill existing process if needed
kill -9 <PID>
```

### Subagent not responding

1. Check the agent YAML syntax
2. Verify model is available (opus/sonnet)
3. Check Claude Code subscription status

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## Acknowledgments

- Built with [Claude Code](https://claude.ai/code) by Anthropic
- Inspired by multi-agent orchestration patterns
- Thanks to all contributors

---

<p align="center">
  <sub>Made with Claude Code</sub>
</p>
