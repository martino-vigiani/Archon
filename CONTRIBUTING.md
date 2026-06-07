# Contributing to Archon

Thanks for your interest in improving Archon. This guide covers how to set up,
make changes, and submit them.

---

## Prerequisites

- Python 3.11+ (validated on 3.12)
- Node.js 18+ (for the dashboard frontend and its tests)
- [Claude Code CLI](https://github.com/anthropics/claude-code) on your `PATH`
  (each terminal is a `claude --print` subprocess)

---

## Setup

```bash
# Fork on GitHub, then clone your fork
git clone https://github.com/YOUR_USERNAME/Archon.git
cd Archon

# Python environment
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Frontend (dashboard)
npm install
```

---

## Workflow

```bash
# Branch off main
git checkout -b feature/my-feature

# Make changes, then format and lint
black orchestrator/
ruff check orchestrator/

# Run the suites
pytest          # backend — 754 tests across 24 files
npx vitest      # frontend — 6 tests across 2 files

# Commit and push
git commit -m "feat: describe the change"
git push origin feature/my-feature
```

Open a PR against `main`. Keep PRs focused — one logical change per PR.

---

## Code standards

| Area | Rules |
|------|-------|
| Python | 3.11+, type hints always, Google-style docstrings, async/await for I/O |
| Formatting | Black (Python), Prettier/ESLint (dashboard JS/TS) |
| Linting | Ruff must pass clean |
| Tests | New behavior needs tests; bug fixes need a regression test |
| Commits | [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, …) |

Match the style of the surrounding code — naming, comment density, and idiom.

---

## Where things live

See [Project Structure](README.md#project-structure) in the README and the
per-component table in [.claude/CLAUDE.md](.claude/CLAUDE.md). Key entry points:

| File | Purpose |
|------|---------|
| `orchestrator/orchestrator.py` | Main coordinator loop |
| `orchestrator/execution.py` | Per-task execution modes → CLI-flag composition |
| `orchestrator/dashboard.py` | FastAPI web UI (localhost:8420) |
| `orchestrator/config.py` | Configuration and terminal definitions |

Deeper docs: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md),
[docs/DESIGN_DECISIONS.md](docs/DESIGN_DECISIONS.md).

---

## Before you open a PR

- [ ] `black orchestrator/` and `ruff check orchestrator/` clean
- [ ] `pytest` green
- [ ] `npx vitest` green (if dashboard JS touched)
- [ ] New/changed behavior is covered by tests
- [ ] Commit messages follow Conventional Commits

---

## Reporting bugs / requesting features

Open a [GitHub issue](https://github.com/martino-vigiani/Archon/issues).
Include repro steps, expected vs actual behavior, and the relevant
`.orchestra/state/` heartbeats or logs when reporting a stalled run.

---

## License

By contributing you agree your contributions are licensed under the
[MIT License](LICENSE).
