# Archon development reference

**Archon is discontinued and no longer maintained.** The [README](../README.md) explains the archived interfaces. This guide records their source layout, configuration, and historical checks; current tools and providers may require fixes.

## Source layout

| Path | Responsibility |
| --- | --- |
| `orchestrator/` | Older Python CLI, worker scheduling, and browser dashboard |
| `orchestrator/v3/` | Local backend for the native Mac app |
| `client/Sources/` | SwiftUI app, terminal display, task board, notes, and voice input |
| `tests/` | Python tests; browser tests are in `tests/frontend/` |
| `client/Tests/` | Native client tests |
| `templates/` | Worker prompts and shared interface templates |

`client/project.yml` defines the Xcode project. Regenerate it after changing the source layout.

## Python and browser checks

From an activated virtual environment at the repository root:

```sh
python -m pip install -r requirements-dev.txt
npm ci
python -m pytest
npm run test:frontend
python -m ruff check orchestrator/ tests/
python -m black --check orchestrator/ tests/
make help
```

These are the historical checks configured in the repository. They are no longer maintained. Python and JavaScript checks do not cover the native UI or a real provider session.

## Native client build

The client targets macOS 26 and uses Swift 6 with strict concurrency checking.

```sh
xcodegen generate --spec client/project.yml
xcodebuild -project client/Archon.xcodeproj -scheme Archon \
  -destination 'platform=macOS' build CODE_SIGNING_ALLOWED=NO
```

This is a compile check without signing. Running voice input and global controls requires a suitable signed app and the relevant macOS permissions. The client links WhisperKit; model files are downloaded separately.

For an Xcode launch, set these variables in the scheme:

| Variable | Value |
| --- | --- |
| `ARCHON_REPO` | Absolute path to this repository |
| `ARCHON_PYTHON` | Absolute path to the virtual environment's Python executable |

These settings avoid relying on the supervisor's historical developer-machine fallback path. See [OrchestratorSupervisor.swift](../client/Sources/ArchonCore/Supervision/OrchestratorSupervisor.swift) for runtime discovery and process supervision.

## V3 backend on its own

To inspect the backend separately from the app, pass an existing project directory:

```sh
python -m orchestrator.v3 --project /absolute/path/to/a/test-project
```

It binds to loopback, chooses an available port, and prints its address. The per-project handshake and state live under `~/Library/Application Support/Archon/projects/`. The handshake contains an access token; keep it private.

The V3 session adapter runs Claude Code. The older CLI's Codex option does not apply to V3. The real V3 planner needs `httpx` plus `ANTHROPIC_API_KEY`, `ARCHON_V3_PROVIDER_KEY`, or a protected file named by `ARCHON_V3_PROVIDER_KEY_FILE`. Do not commit an API key. Without a key, the backend uses its deterministic local planner and reports that no real planner is ready.

The session adapter currently includes `--dangerously-skip-permissions`. Review [adapters.py](../orchestrator/v3/adapters.py) before running it on a valuable checkout.

## Worker teams in the older CLI

The default team assigns UI work to T1, systems to T2, documentation to T3, product work to T4, and testing to T5. `--no-testing` removes the testing worker. `--dynamic-agents` instead creates task-specific workers named `w1`, `w2`, and so on.

See the [CLI reference](CLI_REFERENCE.md) for all flags, worker roles, session controls, and execution profiles. V3 behavior is defined separately by the [API contract](API_CONTRACT_V3.md), [requirements](REQUIREMENTS_V3.md), and [build addendum](BUILD_ADDENDUM_V3.md).
