# Archon V3 — Build Addendum (locked 2026-07-10)

Companion to `REQUIREMENTS_V3.md`. These decisions were locked by the product owner at implementation start and **override** the base document where they conflict. Every implementation agent MUST read this file before writing code.

## A. Product constraints (owner, 2026-07-10)

1. **Provider = Claude Code only (MVP).** The only agent CLI adapter shipped in V3.0 is Claude Code. The generic PTY adapter layer (Q30) stays in the architecture, but no other adapter is implemented or shown in UI.
2. **Any-directory project picker.** The user selects ANY directory on disk as the active project (NSOpenPanel, non-sandboxed app). The orchestrator binds to that directory for the instance lifetime (single-project per instance, Q3). Recent-projects list persisted app-side.
3. **Zero-footprint guarantee (project-file protection).** THE hard rule:
   - The app and the Conductor NEVER autonomously create, modify, or delete files inside the project directory. Opening a project (e.g. `~/subralabs-v2`) must leave its working tree byte-identical — no `.archon/` folder, no auto-generated `CLAUDE.md`/`AGENTS.md`, no dotfiles, nothing.
   - ALL app state (kanban, session metadata, audit, orb position, memory overlay, scrollback snapshots) lives OUTSIDE the project, in `~/Library/Application Support/Archon/projects/<sha256(canonical-path)>/`.
   - Files inside the project MAY change only through: (a) spawned agent terminal sessions doing their coding work (that's their job — code, skills, instructions), or (b) an EXPLICIT user-initiated edit action in the app (e.g. the user edits `CLAUDE.md` in the Memory view and presses Save). Conductor-initiated memory writes are forbidden; the Conductor may only *propose* an edit that the user confirms.
   - This supersedes §8 Q6/Q7 of REQUIREMENTS_V3 where they imply orchestrator-autonomous writes: the orchestrator remains the sole file-writing pathway, but only ever on behalf of an explicit user action.
   - Backend enforcement: a write-guard module gates every project-dir write with `initiator: user` provenance; conductor-provenance writes are rejected and audited.
4. **Resilience / API fallback.** The app must degrade gracefully, never crash or hang on backend loss:
   - Orchestrator process dies → client supervisor auto-restarts it (max 3 attempts, exponential backoff), WS auto-reconnects with replay (REQ-BE-043), UI shows a calm reconnect state.
   - Claude API errors (rate limit, 5xx, network) → typed error surface, automatic retry with backoff for idempotent calls, Conductor enters `error` orb state and recovers; running terminals are unaffected.
   - Everything already rendered stays usable read-only while offline.

## B. Repository layout & module ownership

```
lab/Archon/
├── orchestrator/          # Python backend (existing; V3 additions go in orchestrator/v3/)
├── tests/                 # Python tests (existing conventions)
├── client/                # NEW — native macOS app
│   ├── project.yml        # xcodegen spec (directory-based sources: new files auto-included)
│   ├── Sources/
│   │   ├── App/           # entry point, AppDelegate, window scenes, DI container
│   │   ├── ArchonCore/    # models, APIClient, WSClient, OrchestratorSupervisor, stores
│   │   ├── DesignSystem/  # B/W tokens, typography, components, motion primitives
│   │   ├── Terminals/     # individual terminals view + summary dashboard
│   │   ├── Board/         # kanban + memory views + codebase tree
│   │   └── VoiceOrb/      # WhisperKit push-to-talk, floating orb, conductor surface
│   └── Tests/             # XCTest / Swift Testing
```

- Build: `cd client && xcodegen generate && xcodebuild -project Archon.xcodeproj -scheme Archon -destination 'platform=macOS' build`
- Toolchain on this machine: Xcode 27.0, Swift 6.4, xcodegen 2.44.1, macOS 27. Deployment target: macOS 26.
- Swift 6 language mode, strict concurrency. SwiftUI-first; AppKit/Metal only where REQUIREMENTS_V3 §5 justifies it (orb shader, PTY text rendering).
- WhisperKit via SPM; model download lazy at first push-to-talk, never bundled.

## C. Backend V3 surface (orchestrator/v3/)

New FastAPI router mounted under `/v3`, plus WS endpoint `/v3/stream`. Reuses existing auth token pattern (0600 token file, Q9). SQLite (Q29) in the Application Support project dir — never in the project itself (rule A3). Claude Code PTY sessions spawned through the existing terminal/session machinery, extended with: session lifecycle API, event stream fan-out (WebSocket only, Q10), kanban CRUD, memory file list/read + user-initiated write with provenance guard, dry-run estimate, health endpoint. `--bare` stays OFF (breaks OAuth).

## D. Quality bar

- All REQUIREMENTS_V3 MUSTs in scope for MVP unless marked deferred there.
- Design: STRICT black/white (§5.1-5.2) — chromatic color ONLY in orb states. 120 Hz-smooth animations, Liquid Glass where public API allows (Q20).
- Tests required: backend (pytest, existing conventions) + client (Swift Testing) — unit for stores/clients/parsers, snapshot-free UI logic tests.
- Reference perf machine still placeholder M4 Pro/24 GB (§8 [O]).
