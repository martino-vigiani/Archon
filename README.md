<p align="center">
  <img src="assets/dashboard.png" alt="Archon live control dashboard" width="900">
</p>

<h1 align="center">ARCHON</h1>

<p align="center">
  <strong>Organic Multi-Agent Development</strong><br>
  <sub>Software that grows through collaborative intelligence</sub>
  <br><br>
  <a href="#worker-rosters"><img src="https://img.shields.io/badge/Workers-5_or_dynamic-blue?style=flat-square" alt="5 or dynamic workers"></a> <a href="docs/CLI_REFERENCE.md#subagents"><img src="https://img.shields.io/badge/Subagents-20-green?style=flat-square" alt="20 Subagents"></a> <a href="#development"><img src="https://img.shields.io/badge/Tests-778_passing-brightgreen?style=flat-square" alt="778 Tests"></a> <a href="#quick-start"><img src="https://img.shields.io/badge/Python-3.11+-yellow?style=flat-square" alt="Python 3.11+"></a> <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-lightgrey?style=flat-square" alt="MIT License"></a>
</p>

---
## What is Archon?

Archon is a **gardener of intelligence** — it cultivates parallel Claude Code workers and guides them toward creating software through organic collaboration rather than rigid command.

Give Archon an **intent** like *"Create an iOS habit tracking app"* and it seeds that intent across a team of autonomous workers. Each worker is a non-interactive `claude --print` subprocess; the orchestrator observes quality, resolves conflicts, and intervenes surgically. Work is not binary (done / not done) — it exists on a continuous quality gradient from 0.0 to 1.0.

Workers come in two flavors: the classic **five fixed personalities** (T1–T5) or a **dynamic, task-shaped roster** (`--dynamic-agents`) derived from the goal. An optional Codex runtime is supported via `--llm-provider codex`.

For the gardener model in pictures and the quality-gradient table, see [docs/CLI_REFERENCE.md](docs/CLI_REFERENCE.md#philosophy-the-gardener-model).
## See it in action

Asked to *"create a minimalist iOS water-tracking app"*, a dynamic worker roster produced a **compiling, unit-tested SwiftUI app** — 26 Swift files, a full Xcode project, onboarding, reminders, a design system and tests — autonomously, with zero failed tasks.

<p align="center">
  <img src="assets/example-watertracker-home.png" alt="Water Tracker — home screen with hydration ring and quick-add" width="250">
  &nbsp;&nbsp;&nbsp;
  <img src="assets/example-watertracker-onboarding.png" alt="Water Tracker — onboarding unit selection" width="250">
</p>
<p align="center">
  <sub>An iOS app built end-to-end by Archon, running in the iOS Simulator. The control dashboard at the top of this page is how you watch it happen, live.</sub>
</p>
## Quick Start

```bash
git clone https://github.com/martino-vigiani/Archon.git
cd Archon
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m orchestrator --dashboard "Create a habit tracking iOS app"
```

**Requirements**

- Python 3.11+ (validated on 3.12)
- One supported runtime in PATH: **[Claude Code CLI](https://github.com/anthropics/claude-code)** (default) or **Codex CLI** (`codex`) for `--llm-provider codex`
- Provider account access for the selected runtime
## Worker Rosters

`TerminalID` is a plain `str`, so both roster models are first-class citizens and can even coexist in the same run.

### Fixed Personalities (T1–T5) — Default

| Terminal | Personality | Home Domain |
|----------|-------------|-------------|
| **T1** | The Craftsman | UI/UX |
| **T2** | The Architect | Backend/Systems |
| **T3** | The Narrator | Documentation |
| **T4** | The Strategist | Product/Vision |
| **T5** | The Skeptic | QA/Testing |

T5 is enabled by default and can be disabled with `--no-testing` to save API limits. Every worker can invoke any of the [20 subagents](docs/CLI_REFERENCE.md#subagents) regardless of home domain.

### Dynamic Task-Shaped Roster (`--dynamic-agents`)

Enable with `--dynamic-agents`: Archon derives a roster `w1..wN` from the actual goal — a capability lane per worker, no fixed names or roles. Default lanes: `architecture` (deep model, high effort), `ui` + `strategy` (standard, medium), `code` + `qa` (standard, high; `qa` skipped with `--no-testing`), `docs` (cheap, low).
## Live Control Dashboard

Start with `--dashboard` — opens at **http://localhost:8420**, a multi-route single-page app (the "MONO" control plane: neutral monochrome surfaces, one accent, dark + light).

- **Dashboard** — live agents, per-agent runtime chips (provider · model · effort), quality gradient bars (0.0–1.0), live terminal output, feeds, and the manager interventions timeline.
- **New Run** — launch + configure a run, pick a working directory, preview the roster.
- **Sessions · Chat · Files · Workspace** — switch between runs, talk to the orchestrator with session memory, browse what each agent created, explore the agent/file/contract graph.

Control-plane POST endpoints (pause, resume, inject, mode override, spawn, chat, new runs) and execution-mode internals live in [docs/CLI_REFERENCE.md](docs/CLI_REFERENCE.md).
## CLI Reference

```bash
python -m orchestrator "Create a todo app with SwiftUI"
python -m orchestrator --dashboard "Build a REST API"
python -m orchestrator --chat --dashboard "Create a meditation app"
python -m orchestrator --project ./Apps/MyApp "Add dark mode"
python -m orchestrator --dynamic-agents --dashboard "Build a full-stack app"
python -m orchestrator --llm-provider codex --llm-model gpt-5.3-codex --dashboard "Your task"
python -m orchestrator --resume
```

The complete flag table, Manager Chat commands and Codex mode details live in [docs/CLI_REFERENCE.md](docs/CLI_REFERENCE.md).
## Development

```bash
pip install -r requirements-dev.txt
npm install
pytest                       # backend tests (754 tests, 24 files)
npx vitest                   # frontend tests (6 tests, 2 files)
black orchestrator/ && ruff check orchestrator/
make help
```

Python 3.11+ required; validated on 3.12.
## Docs

| Guide | Purpose |
|-------|---------|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System architecture and organic model |
| [CLI_REFERENCE.md](docs/CLI_REFERENCE.md) | CLI flags, control-plane endpoints, subagents, execution internals |
| [API_REFERENCE.md](docs/API_REFERENCE.md) | Dashboard API endpoints |
| [ARCHITECTURE_AND_SECURITY.md](docs/ARCHITECTURE_AND_SECURITY.md) | Security architecture |
| [AUTH_GUIDE.md](docs/AUTH_GUIDE.md) | Authentication setup |
| [DESIGN_DECISIONS.md](docs/DESIGN_DECISIONS.md) | Key architectural decisions and rationale |
| [GETTING_STARTED.md](docs/GETTING_STARTED.md) | Detailed setup guide |
| [SETUP.md](docs/SETUP.md) | Configuration reference |
| [PRD.md](docs/PRD.md) | Product requirements document |
| [diagrams.md](docs/diagrams.md) | Visual architecture diagrams |
| [CODEX_SPECIALIST_TEAM.md](docs/CODEX_SPECIALIST_TEAM.md) | Codex 5.3 specialist roles, handoffs, autonomy workflow |
| [REVOLUTIONARY_IDEAS.md](docs/REVOLUTIONARY_IDEAS.md) | Next-evolution roadmap |
## License

MIT License — see [LICENSE](LICENSE)

---

<p align="center">
  <sub>Built with <a href="https://github.com/anthropics/claude-code">Claude Code</a> by Anthropic</sub>
</p>
