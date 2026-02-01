# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## What is Archon?

Multi-agent orchestration system for autonomous software development. Coordinates **4 parallel Claude Code terminals** using a **3-phase execution model**.

```
User (CEO) → Archon (Manager) → 4 Terminals (Engineers) → Working Software
```

---

## Commands

### Run Orchestrator

```bash
# Basic execution
python -m orchestrator "Create an iOS app for habit tracking"

# With dashboard (recommended) - opens localhost:8420
python -m orchestrator --dashboard "Build a REST API"

# Continuous mode - keeps asking for new tasks
python -m orchestrator --dashboard --continuous

# Dry run - see the plan without executing
python -m orchestrator --dry-run "Create a meditation app"

# Work on existing project
python -m orchestrator --project ./Apps/MyApp "Add dark mode"

# Resume interrupted session
python -m orchestrator --resume
```

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

## Architecture: 3-Phase Parallel Execution

### Core Flow

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

### Key Components (`orchestrator/`)

| File | Purpose |
|------|---------|
| `orchestrator.py` | Main coordinator - phase-aware execution |
| `planner.py` | Parallel-first task planning |
| `terminal.py` | Claude Code subprocess wrapper |
| `task_queue.py` | Phase-based task management |
| `report_manager.py` | Structured reports & interface contracts |
| `message_bus.py` | Inter-terminal communication |
| `dashboard.py` | FastAPI web UI at localhost:8420 |

### Terminal Principles

| Terminal | Principle | Prompt File |
|----------|-----------|-------------|
| T1 | "Build first, integrate later" | `templates/terminal_prompts/t1_uiux.md` |
| T2 | "Build foundation fast" + tests | `templates/terminal_prompts/t2_features.md` |
| T3 | "Document as it's built" | `templates/terminal_prompts/t3_docs.md` |
| T4 | "Guide, don't block" | `templates/terminal_prompts/t4_ideas.md` |

### Interface Contracts

Terminals don't wait - they communicate via contracts:

```swift
// T1 creates UI and documents expectations:
// T1 INTERFACE CONTRACT
// T2: Please implement a service matching this
struct UserDisplayData {
    let id: UUID
    let name: String
}

// T2 reads .orchestra/reports/t1/ and implements matching APIs
```

---

## Work Philosophy

This project uses a **maximally agentic** approach:

1. **USE SUBAGENTS PROACTIVELY** — Delegate to specialists
2. **PARALLELIZE** — Launch multiple subagents in parallel (max 10)
3. **BE AUTONOMOUS** — Make decisions, don't ask for trivial matters
4. **CONTEXT MANAGEMENT** — Use subagents to keep main context clean
5. **QUALITY > SPEED** — Better to do it right than fast

---

## Subagents — USE THEM!

14 specialized subagents in `.claude/agents/`. **USE THEM** for domain-specific tasks.

| Domain | Subagent |
|--------|----------|
| UI SwiftUI/iOS | `swiftui-crafter` |
| UI React/Next.js | `react-crafter` |
| HTML/CSS/Tailwind | `html-stylist` |
| Colors/Fonts/Tokens | `design-system` |
| iOS Architecture | `swift-architect` |
| Node.js Architecture | `node-architect` |
| Python Architecture | `python-architect` |
| SwiftData/CoreData | `swiftdata-expert` |
| Database/SQL/Prisma | `database-expert` |
| ML/AI/Training | `ml-engineer` |
| Docs/README | `tech-writer` |
| Marketing/App Store | `marketing-strategist` |
| Feature/Roadmap/MVP | `product-thinker` |
| Pricing/Business Model | `monetization-expert` |

### Mandatory Rules

```
RULE 1: Domain-specific task → USE THE SUBAGENT
RULE 2: Complex multi-domain → LAUNCH MULTIPLE IN PARALLEL
RULE 3: NEVER do iOS UI without swiftui-crafter
RULE 4: NEVER make architecture decisions without appropriate architect
```

---

## MCP — Context7

Available but **HAS API COST**. Use sparingly.

```
WHEN TO USE:
✅ Official framework/library documentation
✅ API references you don't know well

WHEN NOT TO USE:
❌ Things you already know
❌ Generic best practices
❌ As first resort
```

---

## Autonomy

### DO WITHOUT ASKING
```
✅ Create/modify/delete files
✅ Launch subagents
✅ Install dependencies (pip, npm)
✅ Refactor, add docs, fix bugs
✅ Format and lint code
```

### ASK BEFORE
```
⚠️ Changing fundamental architecture
⚠️ Deleting working functionality
⚠️ Major version dependency changes
⚠️ Spending money (external APIs)
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
```
