<p align="center">
  <img src="assets/archon-cli.png" alt="Archon CLI" width="700">
</p>

<h1 align="center">ARCHON</h1>

<p align="center">
  <strong>Multi-Agent Development Orchestrator</strong><br>
  <sub>Autonomous software development through coordinated AI agents</sub>
</p>

<p align="center">
  <a href="#features"><img src="https://img.shields.io/badge/Terminals-4-blue?style=flat-square" alt="4 Terminals"></a>
  <a href="#subagents"><img src="https://img.shields.io/badge/Subagents-14-green?style=flat-square" alt="14 Subagents"></a>
  <a href="#installation"><img src="https://img.shields.io/badge/Python-3.11+-yellow?style=flat-square" alt="Python 3.11+"></a>
  <a href="https://github.com/anthropics/claude-code"><img src="https://img.shields.io/badge/Powered_by-Claude_Code-orange?style=flat-square" alt="Claude Code"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-lightgrey?style=flat-square" alt="MIT License"></a>
</p>

---

## What is Archon?

Archon is an AI manager that coordinates **4 parallel Claude Code terminals** to build software autonomously. Instead of you switching between terminals and copying information manually, Archon does it for you.

```
You (CEO) → Archon (Manager) → 4 Terminals (Engineers) → Working Software
```

Give Archon a task like *"Create an iOS speed test app"* and it will:

1. **Plan** → Break down the task into parallel workstreams
2. **Delegate** → Assign work to specialized terminals
3. **Coordinate** → Share context between terminals automatically
4. **Deliver** → Produce a complete, working application

---

## Quick Start

```bash
# Clone and setup
git clone https://github.com/martino-vigiani/Archon.git
cd Archon
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run with dashboard
python -m orchestrator --dashboard --continuous "Create a habit tracking iOS app"
```

**Requirements:** Python 3.11+, [Claude Code CLI](https://github.com/anthropics/claude-code), Claude Max subscription

---

## Features

| Feature | Description |
|---------|-------------|
| **4 Parallel Terminals** | UI/UX, Features, Docs, Strategy - working simultaneously |
| **14 Expert Subagents** | Specialized AI for SwiftUI, React, databases, ML, marketing... |
| **Smart Coordination** | Orchestrator understands outputs and shares context automatically |
| **Real-Time Dashboard** | Monitor progress at `localhost:8420` |
| **Continuous Mode** | Keep building with `--continuous` flag |
| **Report System** | Structured reports enable intelligent cross-terminal coordination |

---

## Architecture

```
                        YOU (CEO)
                          │
                          ▼
            ┌─────────────────────────┐
            │        ARCHON           │
            │    (AI Manager)         │
            │  • Plans tasks          │
            │  • Reads reports        │
            │  • Coordinates work     │
            └───────────┬─────────────┘
                        │
       ┌────────────────┼────────────────┬────────────────┐
       ▼                ▼                ▼                ▼
   ┌───────┐        ┌───────┐        ┌───────┐        ┌───────┐
   │  T1   │        │  T2   │        │  T3   │        │  T4   │
   │ UI/UX │        │ Feat  │        │ Docs  │        │ Ideas │
   └───┬───┘        └───┬───┘        └───┬───┘        └───┬───┘
       │                │                │                │
       ▼                ▼                ▼                ▼
   swiftui-         swift-           tech-           product-
   crafter          architect        writer          thinker
   react-           node-            marketing-      monetization-
   crafter          architect        strategist      expert
   html-            python-
   stylist          architect
   design-          swiftdata-
   system           expert
                    database-
                    expert
                    ml-engineer
```

---

## Terminals & Subagents

### T1 - UI/UX
| Subagent | Specialty |
|----------|-----------|
| `swiftui-crafter` | iOS/macOS SwiftUI interfaces |
| `react-crafter` | React/Next.js components |
| `html-stylist` | HTML/CSS/Tailwind styling |
| `design-system` | Design tokens, colors, typography |

### T2 - Features
| Subagent | Specialty |
|----------|-----------|
| `swift-architect` | iOS architecture, MVVM, Clean Architecture |
| `node-architect` | Node.js/TypeScript backends |
| `python-architect` | Python apps, FastAPI, async |
| `swiftdata-expert` | SwiftData/CoreData persistence |
| `database-expert` | SQL, PostgreSQL, Prisma |
| `ml-engineer` | Machine learning, AI features |

### T3 - Documentation
| Subagent | Specialty |
|----------|-----------|
| `tech-writer` | README, API docs, tutorials |
| `marketing-strategist` | App Store copy, positioning |

### T4 - Strategy
| Subagent | Specialty |
|----------|-----------|
| `product-thinker` | MVP scope, roadmaps, PRDs |
| `monetization-expert` | Pricing, business models |

---

## Usage

### Basic Commands

```bash
# Simple task
python -m orchestrator "Create a todo app with SwiftUI"

# With dashboard (recommended)
python -m orchestrator --dashboard "Build a REST API"

# Continuous mode - keeps asking for new tasks
python -m orchestrator --dashboard --continuous

# Dry run - see the plan without executing
python -m orchestrator --dry-run "Create a meditation app"

# Work on existing project
python -m orchestrator --project ./MyApp "Add dark mode"
```

### CLI Options

| Flag | Description |
|------|-------------|
| `--dashboard` | Start web UI at localhost:8420 |
| `--continuous` | Keep running, prompt for new tasks |
| `--dry-run` | Show plan without executing |
| `--project PATH` | Work on existing project |
| `--parallel N` | Number of terminals (default: 4) |
| `--max-retries N` | Retry failed tasks (default: 2) |
| `--timeout N` | Max execution time in seconds |
| `-v, --verbose` | Detailed output |
| `-q, --quiet` | Minimal output |

---

## How It Works

1. **You give a task** → "Create a speed test iOS app"

2. **Archon plans** → Uses Claude to break into subtasks:
   - T1: Design UI components
   - T2: Implement network speed logic
   - T3: Write documentation
   - T4: Define MVP scope

3. **Terminals execute in parallel** → Each writes a structured report

4. **Archon coordinates** → Reads reports, shares context:
   > "T2 finished the SpeedTestService. T1, you can now bind the UI to it."

5. **Result** → Complete, working application

---

## Project Structure

```
Archon/
├── orchestrator/           # Core Python package
│   ├── orchestrator.py     # Main coordinator
│   ├── planner.py          # Task planning with Claude
│   ├── terminal.py         # Claude Code subprocess
│   ├── report_manager.py   # Structured reports
│   ├── message_bus.py      # Inter-terminal messaging
│   ├── task_queue.py       # Task management
│   └── dashboard.py        # FastAPI web UI
├── templates/
│   └── terminal_prompts/   # System prompts for T1-T4
├── .claude/
│   └── agents/             # 14 subagent definitions
├── .orchestra/             # Runtime state (gitignored)
└── Apps/                   # Generated projects (gitignored)
```

---

## Configuration

### Claude Settings (`.claude/settings.json`)

```json
{
  "permissions": {
    "allow": ["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
    "deny": []
  },
  "model": "opus"
}
```

### Custom Subagent (`.claude/agents/my-agent.yml`)

```yaml
name: my-agent
model: opus
tools: [Read, Write, Edit, Glob, Grep, Bash]
description: |
  What this agent specializes in.
prompt: |
  You are an expert in...
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `claude: command not found` | Install [Claude Code CLI](https://github.com/anthropics/claude-code) |
| Rate limit hit | Wait for reset time shown in error |
| Dashboard not loading | Check if port 8420 is free: `lsof -i :8420` |
| Task stuck | Check `.orchestra/` for state, restart orchestrator |

---

## Contributing

```bash
# Fork and clone
git clone https://github.com/YOUR_USERNAME/Archon.git

# Create feature branch
git checkout -b feature/my-feature

# Make changes, then
git commit -m "Add my feature"
git push origin feature/my-feature
```

PRs welcome! Please follow existing code style (Black + Ruff for Python).

---

## License

MIT License - see [LICENSE](LICENSE)

---

<p align="center">
  <sub>Built with <a href="https://github.com/anthropics/claude-code">Claude Code</a> by Anthropic</sub>
</p>
