# Archon

Archon is a discontinued experiment that coordinated AI coding sessions for a local project and showed their tasks, terminal output, and shared notes.

The source is kept for developers studying the experiment or reusing parts of it. It includes a Python command-line tool, a browser dashboard, and an experimental native Mac app.

## Current state

**Discontinued; no longer maintained.** Dependencies, provider tools, prompts, and dashboard behavior may be out of date. The archived source contains two interfaces with different capabilities:

| Interface | What it uses |
| --- | --- |
| Python CLI and browser dashboard | Claude Code, or Codex when selected with `--llm-provider codex` |
| Native Mac app with the V3 backend | Claude Code sessions, a task board, project files, shared notes, and optional voice input |

The V3 planner uses an Anthropic API key when configured; without one, it creates a simple local plan. A paid CLI login and an API key are separate credentials. The Mac app also needs a local Python environment; this checkout does not package a standalone installer.

## What the experiment included

- Start and monitor coding sessions in a chosen project directory.
- Show live terminal output and session state.
- Organize work on a task board and review proposed changes to shared notes.
- In the older CLI, use a fixed worker team or derive a team from the task with `--dynamic-agents`.

Agents can change project files and consume the selected provider's usage allowance. The V3 session adapter bypasses Claude Code permission prompts by default, so try it on a disposable copy of a project first. Generated work still needs review and testing.

## Explore the historical Python CLI

The commands below describe the existing entry points and may need fixes with current tools or providers. You need Python 3.11 or later, and either `claude` or `codex` installed, signed in, and available in your shell.

```sh
git clone https://github.com/martino-vigiani/Archon.git
cd Archon
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt httpx
python -m orchestrator --help
```

The help command lists the options without starting agents. To start an example using Claude Code:

```sh
mkdir -p Apps/Example
python -m orchestrator --project ./Apps/Example --dashboard \
  "Create a small command-line todo app"
```

The browser dashboard is served at `http://localhost:8420` by default. Add `--llm-provider codex` to use Codex for this CLI path.

## Inspect the experimental Mac client

You also need macOS 26 or later, Xcode with the macOS 26 SDK or later, and XcodeGen.

From the repository root, after setting up Python above:

```sh
xcodegen generate --spec client/project.yml
open client/Archon.xcodeproj
```

In the `Archon` scheme's **Run → Arguments → Environment Variables**, set `ARCHON_REPO` to this repository's absolute path and `ARCHON_PYTHON` to its `.venv/bin/python`. Select the `Archon` scheme and run it. Choose a project directory when asked.

Voice input needs Microphone permission and a downloaded speech model. Coding requests may be sent to the configured provider; local voice transcription does not make the whole workflow offline.

## Historical development and reference

- [Development setup and checks](docs/DEVELOPMENT.md)
- [CLI options and dashboard controls](docs/CLI_REFERENCE.md)
- [V3 API contract](docs/API_CONTRACT_V3.md)
- [V3 requirements and build decisions](docs/REQUIREMENTS_V3.md), [build addendum](docs/BUILD_ADDENDUM_V3.md)
- [Architecture and security](docs/ARCHITECTURE_AND_SECURITY.md)
- [Contributing](CONTRIBUTING.md)

Licensed under the [MIT License](LICENSE).
