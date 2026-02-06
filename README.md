<p align="center">
  <img src="assets/archon-cli.png" alt="Archon CLI" width="700">
</p>

<h1 align="center">ARCHON</h1>

<p align="center">
  <strong>Organic Multi-Agent Development</strong><br>
  <sub>Software that grows through collaborative intelligence</sub>
</p>

<p align="center">
  <a href="#terminals"><img src="https://img.shields.io/badge/Terminals-5-blue?style=flat-square" alt="5 Terminals"></a>
  <a href="#subagents"><img src="https://img.shields.io/badge/Subagents-20-green?style=flat-square" alt="20 Subagents"></a>
  <a href="#installation"><img src="https://img.shields.io/badge/Python-3.11+-yellow?style=flat-square" alt="Python 3.11+"></a>
  <a href="https://github.com/anthropics/claude-code"><img src="https://img.shields.io/badge/Powered_by-Claude_Code-orange?style=flat-square" alt="Claude Code"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-lightgrey?style=flat-square" alt="MIT License"></a>
</p>

---

## What is Archon?

Archon is a **gardener of intelligence** - it cultivates 5 parallel Claude Code terminals, each with a distinct personality, and guides them toward creating software through organic collaboration rather than rigid command.

```
                    ┌─────────────────┐
                    │     ARCHON      │
                    │   The Gardener  │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │   Observes   │   Nurtures   │
              │              │              │
    ┌─────────┴─────────────────────────────┴─────────┐
    │                                                 │
    │   T1          T2          T3          T4       T5
    │   The         The         The         The      The
    │   Craftsman   Architect   Narrator    Strategist Skeptic
    │                                                 │
    └─────────────────────┬───────────────────────────┘
                          │
              ┌───────────┴───────────┐
              │     NEGOTIATIONS      │
              │   Contracts & Flow    │
              └───────────────────────┘
```

Give Archon an **intent** like *"Create an iOS counter app"* and watch it:

1. **Seed** - Plant the intent across all terminals
2. **Grow** - Terminals develop their specialties organically
3. **Negotiate** - Craftspeople exchange contracts and resolve differences
4. **Cultivate** - The gardener observes quality and intervenes when needed
5. **Harvest** - Complete, tested, documented application emerges

---

## Quick Start

```bash
# Clone and setup
git clone https://github.com/martino-vigiani/Archon.git
cd Archon
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run with dashboard (recommended)
python -m orchestrator --dashboard "Create a habit tracking iOS app"
```

### Requirements

- **Python 3.11+**
- **[Claude Code CLI](https://github.com/anthropics/claude-code)** installed and in PATH
- **Any paid Claude subscription** (Pro, Max, Team)
  - Recommended: **Max 5x** for heavy parallel usage without hitting rate limits

---

## The Organic Philosophy

Archon rejects the factory model of software development. Instead of treating AI agents as assembly line workers executing predefined tasks, Archon cultivates them as craftspeople with distinct personalities and expertise.

### Core Principles

| Traditional | Organic |
|-------------|---------|
| **Task** - "Do exactly this" | **Intent** - "We want to achieve this" |
| **Phase** - "First A, then B, then C" | **Flow** - "Work naturally, negotiate as needed" |
| **Distribution** - "Manager assigns all work" | **Observation** - "Terminals choose, manager guides" |
| **Binary Status** - "Done or not done" | **Quality Gradient** - "0.0 to 1.0 readiness" |

### Why Organic?

Traditional orchestration systems fail because they try to predict every dependency upfront. Real software development is emergent - the UI reveals needed APIs, tests expose edge cases, documentation clarifies requirements.

Archon embraces this uncertainty. Terminals work in their natural rhythm, communicating through contracts and negotiations. The manager watches quality gradients and intervenes only when the garden needs tending.

---

## Terminal Personalities

Each terminal is a craftsperson with a distinct worldview and approach:

### T1 - The Craftsman

*"I make things beautiful. Every pixel, every interaction, every moment of delight."*

The Craftsman obsesses over user experience. They build interfaces that feel alive, creating with mock data first so nothing blocks their creative flow. They define what the user will see and touch.

| Focus | Subagents |
|-------|-----------|
| Visual Design | `swiftui-crafter`, `react-crafter` |
| Styling | `html-stylist`, `design-system` |

### T2 - The Architect

*"I make things reliable. Every foundation solid, every system resilient, every edge case handled."*

The Architect builds what others depend on. They create the models, services, and tests that make software trustworthy. When T1 proposes an interface, T2 makes it real and bulletproof.

| Focus | Subagents |
|-------|-----------|
| Architecture | `swift-architect`, `node-architect`, `python-architect` |
| Data | `swiftdata-expert`, `database-expert` |
| Intelligence | `ml-engineer` |

### T3 - The Narrator

*"I explain things clearly. Every concept accessible, every decision documented, every user guided."*

The Narrator watches the system grow and captures its story. They write documentation that helps users understand, onboarding that welcomes newcomers, and technical specs that preserve knowledge.

| Focus | Subagents |
|-------|-----------|
| Documentation | `tech-writer` |
| Communication | `marketing-strategist` |

### T4 - The Strategist

*"I see the whole board. Every move connected, every decision aligned, every path leading somewhere."*

The Strategist never blocks - they advise. Early on they broadcast MVP scope so everyone knows the destination. Throughout development they watch for scope creep, suggest pivots, and ensure the team builds the right thing.

| Focus | Subagents |
|-------|-----------|
| Product | `product-thinker` |
| Business | `monetization-expert` |

### T5 - The Skeptic

*"I find every flaw. Every assumption challenged, every path tested, every weakness exposed."*

The Skeptic is the team's immune system. They don't wait until the end - they probe continuously, running builds, checking contracts, finding issues before they compound. When they find problems, they report to the responsible terminal.

| Focus | Subagents |
|-------|-----------|
| Quality | `test-genius` |
| Validation | `swift-architect`, `node-architect`, `python-architect` |

---

## How Flow Works

Unlike rigid phase systems, Archon terminals flow naturally:

```
GROWTH PATTERN (not a phase - terminals flow at their own pace)

    T4 broadcasts intent
           │
           ├──────────────────────────────────────────────┐
           │                                              │
    T1 creates UI          T2 builds foundation          T3 watches
    with mock data         with real logic               and documents
           │                      │                            │
           │                      │                            │
           └──────── negotiate ───┘                            │
                         │                                     │
              contracts form organically                       │
                         │                                     │
           ┌─────────────┴─────────────┐                      │
           │                           │                      │
    T1 connects to              T2 adapts to                  │
    real APIs                   UI needs                      │
           │                           │                      │
           └───────────────────────────┴──────────────────────┘
                                │
                         T5 validates continuously
                         (builds every 2 min)
                                │
                         Quality: 0.0 → 1.0
                                │
                         When ready, harvest
```

### Quality Gradient

Instead of binary "done/not done", Archon tracks quality on a gradient:

| Quality | Meaning |
|---------|---------|
| 0.0-0.3 | Early growth - structure forming |
| 0.3-0.6 | Developing - core functionality emerging |
| 0.6-0.8 | Maturing - integration happening |
| 0.8-0.95 | Ripening - testing and polish |
| 0.95-1.0 | Ready to harvest |

The gardener watches this gradient and intervenes when growth stalls or quality drops.

---

## Manager Interventions

The gardener doesn't dictate - they tend. Five types of intervention:

### AMPLIFY

*"T2 is making great progress on the API. T1, consider connecting to their endpoints now."*

When a terminal produces something valuable, the manager amplifies it - broadcasting the artifact and suggesting others leverage it.

### REDIRECT

*"T1, the login screen is out of MVP scope. Focus on the main counter interface."*

When a terminal drifts from intent, the manager gently redirects without killing their momentum.

### MEDIATE

*"T1 expects `UserProfile.avatarURL`, but T2 implemented `UserProfile.imageData`. Let's negotiate."*

When contracts conflict, the manager facilitates resolution rather than dictating a solution.

### INJECT

*"Nobody is handling the edge case where the counter overflows. T2, consider adding bounds checking."*

When the manager observes a gap, they inject a suggestion without forcing assignment.

### PRUNE

*"T3, the API documentation for the deprecated endpoint can be removed."*

When something is no longer serving the system, the manager suggests pruning to keep the garden healthy.

---

## Usage

### Basic Commands

```bash
# Simple task
python -m orchestrator "Create a todo app with SwiftUI"

# With dashboard (recommended)
python -m orchestrator --dashboard "Build a REST API"

# Interactive chat mode - guide the growth in real-time
python -m orchestrator --chat "Create a meditation app"

# Continuous mode - keeps growing new features
python -m orchestrator --dashboard --continuous

# Dry run - see the growth plan without executing
python -m orchestrator --dry-run "Create a meditation app"

# Work on existing project
python -m orchestrator --project ./MyApp "Add dark mode"

# Disable T5 validation (saves API limits)
python -m orchestrator --no-testing "Quick prototype"

# Combine flags
python -m orchestrator --chat --dashboard "Build a full-stack app"
```

### CLI Options

| Flag | Description |
|------|-------------|
| `--chat` | Interactive Gardener Chat (guide growth in real-time) |
| `--dashboard` | Start web UI at localhost:8420 |
| `--continuous` | Keep running, prompt for new intents |
| `--dry-run` | Show growth plan without executing |
| `--project PATH` | Work on existing project |
| `--no-testing` | Disable T5 validation (saves API limits) |
| `--max-retries N` | Retry failed growth (default: 2) |
| `--timeout N` | Max growth time in seconds |
| `-v, --verbose` | Detailed output |
| `-q, --quiet` | Minimal output |

### Gardener Chat (`--chat`)

Interactive REPL to guide the organic growth:

```
> status              # Overall garden health
> status t1           # Health of specific terminal
> pause               # Pause growth
> resume              # Resume growth
> inject: Add login   # Inject new intent
> cancel <task_id>    # Cancel pending growth
> tasks               # List all active growth
> reports             # Show terminal reports
> What has T2 built?  # Natural language questions (via Claude)
> help                # Show all commands
```

---

## Subagents

20 specialist subagents that terminals can invoke for deep expertise:

| Domain | Subagent | Specialty |
|--------|----------|-----------|
| iOS UI | `swiftui-crafter` | SwiftUI interfaces, animations |
| Web UI | `react-crafter` | React/Next.js components |
| Styling | `html-stylist` | HTML/CSS/Tailwind |
| Design | `design-system` | Tokens, colors, typography |
| Web Design | `web-ui-designer` | Visual design, UX, responsive |
| Dashboards | `dashboard-architect` | Real-time dashboards, API sync |
| iOS | `swift-architect` | MVVM, Clean Architecture |
| Node.js | `node-architect` | TypeScript backends |
| Python | `python-architect` | FastAPI, async patterns |
| iOS Data | `swiftdata-expert` | SwiftData/CoreData |
| Database | `database-expert` | SQL, PostgreSQL, Prisma |
| ML/AI | `ml-engineer` | Machine learning features |
| Testing | `test-genius` | Edge cases, orchestrator tests |
| Docs | `tech-writer` | README, API docs |
| Marketing | `marketing-strategist` | App Store, positioning |
| Product | `product-thinker` | MVP, roadmaps |
| Business | `monetization-expert` | Pricing, business models |
| CLI | `cli-ux-master` | Terminal UX, argument design |
| Tooling | `claude-code-toolsmith` | MCP servers, Claude Code integration |
| Prompts | `prompt-craftsman` | System prompts, prompt engineering |

---

## Documentation

| Guide | Purpose |
|-------|---------|
| **[ARCHITECTURE.md](docs/ARCHITECTURE.md)** | System architecture and organic model |
| **[API_REFERENCE.md](docs/API_REFERENCE.md)** | Dashboard API endpoints |
| **[DESIGN_DECISIONS.md](docs/DESIGN_DECISIONS.md)** | Key architectural decisions and rationale |
| **[SETUP.md](docs/SETUP.md)** | Detailed setup and configuration guide |
| **[PRD.md](docs/PRD.md)** | Product requirements document |
| **[diagrams.md](docs/diagrams.md)** | Visual diagrams for the architecture |

---

## Project Structure

```
Archon/
├── orchestrator/                # Core Python package
│   ├── orchestrator.py          # The Gardener
│   ├── planner.py               # Intent interpretation
│   ├── terminal.py              # Terminal personality wrapper
│   ├── task_queue.py            # Organic growth management
│   ├── message_bus.py           # Inter-terminal negotiation
│   ├── report_manager.py        # Artifact tracking
│   │
│   │── # Organic Collaboration Components
│   ├── sync_manager.py          # Quality gradient tracking
│   ├── contract_manager.py      # Negotiation contracts
│   ├── manager_intelligence.py  # Intervention decisions
│   ├── validator.py             # Continuous validation
│   │
│   ├── manager_chat.py          # Gardener chat REPL
│   └── dashboard.py             # Growth visualization UI
│
├── templates/
│   └── terminal_prompts/        # Terminal personality definitions
│       ├── t1_uiux.md           # The Craftsman
│       ├── t2_features.md       # The Architect
│       ├── t3_docs.md           # The Narrator
│       ├── t4_ideas.md          # The Strategist
│       └── t5_qa.md             # The Skeptic
│
├── .claude/
│   └── agents/                  # 20 subagent definitions
│
├── .orchestra/                  # Runtime state (gitignored)
│   ├── state/                   # Terminal heartbeats
│   ├── contracts/               # Negotiation contracts
│   ├── reports/                 # Terminal artifacts
│   ├── messages/                # Inter-terminal messages
│   ├── tasks/                   # Growth queue
│   └── qa/                      # T5 validation data
│
└── Apps/                        # Generated projects (gitignored)
```

---

## Example: Growing a Counter App

**Intent:** *"Create a simple iOS counter app"*

**How Archon grows it:**

```
1. The Strategist (T4) broadcasts: "MVP = increment, decrement, display"

2. The Craftsman (T1) begins:
   - Creates CounterView.swift with mock data
   - Proposes contract: CounterViewModel with count, increment(), decrement()

3. The Architect (T2) simultaneously:
   - Builds Counter.swift model with bounds checking
   - Creates CounterViewModel matching T1's contract
   - Writes unit tests

4. The Narrator (T3) watches and documents:
   - Creates README.md describing the app
   - Documents the Counter model API

5. The Skeptic (T5) validates continuously:
   - Runs swift build every 2 minutes
   - Verifies T1's contract matches T2's implementation
   - Reports quality gradient: 0.4 → 0.7 → 0.95

6. Integration flows naturally:
   - T1 connects to T2's real ViewModel
   - T2 adjusts API based on T1's needs
   - Quality reaches 0.95+

7. Harvest: Complete, tested, documented app
```

**What emerges:**

```
Apps/CounterApp/
├── Package.swift
├── README.md
├── CounterApp/
│   ├── CounterAppApp.swift
│   ├── Models/Counter.swift
│   ├── ViewModels/CounterViewModel.swift
│   └── Views/CounterView.swift
└── CounterAppTests/
    ├── CounterTests.swift
    └── CounterViewModelTests.swift
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `claude: command not found` | Install [Claude Code CLI](https://github.com/anthropics/claude-code) |
| Rate limit hit | Use Max 5x subscription or use `--no-testing` |
| Dashboard not loading | Check if port 8420 is free: `lsof -i :8420` |
| Growth stalled | Check `.orchestra/state/` for terminal heartbeats |
| Quality not improving | T5 will report issues to responsible terminal |
| Contract mismatch | Manager will facilitate mediation |

---

## Contributing

```bash
# Fork and clone
git clone https://github.com/YOUR_USERNAME/Archon.git

# Create feature branch
git checkout -b feature/my-feature

# Make changes, then format
black orchestrator/
ruff check orchestrator/

# Commit and push
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
