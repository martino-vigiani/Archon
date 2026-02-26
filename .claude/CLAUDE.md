# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## What is Archon?

Organic multi-agent orchestration system for autonomous software development. Coordinates **5 parallel Claude Code terminals** through **flow-based execution** where work emerges naturally rather than following rigid phases.

```
User (CEO) --> Archon (Gardener) --> 5 Terminals (Craftspeople) --> Working Software
```

**GitHub:** https://github.com/martino-vigiani/Archon

---

## Commands

### Run Orchestrator

```bash
# Basic execution
python -m orchestrator "Create an iOS app for habit tracking"

# With dashboard (recommended) - opens localhost:8420
python -m orchestrator --dashboard "Build a REST API"

# Interactive chat mode - control execution in real-time
python -m orchestrator --chat "Create a meditation app"

# Continuous mode - keeps asking for new tasks
python -m orchestrator --dashboard --continuous

# Dry run - see the plan without executing
python -m orchestrator --dry-run "Create a meditation app"

# Work on existing project
python -m orchestrator --project ./Apps/MyApp "Add dark mode"

# Disable T5 testing (saves API limits)
python -m orchestrator --no-testing "Quick prototype"

# Combine flags
python -m orchestrator --chat --dashboard "Build a full-stack app"

# Resume interrupted session
python -m orchestrator --resume
```

### CLI Flags

| Flag | Description |
|------|-------------|
| `--chat` | Interactive Manager Chat (control execution in real-time) |
| `--dashboard` | Start web UI at localhost:8420 |
| `--continuous` | Keep running, prompt for new tasks |
| `--dry-run` | Show plan without executing |
| `--project PATH` | Work on existing project |
| `--no-testing` | Disable T5 QA terminal (saves API limits) |
| `--max-retries N` | Retry failed tasks (default: 2) |
| `--timeout N` | Max execution time in seconds |
| `-v, --verbose` | Detailed output |
| `-q, --quiet` | Minimal output |

### Development

```bash
# Setup
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Format & Lint
black orchestrator/
ruff check orchestrator/
```

---

## Philosophy: Organic Flow

Archon rejects rigid phase gates. Instead, work **flows** naturally like a living system.

### Core Concepts

| Concept | Old Way | Archon Way |
|---------|---------|------------|
| **Intent, not Task** | "T1: Build ProfileView" | Manager broadcasts intent, terminals interpret |
| **Flow, not Phase** | Phase 0 -> 1 -> 2 -> 3 | Work flows continuously, no gates |
| **Observation, not Distribution** | Manager assigns tasks | Manager watches and intervenes surgically |
| **Negotiation, not Assignment** | Tasks assigned to terminals | Terminals negotiate among themselves |
| **Quality Gradient** | Done/Not Done | Work exists on 0.0-1.0 spectrum |

### The Manager as Gardener

The Manager does not command. It **cultivates**:

- Observes what's growing
- Prunes what isn't working
- Waters what shows promise
- Protects delicate growth
- Knows when to intervene vs let be

### Manager Interventions

| Intervention | When | Example |
|--------------|------|---------|
| **AMPLIFY** | Something is working well | "T1's approach is excellent, all terminals adopt similar patterns" |
| **REDIRECT** | Duplicate or wasted effort | "T2, stop - T1 already solved this better" |
| **MEDIATE** | Terminals disagree | "T1 and T2 need to align on this interface" |
| **INJECT** | Gap nobody's filling | "Nobody's handling auth - T2, take this" |
| **PRUNE** | Approach isn't working | "Abandon this direction, try something else" |

---

## Terminal Personalities

Each terminal has a **personality**, not a rigid role. They can venture into any domain when needed.

| Terminal | Personality | Home Domain | Superpower |
|----------|-------------|-------------|------------|
| **T1** | The Craftsman | UI/UX | Makes anything beautiful |
| **T2** | The Architect | Backend/Systems | Makes anything reliable |
| **T3** | The Narrator | Documentation | Explains anything clearly |
| **T4** | The Strategist | Product/Vision | Sees the whole board |
| **T5** | The Skeptic | QA/Testing | Finds any flaw |

### Personality Principles

**T1 - The Craftsman**
> "I see the user's hands on this interface. Every pixel matters."

**T2 - The Architect**
> "I see the forces acting on this system. Every foundation must hold."

**T3 - The Narrator**
> "I see the story this code tells. Every explanation illuminates."

**T4 - The Strategist**
> "I see the map from above. Every decision shapes the journey."

**T5 - The Skeptic**
> "I see what could break. Every assumption must be tested."

---

## Quality Gradient

Work is not binary (done/not-done). It exists on a **quality spectrum**:

| Quality | Description | Action |
|---------|-------------|--------|
| **0.0-0.2** | Sketch/Concept | Needs substantial work |
| **0.2-0.4** | Draft | Structure exists, needs refinement |
| **0.4-0.6** | Working | Functional but rough edges |
| **0.6-0.8** | Solid | Ready for integration |
| **0.8-0.9** | Polished | Production-ready |
| **0.9-1.0** | Excellent | Exceeds expectations |

Terminals report quality levels. Manager decides when to **AMPLIFY** (push higher) or **accept** (good enough for now).

---

## Key Components (`orchestrator/`)

| File | Purpose |
|------|---------|
| `orchestrator.py` | Main coordinator - observes and intervenes |
| `planner.py` | Intent broadcasting, not task assignment |
| `terminal.py` | Claude Code subprocess wrapper |
| `task_queue.py` | Flow-based work management |
| `report_manager.py` | Quality gradient tracking |
| `message_bus.py` | Inter-terminal negotiation |
| `config.py` | Configuration and terminal definitions |
| `cli_display.py` | Colors, terminal badges, quality bars |
| `dashboard.py` | FastAPI web UI at localhost:8420 |
| `manager_chat.py` | Interactive chat REPL |
| `sync_manager.py` | Heartbeat coordination |
| `contract_manager.py` | Interface negotiation |
| `manager_intelligence.py` | Intervention decisions |
| `validator.py` | Continuous validation |
| `logger.py` | Event logging system |

---

## Work Philosophy

This project uses a **maximally agentic** approach:

1. **USE SUBAGENTS PROACTIVELY** - Delegate to specialists
2. **PARALLELIZE** - Launch multiple subagents in parallel (max 10)
3. **BE AUTONOMOUS** - Make decisions, don't ask for trivial matters
4. **CONTEXT MANAGEMENT** - Use subagents to keep main context clean
5. **QUALITY > SPEED** - Better to do it right than fast

---

## Subagents - ALL TERMINALS CAN USE ALL SUBAGENTS

20 specialized subagents in `.claude/agents/`. **Every terminal can invoke any subagent** based on the work at hand.

### UI/Frontend

| Domain | Subagent |
|--------|----------|
| UI SwiftUI/iOS | `swiftui-crafter` |
| UI React/Next.js | `react-crafter` |
| HTML/CSS/Tailwind | `html-stylist` |
| Colors/Fonts/Tokens | `design-system` |
| Web UI Design | `web-ui-designer` |
| Dashboard/API sync | `dashboard-architect` |

### Architecture

| Domain | Subagent |
|--------|----------|
| iOS Architecture | `swift-architect` |
| Node.js Architecture | `node-architect` |
| Python Architecture | `python-architect` |

### Data/Backend

| Domain | Subagent |
|--------|----------|
| SwiftData/CoreData | `swiftdata-expert` |
| Database/SQL/Prisma | `database-expert` |
| ML/AI/Training | `ml-engineer` |

### Testing/Quality

| Domain | Subagent |
|--------|----------|
| Advanced Testing | `test-genius` |

### Documentation/Strategy

| Domain | Subagent |
|--------|----------|
| Docs/README | `tech-writer` |
| Marketing/App Store | `marketing-strategist` |
| Feature/Roadmap/MVP | `product-thinker` |
| Pricing/Business Model | `monetization-expert` |

### Tooling/Prompts

| Domain | Subagent |
|--------|----------|
| Claude Code Tools/MCP | `claude-code-toolsmith` |
| Prompt Engineering | `prompt-craftsman` |
| CLI UX Design | `cli-ux-master` |

### Subagent Access Rules

```
RULE 1: ANY terminal can call ANY subagent
RULE 2: Use the right tool for the job, not "your" tool
RULE 3: Negotiate with other terminals if subagent overlap occurs
RULE 4: Quality of output > ownership of domain
```

---

## MCP - Context7

Available but **HAS API COST**. Use sparingly.

```
WHEN TO USE:
- Official framework/library documentation
- API references you don't know well

WHEN NOT TO USE:
- Things you already know
- Generic best practices
- As first resort
```

## MCP - XcodeBuildMCP

**SEMPRE DISPONIBILE. USALO PER TUTTO IL LAVORO iOS/Xcode.**

XcodeBuildMCP permette ai terminali di gestire autonomamente build, test e deploy di progetti iOS/Swift/SwiftUI. Ogni terminale deve usare XcodeBuildMCP invece di comandi xcodebuild manuali.

```
CAPACITA:
- Build e compilazione progetti Xcode (con fix automatico errori)
- Build incrementali per compilazione veloce
- Test su simulatore iOS con screenshot
- Deploy su device fisici via USB/Wi-Fi
- Gestione completa ciclo di sviluppo iOS

QUANDO USARLO:
- SEMPRE quando si lavora su progetti iOS/Swift/SwiftUI
- Per buildare, testare, deployare qualsiasi progetto Xcode
- Per catturare screenshot dal simulatore
- Per debug errori di compilazione

REGOLA: Se il progetto generato e' iOS, i terminali DEVONO usare XcodeBuildMCP
```

---

## Autonomy

### DO WITHOUT ASKING
```
- Create/modify/delete files
- Launch subagents
- Install dependencies (pip, npm)
- Refactor, add docs, fix bugs
- Format and lint code
- Negotiate with other terminals
```

### ASK BEFORE
```
- Changing fundamental architecture
- Deleting working functionality
- Major version dependency changes
- Spending money (external APIs)
```

---

## Code Standards

### Python (orchestrator)
- Python 3.11+, type hints ALWAYS
- Black formatter, Ruff linter
- Google-style docstrings
- Async/await for I/O

### Swift (generated projects)
- Swift 5.9+, SwiftUI, SwiftData
- MVVM pattern
- Unit tests required

### Node.js/TypeScript (generated projects)
- TypeScript strict mode
- ESLint + Prettier
- Zod for validation

---

## Quick Reference

```bash
# Launch subagent
"Use the swiftui-crafter subagent to create..."

# Launch parallel subagents
"Launch swift-architect, swiftui-crafter and swiftdata-expert in parallel for..."

# See subagents
/agents

# Run with chat + dashboard
python -m orchestrator --chat --dashboard "Your task"
```
