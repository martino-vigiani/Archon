# Archon

> **Status: discontinued.** Archon was a personal experiment and is no longer maintained.

Archon explored whether a local Python orchestrator could coordinate multiple coding-agent processes around one software task. It started Claude Code or Codex CLI workers, assigned them fixed or task-shaped roles, collected their output, and exposed a local dashboard for control.

The repository remains public as a historical reference. It is not production software. Dependencies, provider CLIs, prompts, and dashboard behavior may be out of date.

## What the experiment included

- a fixed worker roster and an optional task-shaped roster;
- a local dashboard for runs, sessions, files, and worker output;
- pause, resume, chat, and other control-plane commands;
- a Python backend, JavaScript frontend, and optional Swift client;
- optional support for the Codex CLI as an alternative provider.

## Run the historical version

Running Archon may invoke a paid provider API. Use it only if you want to inspect the old experiment.

```bash
git clone https://github.com/martino-vigiani/Archon.git
cd Archon
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m orchestrator --dashboard "Create a habit tracking iOS app"
```

The dashboard, when enabled, runs at `http://localhost:8420`.

## Development

The repository contains historical backend and frontend test suites. They are not run in continuous integration and are not maintained.

```bash
pip install -r requirements-dev.txt
npm install
pytest
npx vitest
make help
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [CLI reference](docs/CLI_REFERENCE.md)
- [API reference](docs/API_REFERENCE.md)
- [Security architecture](docs/ARCHITECTURE_AND_SECURITY.md)
- [Setup](docs/SETUP.md)
- [Design decisions](docs/DESIGN_DECISIONS.md)

## License

MIT License - see [LICENSE](LICENSE).
