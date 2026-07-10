# Archon V3 — Requirements Specification

## Executive Summary

Archon V3 is a native macOS 26 (Tahoe) client that turns spoken or typed intent into a fleet of coordinated, locally-running coding agents. A single Claude-driven **Conductor** — running inside a local orchestrator that holds the provider key — interprets intent, decides how many PTY-backed agent sessions ("terminals") to spawn, and routes work against a local codebase, while the developer steers and reviews through a strictly black-and-white interface whose only color lives in a fluid, Siri-like **orb**. This document is the consolidated, at-the-limit engineering specification for V3: it fixes the product scope and personas, the client/orchestrator architecture and transport, the backend orchestrator refactor, the UX and view model, the visual design and motion language, and hard performance/resource budgets — all reconciled against the four Locked Decisions below.

## Locked Decisions (recap)

1. **Local-only agent execution.** Agents run exclusively as PTY-backed local sessions ("terminals") against a local codebase. No remote/cloud agent execution; no non-loopback orchestrator.
2. **Single Conductor; provider key server-side only.** Exactly one Conductor presence, powered by the Claude API via the local orchestrator. The orchestrator is the sole holder of the provider API key and the sole spawner of terminals; the Swift client never stores, requests, reads, or transmits the key.
3. **On-device speech-to-text.** Dictation is WhisperKit on-device only. No cloud/third-party STT. Only the finalized text intent leaves the client, and only to loopback.
4. **Strictly monochrome UI, color only in the orb.** All UI surfaces are achromatic except the orb and its enumerated animation surfaces (glow, listening ripple, state-transition overlays).

### Product Decisions (locked 2026-07-09)

These four resolve the highest-leverage product Open Questions; they are now binding and the affected requirements are read in their light. See §8 Decisions Log for the full resolution of all 32 original open items.

5. **Single-project per instance.** One orchestrator instance drives terminals against exactly one project directory/codebase. Multiple projects = multiple instances. Session, memory, and kanban scoping are single-project; the API does not multiplex projects. *(Resolves original Q3; simplifies REQ-BE-004, REQ-ARCH memory/session scoping.)*
6. **Memory files = agent-native conventions + optional overlay.** Directory-scoped memory reuses the agents' own `CLAUDE.md` / `AGENTS.md` files as the primary, in-app-editable base, plus an optional `.archon/` overlay for Archon-specific metadata. Both are read into agent context; the orchestrator is the sole writer (see §8). *(Resolves original Q6.)*
7. **Accept = automatic git commit.** Accepting an agent's changes creates a git commit on the current branch with a generated message referencing the run/task; reject discards the working-tree changes. This is local git only (consistent with the "no in-app git hosting/PR-server" non-goal, REQ-VIS-023d). Dedicated-branch strategy is COULD/later. *(Resolves original Q1; refines REQ-VIS-014.)*
8. **Voice activation = push-to-talk.** A global hotkey gates dictation; WhisperKit runs only while the key is held, keeping idle RAM/CPU at zero for STT. Wake-word is deferred (COULD, opt-in in Settings). *(Resolves original Q13; refines REQ-UX-030, tightens PERF budgets.)*

## Table of Contents

1. Product Vision, Scope & Personas — `REQ-VIS-*`
2. System Architecture — `REQ-ARCH-*`
3. Backend Orchestrator — `REQ-BE-*`
4. UX, Views & Interaction — `REQ-UX-*`
5. Visual Design System & Motion — `REQ-DSN-*`
6. Performance & Resource Budgets — `REQ-PERF-*`
7. Glossary
8. Decisions Log & Residual Open Items
9. Traceability Note

**Reference machine (canonical, all hard budgets):** Apple M4 Pro (12-core CPU, 20-core GPU), 24 GB unified memory, macOS 26.0, internal NVMe SSD. No requirement may cite a machine more powerful than M4 Pro to justify laxity. *(This supersedes the "16 GB Apple silicon" assumption in the original Product Vision draft; see the consolidated Open Question on supported memory configurations.)*

**Requirement keywords:** MUST / SHOULD / COULD carry RFC-2119 force. Every MUST states an Acceptance Criterion. Binary byte sizes use KiB/MiB (1024-based) where the owning section originally specified them; decimal MB/GB are preserved as written.

---

## 1. Product Vision, Scope & Personas

### 1.1 Personas

- **Mara — solo power-developer (primary).** Senior developer working alone or leading a tiny team; fluent with Claude Code / Codex CLI. Wants to fan work across many parallel local sessions and stay in flow via voice. Values fluidity, minimalism, low resource cost, full local control of code and keys.
- **Devin — OSS contributor (primary).** Runs Archon from source, inspects the orchestrator, files issues/PRs. Values reproducible local setup, transparent behavior, hackable memory files, and no hidden cloud dependency beyond the Claude API used by the Conductor.
- **Sam — reviewer/observer (secondary).** Drives Archon mainly to monitor progress and review diffs. Values the summary dashboard, live terminal view, and change review being legible at a glance.

### 1.2 Vision Requirements

- **REQ-VIS-001 (MUST)** — Serve a single-operator, single-machine workflow: one human orchestrating N concurrent local terminals through one Conductor. *Acceptance:* On one Mac with one account, the app spawns, displays, and controls ≥ 8 concurrent terminals against a local codebase with no second machine or remote service other than the Claude API used by the orchestrator.
- **REQ-VIS-002 (MUST)** — The client MUST NOT hold, request, or persist the provider (Claude) API key; all Claude access is mediated by the local orchestrator. *Acceptance:* Static inspection of client storage (Keychain, defaults, files) after a full session shows no provider key; disabling the orchestrator disables all Conductor intelligence. *(Enforced client-side by REQ-ARCH-040, server-side by REQ-BE-060.)*
- **REQ-VIS-003 (SHOULD)** — Usable end-to-end by Mara without touching a mouse for the core loop (speak → spawn → monitor), and fully operable by Devin/Sam with keyboard and pointer.
- **REQ-VIS-004 (SHOULD)** — From a cloned repo and a running orchestrator, a first-time contributor reaches their first spawned terminal in ≤ 5 minutes without editing source.

### 1.3 Use Cases & Journeys

Catalog: **UC-1** Voice-to-spawn · **UC-2** Manual policy/cap · **UC-3** Live monitoring · **UC-4** Summary overview · **UC-5** Kanban management · **UC-6** Read-only codebase browsing · **UC-7** Change review · **UC-8** Directory-scoped memory. Journeys: **J-1** Voice → spawn → monitor · **J-2** Constrain then delegate · **J-3** Board-driven work · **J-4** Browse & review · **J-5** Memory-guided run.

- **REQ-VIS-010 (MUST)** — UC-1…UC-8 are first-class, discoverable features in V3. *Acceptance:* Each is reachable within ≤ 2 interactions from the default screen and has a passing end-to-end test.
- **REQ-VIS-011 (MUST)** — J-1 is completable voice-first, from first utterance to ≥ 1 live streaming terminal. *Acceptance:* A scripted run (audio → transcription → plan → spawn) yields ≥ 1 terminal emitting live output with no keyboard/mouse input after dictation begins.
- **REQ-VIS-012 (MUST)** — The user can override Conductor autonomy with an explicit terminal/policy cap (UC-2), which the Conductor MUST honor. *Acceptance:* Given a cap of K, the app never exceeds K concurrent terminals for that run; exceeding K is a test failure. *(Enforced server-side by REQ-BE-003.)*
- **REQ-VIS-013 (MUST)** — Both required visualizations (Individual Terminals, Summary Dashboard) are present and switchable. *Acceptance:* The user can switch between them and see the same run reflected consistently within ≤ 1 s of state change.
- **REQ-VIS-014 (SHOULD)** — Change review (UC-7) lets the user accept/reject an agent's changes without leaving the app. *Acceptance:* For a run that modifies files, the user views a per-file diff and issues an accept/reject the orchestrator records.
- **REQ-VIS-015 (SHOULD/MUST)** — Directory-scoped memory (UC-8) SHOULD be editable in-app and MUST be consumed by agents scoped to that directory. *Acceptance:* Editing a directory's memory file changes the context provided to a subsequent agent run there (verifiable via assembled context).

### 1.4 Non-Goals / Out of Scope for V3

- **REQ-VIS-020 (MUST)** — No remote/cloud execution of agents. *Acceptance:* No code path spawns a terminal on a non-localhost host.
- **REQ-VIS-021 (MUST)** — No cloud/third-party STT; dictation is WhisperKit on-device only. *Acceptance:* Network capture during dictation shows zero outbound audio/transcription traffic.
- **REQ-VIS-022 (MUST)** — No color in the UI outside the orb/animation surfaces. *Acceptance:* An automated screenshot audit of all non-orb regions finds only grayscale pixels within tolerance. *(Formalized by REQ-DSN-001/011.)*
- **REQ-VIS-023 (SHOULD)** — Explicitly out of scope and not to be built: (a) multi-user collaboration / accounts / cloud sync; (b) iOS/iPad mobile clients; (c) plugin marketplace / extension store; (d) in-app git hosting or PR-server beyond local diff review; (e) agent CLIs beyond the orchestrator's defined set (initially Claude Code / Codex CLI); (f) an in-app code editor (codebase view is read-only). *Acceptance:* No V3 milestone contains deliverables for (a)–(f).
- **REQ-VIS-024 (COULD)** — V3 COULD expose read-only hooks/telemetry for future extension, but MUST NOT commit to a stable public extension API in V3.

### 1.5 Success Metrics

- **REQ-VIS-030 (MUST)** — Voice-to-first-agent latency (end of dictation → first terminal visibly streaming) ≤ 4 s p50 and ≤ 8 s p95 on the reference machine, excluding model/network time attributable to the Claude API. *Acceptance:* Instrumented runs (n ≥ 20) meet both percentiles.
- **REQ-VIS-031 (MUST)** — UI animations, including the orb, sustain display refresh (target 120 Hz on ProMotion) with no dropped-frame streak > 3 frames during listening/spawn transitions. *Acceptance:* Core Animation capture during J-1 shows ≥ 99% frames on time. *(Subsumed by the tighter REQ-PERF-010 floor of 90 Hz.)*
- **REQ-VIS-032 (MUST)** — With 8 idle-but-live terminals displayed, client steady-state resident memory and CPU stay within the budgets defined authoritatively in **REQ-PERF-003 (≤ 340 MB RSS)** and **REQ-PERF-006/008 (CPU)**. *Resolution: the original draft's "≤ 600 MB / ≤ 8% of one core on 16 GB Apple silicon" is superseded by the reference-machine PERF budgets to remove the machine/budget conflict.* *Acceptance:* Measured per REQ-PERF-003 over a 5-minute idle-observation window.
- **REQ-VIS-033 (SHOULD)** — On-device transcription WER low enough that ≥ 90% of dictated intents need no manual correction for a native-English speaker in a quiet room. *Acceptance:* Measured over a fixed 30-utterance script.
- **REQ-VIS-034 (SHOULD)** — New-contributor time-to-first-spawn ≤ 5 minutes (per REQ-VIS-004). *Acceptance:* Cold-start walkthrough by a first-time user completes within budget.
- **REQ-VIS-035 (COULD)** — Track task-acceptance rate (share of agent changes the user accepts); dogfooding target ≥ 60%.

---

## 2. System Architecture

Binds the client to the local orchestrator. Server-side behaviors (replay buffers, throttling, cap enforcement, plan generation, key custody, PTY spawning) are owned by `REQ-BE-*` and referenced, not duplicated. Assumptions: the orchestrator runs as a separate local process on the same machine; one user / one machine / one orchestrator for V3; "terminal" = one PTY-backed agent session; "task" = a kanban card mapping to zero, one, or many terminals over its lifetime.

### 2.A Transport & Protocol

- **REQ-ARCH-001 (MUST)** — Split transport: (a) a **control channel** over localhost HTTP/1.1 or HTTP/2 for transactional commands (spawn, kill, plan, board mutations, memory read/write); (b) a **stream channel** over a persistent WebSocket for PTY output and lifecycle/board/plan events. SSE MAY serve as a fallback stream transport only. *Acceptance:* With the stream channel closed, control commands still succeed within budget; with control idle, PTY output continues on the stream channel.
- **REQ-ARCH-002 (MUST)** — Loopback-only: connect only to `127.0.0.1`/`::1` on a configured port; refuse and never discover non-loopback hosts. *Acceptance:* Configuring a non-loopback host is rejected with a visible error; a packet capture shows zero orchestrator traffic leaving loopback.
- **REQ-ARCH-003 (MUST)** — Message envelope: every stream message and control response is a single framed JSON object carrying `v` (int), `type` (enum), `id` (ULID/UUID), `ts` (RFC 3339 UTC, ms precision), and `payload`. Session-scoped messages carry `sessionId`; board/plan messages carry `taskId`/`planId`. *Acceptance:* A schema validator over a 10-minute session flags zero missing required fields; unknown `type` is ignored without disconnecting.
- **REQ-ARCH-004 (MUST)** — Version negotiation at connect. Major-version mismatch → refuse the stream and surface an "incompatible orchestrator" state (no best-effort parsing). Minor differences tolerated (additive fields only). *Acceptance:* Higher major yields the incompatible state and no data-plane parsing; higher minor connects and ignores unknown additive fields.
- **REQ-ARCH-005 (MUST)** — Per-session monotonic, gap-free `seq` on PTY output and lifecycle events. The client renders bytes in `seq` order and detects gaps. *Acceptance:* Captured `seq` increases by exactly 1 per session; dropping one frame triggers resync (REQ-ARCH-008), never out-of-order render.
- **REQ-ARCH-006 (SHOULD)** — Ignore unknown message types and payload fields without disconnecting; log at debug only.
- **REQ-ARCH-007 (MUST)** — Auto-reconnect on stream drop with exponential backoff + jitter, start ≤ 500 ms, cap ≤ 15 s, indefinitely while foregrounded, no user action. Reconnection MUST NOT spawn, kill, or duplicate any terminal. *Acceptance:* Restarting the orchestrator re-establishes the stream within one backoff cycle after the port reopens; terminal count is identical before and after.
- **REQ-ARCH-008 (MUST)** — Resync after reconnect: request per-session output since last `seq` plus current lifecycle/board/plan snapshots. If requested `seq` predates the server buffer (REQ-BE-043), do a full snapshot resync and mark a visible truncation point. *Acceptance:* After a 30 s disconnect during active output, the reconnected view has no duplicated lines and shows all missed output or an explicit "output truncated" marker.
- **REQ-ARCH-009 (MUST)** — Backpressure & flow control. Per-session live ring buffer sized per **REQ-PERF-021/022 (10,000-line virtualized buffer)**; aggregate stream-buffer memory bounded ≤ 64 MiB across all sessions. *Resolution: the draft's per-session "≤ 5,000 lines / ≤ 2 MiB" is aligned to the 10,000-line PERF budget; the aggregate cap is retained.* When the client cannot keep up it applies backpressure (coalescing renders and/or signaling throttle per REQ-BE-044), never an unbounded queue. *Acceptance:* Under a synthetic 5 MB/s PTY stream for 60 s, stream-buffer RSS stays ≤ 64 MiB across all sessions and no main-thread hang > 250 ms.
- **REQ-ARCH-010 (MUST)** — Render coalescing capped at display refresh (≤ 120 Hz on ProMotion), one UI update per session per frame, batching bytes received between frames. Ingestion batching uses the 16 ms window of **REQ-PERF-020**. *Acceptance:* Instruments shows terminal-view updates capped at display refresh; sustained output does not exceed one committed render per frame per visible session.
- **REQ-ARCH-011 (MUST)** — Application-level heartbeats (ping/pong ≤ 15 s). Two consecutive missed heartbeats mark the connection stale and trigger reconnection. *Acceptance:* A silently dropped socket is detected stale within ≤ 30 s and reconnection begins.
- **REQ-ARCH-012 (SHOULD)** — For non-visible sessions, request reduced-rate/summarized streaming (REQ-BE-045) to conserve CPU/energy; restore full rate on focus.

### 2.B Terminal Lifecycle (client view)

- **REQ-ARCH-020 (MUST)** — Explicit state machine per terminal: `Requested → Spawning → Running → (Completed | Failed | Killed)` plus transient `Reconnecting`. Every transition originates from an orchestrator event carrying `sessionId` and `seq`; the client MUST NOT infer `Completed` from output content. *Acceptance:* A scripted spawn/stream/exit drives exactly `Requested→Spawning→Running→Completed`, each transition timestamped from a received event.
- **REQ-ARCH-021 (MUST)** — Idempotent spawn keyed by client `requestId`; retry never creates a second terminal; the response returns the authoritative `sessionId`. *Acceptance:* Sending the same spawn `requestId` twice yields one terminal and the same `sessionId`.
- **REQ-ARCH-022 (MUST)** — Spawn ack (accepted + `sessionId`, or rejected + reason) within **500 ms P95** under nominal local load, independent of agent productivity time. *Acceptance:* Over 100 warm-orchestrator spawns, P95 ack ≤ 500 ms; every response is accept-with-`sessionId` or reject-with-reason.
- **REQ-ARCH-023 (MUST)** — Graceful termination then bounded forced kill; idempotent; resolves to `Killed` (or `Completed` if it finished first) with a terminal event. *Acceptance:* Killing a long-running terminal transitions it to `Killed` within grace+force (default ≤ 10 s) and no further PTY output for that `sessionId` renders afterward.
- **REQ-ARCH-024 (MUST)** — Honor and display the effective concurrent cap (auto or user-set); show which regime is active and current/max. Enforcement is server-side (REQ-BE-003/004); the client MUST NOT locally exceed a user-set cap when issuing spawns. *Acceptance:* With a user cap X, the UI shows "N/X"; manual spawns beyond X are disabled or rejected with a visible reason.
- **REQ-ARCH-025 (MUST)** — Each terminal binds to at most one task via `taskId`; a task may have many terminals. Auto- and user-driven bindings are modeled identically. *Acceptance:* A card move and a Conductor spawn both yield the same `taskId`↔`sessionId` association in board and terminals views.
- **REQ-ARCH-026 (MUST)** — On (re)connect, replace the local session list with the orchestrator's authoritative snapshot: unknown-to-server sessions removed (archived per REQ-ARCH-041); server sessions unknown locally added. *Acceptance:* Restarting the client mid-run reconstructs the exact live-terminal set with no phantom or missing entries.
- **REQ-ARCH-027 (SHOULD)** — Surface per-terminal start time, elapsed, exit code/reason, and last-activity timestamp from lifecycle events.

### 2.C WhisperKit Integration Boundary

- **REQ-ARCH-030 (MUST)** — STT runs entirely on-device via embedded WhisperKit. Captured audio and intermediate transcripts MUST NOT be transmitted anywhere, including the local orchestrator, except as the final text intent (REQ-ARCH-032). *Acceptance:* During dictation, a network capture shows zero audio-bearing payloads on any interface; only text intent leaves the client, only to loopback.
- **REQ-ARCH-031 (MUST)** — The client owns the full audio path (capture, buffering, transcription, dictation UI). Mic access is gated by explicit user action; the orb/listening indicator is visible whenever the mic is active. *Acceptance:* The mic is active only while the listening state is shown; ending dictation releases the input node and hides the indicator.
- **REQ-ARCH-032 (MUST)** — The STT→orchestrator handoff is a finalized UTF-8 text intent over the control channel, tagged with a client `requestId` and optional context (active directory/project, board selection). Partial hypotheses MAY show locally but MUST NOT be sent. *Acceptance:* Speaking a command yields exactly one intent request containing the final transcript; interim hypotheses produce no orchestrator traffic.
- **REQ-ARCH-033 (SHOULD)** — End-of-speech to finalized transcript ≤ 1.5 s P90 for utterances ≤ 10 s on Apple silicon; loaded model resident memory within a documented budget (target ≤ 600 MiB for the selected tier) and unload after a configurable idle period. *Acceptance:* Benchmarked utterances meet the latency target; the model unloads after idle timeout.
- **REQ-ARCH-034 (MUST)** — The model is usable offline once provisioned. If first-run download is needed, show progress and do not block non-voice features; voice degrades gracefully (disabled with explanation) until ready. *Acceptance:* With networking disabled after first provisioning, dictation works fully; before provisioning, voice UI shows "preparing dictation" and typed intent still works.

### 2.D Claude-API-via-Backend Flow

- **REQ-ARCH-040 (MUST)** — No provider keys in client: no code path reads a provider key from disk, Keychain, env, or user input; all Claude calls originate from the orchestrator. *Acceptance:* Static inspection finds no provider-key handling; the full voice→plan→spawn flow works with the client sandbox denied direct outbound internet (loopback only).
- **REQ-ARCH-041 (MUST)** — Intent → plan round trip: submit intent (voice or typed) and receive a structured **plan** (tasks to create/modify, terminals to spawn, target directories, terminal-count decision, auto vs user-capped). Plan generation is streamed as events so the Conductor "thinking" renders without blocking. *Acceptance:* A submitted intent yields a structured plan the client renders as board/terminal proposals; progress is incremental via stream events, not a single blocking response.
- **REQ-ARCH-042 (SHOULD)** — Support auto-apply and confirm-before-apply regimes (user-configurable); destructive proposals (kill terminals, delete tasks) are distinguishable before applying when confirmation is enabled. *Acceptance:* In confirm mode nothing spawns/kills until accepted; in auto mode actions apply with an undo/stop affordance where feasible.
- **REQ-ARCH-043 (MUST)** — Exactly one primary Conductor presence; multiple concurrent Conductor identities MUST NOT be presented despite many parallel terminals. *Acceptance:* At all times the UI exposes one Conductor entity that owns planning; terminals are subordinate sessions, never additional Conductors.
- **REQ-ARCH-044 (COULD)** — Surface orchestrator-reported planning metadata (model, token/cost estimates, latency) read-only, without ever handling keys.

### 2.E Directory-Scoped Memory Files (client)

- **REQ-ARCH-050 (MUST)** — Memory stored as plain files under a per-directory location (default `.archon/memory/` at the project root), scoped to that directory. *Acceptance:* Two projects maintain independent memory; switching the active directory swaps the visible/effective set with no cross-contamination.
- **REQ-ARCH-051 (MUST)** — Human-readable UTF-8 (Markdown for prose; a documented structured format for machine metadata). Diff-friendly and safe to commit. *Acceptance:* A memory file opens/edits cleanly in a plain editor and produces a readable line-based git diff.
- **REQ-ARCH-052 (MUST)** — Write arbitration prevents lost updates: the orchestrator is authoritative writer for agent-initiated changes; the client writes user edits through the orchestrator (REQ-BE-023) or via the atomic protocol (REQ-ARCH-053) when writing directly. Concurrent blind overwrites MUST be prevented. *Acceptance:* A simulated simultaneous agent+user edit discards neither change; the loser is merged, rejected, or preserved as a conflict copy.
- **REQ-ARCH-053 (MUST)** — Direct client writes are atomic (write-temp-then-rename) with an optimistic-concurrency guard (content hash / modification token compared before replace); stale writes are rejected and reconciled. *Acceptance:* Under a scripted race (external rewrite between read and write), the client write is rejected as stale and the external change is preserved.
- **REQ-ARCH-054 (MUST)** — Detect out-of-band changes (agents, git, manual edits) and refresh the in-memory view without restart, coalescing rapid changes. *Acceptance:* An external editor's change updates the displayed content within ≤ 2 s without manual reload.
- **REQ-ARCH-055 (SHOULD)** — Warn when a directory's memory footprint exceeds a configurable threshold (default 1 MiB/file, 10 MiB/directory) and offer pruning/summarization. *Note:* the backend enforces a hard quota (REQ-BE-025: 1 MB/file, 32 MB/512 files per scope); the client warning threshold is intentionally lower than the hard limit.

### 2.F Client-Side Data Model & Persistence

- **REQ-ARCH-060 (MUST)** — The orchestrator is source of truth for live runtime state; the client store is a cache/projection plus local-only UI state; on reconnect conflict, server state wins (REQ-ARCH-026). *Acceptance:* Deleting the local store and relaunching reconstructs live terminals and board state from the orchestrator with no loss of active work.
- **REQ-ARCH-061 (MUST)** — The client persists only: (a) UI/preferences; (b) recent directories and their `.archon/` paths; (c) a bounded local cache of scrollback/event history; (d) dictation preferences. No provider keys or full conversation secrets. *Acceptance:* On-disk store shows only these categories; no provider credential material.
- **REQ-ARCH-062 (SHOULD)** — Small structured state uses SwiftData/SQLite; large append-only artifacts (scrollback, event logs) use flat/rotated files. Persistence-layer resident footprint target ≤ 50 MiB steady-state (excluding capped caches). *Acceptance:* After a typical run, the DB stays ≤ 20 MiB and bulk output lives in rotating logs capped per REQ-ARCH-063.
- **REQ-ARCH-063 (MUST)** — Cached scrollback/event history bounded by size and/or age (default ≤ 200 MiB total and ≤ 14 days, whichever first), oldest-first eviction. *Acceptance:* Sustained usage past the cap evicts oldest data; on-disk cache stays within the limit.
- **REQ-ARCH-064 (MUST)** — Versioned schema; migrate or safely discard incompatible caches on upgrade without crashing or corrupting preferences. *Acceptance:* Launching a new version over an older store migrates cleanly or resets the cache while preserving preferences, no crash.

### 2.G Security

- **REQ-ARCH-070 (MUST)** — Communicate only over a loopback-bound port. If the client supervises orchestrator startup, ensure loopback binding and never expose the port externally. *Acceptance:* `lsof`/`netstat` shows the orchestrator port bound to loopback only.
- **REQ-ARCH-071 (MUST)** — Authenticate every control and stream connection with a per-session bearer token/secret shared out-of-band at orchestrator startup; unauthenticated connections rejected. *Acceptance:* A request without the valid token is rejected (401/handshake failure); a second local user cannot connect via default discovery. *(Server side: REQ-BE-071.)*
- **REQ-ARCH-072 (MUST)** — Persisted auth tokens live in the macOS Keychain (or equivalent), never plaintext prefs/logs, scoped against other-app reads. *Acceptance:* The token is in Keychain with proper access control and absent from plist/UserDefaults/logs.
- **REQ-ARCH-073 (MUST)** — Redact tokens, secret-bearing file contents, and any provider material from logs, crash reports, diagnostics. *Acceptance:* Triggering a crash report and reviewing logs shows redacted tokens and no verbatim secret payloads.
- **REQ-ARCH-074 (MUST)** — Read/write only user-granted directories (security-scoped bookmarks); memory writes stay within the granted directory's `.archon/` subtree. *Acceptance:* Access outside a granted directory is denied; opening a project establishes a bookmark reused across launches.
- **REQ-ARCH-075 (SHOULD)** — Plaintext HTTP/WS on loopback is acceptable for MVP; support an optional local TLS/mutual-secret upgrade if the orchestrator offers it, without weakening REQ-ARCH-071.

### 2.H Offline / Backend-Down / Failure Behavior

- **REQ-ARCH-080 (MUST)** — Detect orchestrator unavailability within ≤ 5 s and enter a labeled "orchestrator offline" state without crashing, hanging, or spinning CPU. *Acceptance:* Killing the orchestrator surfaces the offline state within ≤ 5 s; client CPU while offline stays near idle (backoff per REQ-ARCH-007).
- **REQ-ARCH-081 (MUST)** — Degraded read-only mode while offline: browse the tree, view cached scrollback/board snapshots, read/edit memory (atomic/optimistic per REQ-ARCH-053), configure preferences. Orchestrator-requiring actions (spawn/kill/plan/apply) are visibly disabled with the reason. *Acceptance:* With the orchestrator down, the user opens a project, browses files, reads last snapshots; spawn/plan controls are disabled and explain why.
- **REQ-ARCH-082 (MUST)** — Dictation still transcribes while offline (on-device); the resulting intent is queued or clearly rejected (user-configurable), never silently dropped. *Acceptance:* Speaking while offline produces a visible transcript and either a queued intent (delivered on reconnect) or an explicit "cannot dispatch — orchestrator offline" message.
- **REQ-ARCH-083 (MUST)** — Transport failures/timeouts/reconnects MUST NOT auto-kill terminals, auto-mutate the board, or discard user edits; recovery is reconciliation (REQ-ARCH-008/026), never destructive reset. *Acceptance:* Injecting repeated disconnects during active runs leaves orchestrator terminals and board unchanged; the client re-attaches intact.
- **REQ-ARCH-084 (MUST)** — Bounded control-command timeouts (default ≤ 10 s; spawn ack per REQ-ARCH-022) with retry-or-cancel rather than an indefinite spinner; idempotency (REQ-ARCH-021/023) makes retries safe. *Acceptance:* A stalled command shows timeout with retry/cancel within budget; retrying creates no duplicate terminals or board mutations.
- **REQ-ARCH-085 (SHOULD)** — On partial plan application, show per-action success/failure with reasons and offer targeted retry of only failed actions.

---

## 3. Backend Orchestrator

Python-side refactor (FastAPI in place) supporting V3. Assumptions: orchestrator bound to `127.0.0.1`; local embedded store (SQLite assumed) plus on-disk memory files; "terminal" = one PTY-backed agent CLI session; "Conductor" = the Claude-API-driven orchestration layer inside the backend.

### 3.1 Terminal Spawning Policy Engine

- **REQ-BE-001 (MUST)** — One policy engine is the single spawn authority; no path spawns a PTY bypassing it. *Acceptance:* Every spawn entry point is mediated by the engine; a static check finds zero direct PTY-spawn calls outside the engine module.
- **REQ-BE-002 (MUST)** — Auto mode: the Conductor proposes a terminal count and routing plan from intent + kanban state, returned as a structured decision (proposed count, per-terminal task assignment, rationale). *Acceptance:* The engine returns a schema-valid decision with `count ≥ 1`, one assignment per terminal, and a non-empty rationale.
- **REQ-BE-003 (MUST)** — Manual cap overrides the Conductor: clamp effective count to `min(conductor_proposed, user_cap)`, never exceeding `user_cap` for that instruction's session. *Acceptance:* With `user_cap = 2`, `conductor_proposed = 5`, exactly 2 terminals spawn; a third request in-session is rejected `cap_exceeded`.
- **REQ-BE-004 (MUST)** — Absolute hard ceiling on concurrent live terminals (default 8, configurable), overriding any Conductor proposal or user cap above it. *Acceptance:* With ceiling 8, a 9th live terminal is rejected `ceiling_reached`. *(V3 scalability target is 16 concurrent per REQ-PERF-024; the default ceiling is a safety cap, not the maximum supported.)*
- **REQ-BE-005 (MUST)** — Resource-aware admission control against host headroom and per-terminal budgets (REQ-BE-034); refuse or queue spawns that would breach the safety margin (default: keep ≥ 15% free RAM, ≤ 90% projected aggregate CPU). *Acceptance:* On a synthetically constrained host, a spawn is queued (not spawned) with a `spawn_deferred` event naming the limiting resource.
- **REQ-BE-006 (SHOULD)** — Deferred spawns enter a FIFO queue keyed by kanban priority, draining as terminals complete and headroom returns. *Acceptance:* Two deferred spawns of distinct priority drain highest-first when a slot frees.
- **REQ-BE-007 (SHOULD)** — Policy mode/cap can be scoped to a single instruction without changing the persistent default. *Acceptance:* A capped instruction leaves the stored default unchanged.
- **REQ-BE-008 (MUST)** — Every spawn decision is persisted with timestamp, intent reference, proposed count, applied cap, ceiling, final count, and reduction reason. *Acceptance:* After a capped spawn the audit shows proposed=5, cap=2, final=2, reason=`user_cap`.

### 3.2 Kanban as a First-Class Backend Model

- **REQ-BE-010 (MUST)** — Persist a board with ordered columns and tasks as first-class entities; a task carries stable id, title, body/spec, column, ordinal, priority, owner (conductor|user|terminal-id), linked terminal id (nullable), created/updated timestamps, and a monotonic revision. *Acceptance:* Create/read/reorder survives restart with identical ids, ordinals, revisions.
- **REQ-BE-011 (MUST)** — Explicit task state machine: `backlog → ready → in_progress → blocked → review → done` plus terminal `cancelled`; only defined transitions allowed. *Acceptance:* The transition table accepts `ready→in_progress` and rejects `done→in_progress` with `illegal_transition`. *(These task lifecycle states are distinct from the five user-facing board columns of REQ-UX-050 and the five session-status badges of REQ-UX-060; the column↔state mapping is defined in the Glossary/Traceability.)*
- **REQ-BE-012 (MUST)** — The Conductor can create, edit, move, split, and re-prioritize tasks, each attributed owner=`conductor`. *Acceptance:* A Conductor move changes the column and records owner=`conductor` and a new revision.
- **REQ-BE-013 (MUST)** — User and Conductor mutations go through one validated path so invariants (ordinals, legal transitions, ownership) hold identically. *Acceptance:* Identical malformed moves from user and Conductor fail with the same validation error.
- **REQ-BE-014 (MUST)** — Moving a task to `in_progress` is the canonical trigger to bind/spawn a terminal (subject to the policy engine); reaching `done`/`cancelled` releases the bound terminal. *Acceptance:* Dragging to `in_progress` yields a bound terminal id; moving to `done` clears the binding and initiates teardown.
- **REQ-BE-015 (MUST)** — Revision-checked optimistic concurrency; stale-revision writes rejected. *Acceptance:* A write with an outdated revision returns `revision_conflict` and leaves the task unchanged.
- **REQ-BE-016 (MUST)** — Every task/column mutation emits a kanban event (created/updated/moved/deleted, before/after column+ordinal, new revision) over the stream. *Acceptance:* A single move produces exactly one `kanban.task_moved` with the new revision; the client can reconstruct board state from the event stream alone.
- **REQ-BE-017 (SHOULD)** — Full board snapshot on connect, deltas thereafter; no polling. *Acceptance:* A new client receives one snapshot then only deltas.

### 3.3 Directory-Scoped Memory Files API

- **REQ-BE-020 (MUST)** — Memory files are directory-scoped, addressable by `(scope_dir, filename)`, stored human-readable within that directory's memory location. *Acceptance:* Memory written under `/proj/A` does not appear when listing `/proj/B`.
- **REQ-BE-021 (MUST)** — List/read/write operations return content plus metadata (size, mtime, owner, revision, byte checksum). *Acceptance:* After a write, a read returns exact bytes with an incremented revision; list shows correct size and mtime.
- **REQ-BE-022 (MUST)** — Each file records an owner and access class (Conductor/agent/user-authored); agents MUST NOT overwrite Conductor-owned memory unless explicitly granted. *Acceptance:* An agent write to a Conductor-owned, non-shared file is rejected `memory_write_denied`; bytes unchanged.
- **REQ-BE-023 (MUST)** — Concurrent writes serialized with revision-checked, atomic (write-temp-then-rename) semantics; a stale write fails rather than corrupt/partial-write. *Acceptance:* Two concurrent writes with the same base revision: one succeeds, the other `revision_conflict`; the file is never partially written (checksum always valid).
- **REQ-BE-024 (MUST)** — All memory paths validated to resolve inside the declared scope; `..`, symlink escapes, and absolute-path injection rejected. *Acceptance:* A write to `../../etc/passwd` or an escaping symlink is rejected `path_escape` with no filesystem write.
- **REQ-BE-025 (MUST)** — Enforce per-file (default 1 MB) and per-scope (default 32 MB / 512 files) limits. *Acceptance:* A write > 1 MB is rejected `memory_too_large`; the 513th file in a scope is rejected `memory_quota_exceeded`.
- **REQ-BE-026 (SHOULD)** — Memory mutations emit stream events so the client updates without polling. *Acceptance:* External and API writes both produce `memory.changed` with `(scope_dir, filename, revision)`.
- **REQ-BE-027 (COULD)** — Agents COULD receive scoped read access to relevant memory at session start, injected into working context. *Acceptance:* A `/proj/A` terminal observes `/proj/A` shared memory but not `/proj/B`'s.

### 3.4 PTY Session Management

- **REQ-BE-030 (MUST)** — Spawn each agent CLI in a dedicated PTY with defined cwd, environment, and argv; return a stable session id. *Acceptance:* A spawn returns a session id and live PTY; the child runs under the requested cwd.
- **REQ-BE-031 (MUST)** — Multiple clients may attach and receive the same output stream; PTY output streamed incrementally as ordered, sequence-numbered chunks. *Acceptance:* Two consumers receive identical in-order chunk sequences; late attach receives a bounded replay buffer then live tail.
- **REQ-BE-032 (MUST)** — Forward client-originated input to the correct session's PTY. *Acceptance:* Input sent to session S appears at S's child stdin and only S's. *(Whether the client exposes interactive stdin is an open question; see §8.)*
- **REQ-BE-033 (MUST)** — Graceful termination (SIGTERM then SIGKILL after grace, default 5 s) of any session, with guaranteed reaping. *Acceptance:* A kill ends the child within grace+ε; no zombie/orphan remains.
- **REQ-BE-034 (MUST)** — Enforce per-session limits: max RSS (default 1.5 GB), CPU share/nice, max FDs, and an idle timeout (default 30 min no output → flagged, not auto-killed unless configured). *Acceptance:* A session exceeding its RSS limit is throttled/terminated per policy and emits `session.resource_exceeded` naming the limit.
- **REQ-BE-035 (MUST)** — On orchestrator/session crash, detect and reap orphaned children and PTYs on next start; mark stale sessions `terminated` with a reason. *Acceptance:* After a simulated orchestrator kill, restart reaps orphaned PIDs and marks sessions `terminated(reason=crash_recovery)`; RAM reclaimed.
- **REQ-BE-036 (MUST)** — Per-session output retention bounded (default 2 MB ring buffer or 5,000 lines, whichever first). *Acceptance:* A session emitting 100 MB retains ≤ the bound; older output is evicted. *(This server-side retention is distinct from the client's 10,000-line virtualized buffer, REQ-PERF-021.)*
- **REQ-BE-037 (SHOULD)** — Each session carries its bound kanban task id so lifecycle events cross-reference the board. *Acceptance:* A task's session exposes that task id; teardowns are correlated in the audit log.
- **REQ-BE-038 (SHOULD)** — Track aggregate RAM/CPU across live sessions and expose it for admission control (§3.1) and the summary dashboard. *Acceptance:* Aggregate counters equal the sum of live-session measurements within a 2 s window.

### 3.5 Streaming Event Protocol (Server End)

Server end of the transport in §2.A; delivery/rendering is client-side and not restated.

- **REQ-BE-040 (MUST)** — One WebSocket (SSE fallback) multiplexing all event types over subscribable topics; each message a typed, versioned JSON envelope `{ v, type, topic, seq, ts, payload }`. *Acceptance:* A conformance client validates every message against its `type` schema and a strictly increasing per-topic `seq`.
- **REQ-BE-041 (MUST)** — Implement at minimum: `session.output`, `session.status`, `session.lifecycle`, `session.resource_exceeded`; `kanban.snapshot`, `kanban.task_created|updated|moved|deleted`, `kanban.column_changed`; `memory.changed`; `policy.spawn_decision`, `policy.spawn_deferred`; `conductor.message`, `conductor.status`; `error` (typed, stable codes). *Acceptance:* Each type is emitted in an end-to-end scenario and passes schema validation.
- **REQ-BE-042 (MUST)** — Per-topic `seq` monotonic and contiguous for client gap detection. *Acceptance:* Dropping one message causes an observed gap and a successful replay request from last-good `seq`.
- **REQ-BE-043 (MUST)** — Resume a topic from a client-supplied last-seen `seq`, replaying buffered events within a bounded window (default 2,000 events or 60 s), then live. *Acceptance:* A reconnecting client with `last_seq` receives missed events in order, then live, with no duplicates.
- **REQ-BE-044 (MUST)** — Bounded per-connection queues; slow consumers cause no unbounded server RAM growth — coalesce or drop-with-marker (output) or disconnect-with-error (kanban) per a documented per-type policy. *Acceptance:* A stalled consumer causes bounded queue growth then documented shedding; server RSS stays within budget.
- **REQ-BE-045 (SHOULD)** — Clients may subscribe to a topic subset. *Acceptance:* A client subscribed only to `kanban.*` receives no `session.output` frames.
- **REQ-BE-046 (SHOULD)** — Periodic heartbeats (default 15 s). *Acceptance:* With no traffic a heartbeat arrives within the interval; suppressing heartbeats triggers client reconnect.

### 3.6 API Surface (requirement-level)

- **REQ-BE-050 (MUST)** — Expose control endpoints (all loopback): Intent (submit text intent → intent id, triggers planning); Policy (get/set default mode/caps, read audit); Sessions (list/get/spawn/send-input/kill); Kanban (snapshot, create/update/move/delete task, column ops); Memory (list/read/write/delete scoped); Health/version/capabilities. *Acceptance:* Each operation has a documented request/response schema and typed error codes enumerated in an OpenAPI-equivalent document.
- **REQ-BE-051 (MUST)** — Document the full inbound (subscribe/unsubscribe/resume/input) and outbound (§3.5) message set with schemas and version. *Acceptance:* A published catalog lists every type with fields, types, and protocol `v`.
- **REQ-BE-052 (MUST)** — Expose a version and capabilities descriptor; refuse incompatible major versions. *Acceptance:* An unsupported-major request receives `incompatible_version`; capabilities reflect enabled features.
- **REQ-BE-053 (SHOULD)** — Shared typed error envelope `{ code, message, retriable, details }` with a stable code registry (`*_denied`, `*_exceeded`, `*_conflict`, …). *Acceptance:* Three distinct failures return the same shape with registry codes.

### 3.7 Conductor / Provider-Key Management (server-side)

- **REQ-BE-060 (MUST)** — The provider key lives only server-side; no endpoint or stream returns it; the client functions without ever receiving it. *Acceptance:* Static and runtime inspection of all responses/streams shows the key is never transmitted.
- **REQ-BE-061 (MUST)** — Key sourced from environment/secure local storage (Keychain-backed or `0600` file), never hardcoded/logged, redacted in diagnostics. *Acceptance:* Log grep after a full session shows zero key occurrences; a world-readable key file is refused at startup.
- **REQ-BE-062 (MUST)** — Only the server-side Conductor calls the provider API; agent terminals and clients receive no provider credentials. *Acceptance:* Spawned agent environments contain no provider key variable; a code check confirms the single call site.
- **REQ-BE-063 (SHOULD)** — Meter provider usage (tokens/requests) and enforce optional caps; emit `conductor.status` near limits. *Acceptance:* Exceeding a configured request cap halts new Conductor calls and emits a warning before the hard stop.
- **REQ-BE-064 (SHOULD)** — Support hot key rotation without restart. *Acceptance:* Replacing the key at its source and signaling reload makes subsequent calls use the new key with no process restart.

### 3.8 Local Binding, Authentication & Isolation

- **REQ-BE-070 (MUST)** — Bind to `127.0.0.1` only by default; non-loopback binding requires explicit opt-in. *Acceptance:* A default-config server is unreachable from another host; a LAN port scan shows the port closed.
- **REQ-BE-071 (MUST)** — Even on loopback, control + WS connections require a locally issued token/secret. *Acceptance:* A request without the local token is rejected `401/unauthorized`; the legitimate token succeeds. *(Client side: REQ-ARCH-071/072.)*
- **REQ-BE-072 (SHOULD)** — Validate WebSocket upgrade origin to prevent local cross-origin abuse. *Acceptance:* A WS upgrade with a disallowed origin is refused.

### 3.9 Backend Performance & Resource Budgets

- **REQ-BE-080 (MUST)** — Idle backend RSS ≤ 150 MB and idle CPU ≤ 1% of one core (excluding provider calls). *Acceptance:* A 10-minute idle measurement shows RSS ≤ 150 MB and mean CPU ≤ 1%.
- **REQ-BE-081 (MUST)** — Per-live-session bookkeeping overhead (excluding the agent child) ≤ 40 MB RSS. *Acceptance:* Spawning 4 sessions raises orchestrator-attributed RSS by ≤ 160 MB.
- **REQ-BE-082 (SHOULD)** — Median added latency from PTY byte availability to WS emission ≤ 20 ms on the reference machine. *Acceptance:* Over 1,000 chunks, median ≤ 20 ms.
- **REQ-BE-083 (SHOULD)** — Event/async-driven; no idle busy-polling. *Acceptance:* Idle CPU profiling shows no hot loop; wakeups are event-driven.

### 3.10 Backward Compatibility & Migration

- **REQ-BE-090 (MUST)** — Migrate existing persisted state (tasks/board/config) into the new kanban + memory models without data loss. *Acceptance:* Migration on a copy of current data yields the same tasks/columns with mapped states and a migration report listing every record's disposition.
- **REQ-BE-091 (MUST)** — Migration is non-destructive to the source (copy/backup) and idempotently re-runnable. *Acceptance:* Running twice yields identical output; the original store checksum is unchanged.
- **REQ-BE-092 (SHOULD)** — Legacy web-dashboard endpoints are preserved during a transition window or return a typed `gone/deprecated` with guidance, not silent 404s. *Acceptance:* A legacy endpoint returns a documented deprecation response naming the replacement.
- **REQ-BE-093 (SHOULD)** — Legacy statuses without a 1:1 mapping have a documented mapping (e.g. unknown → `backlog`). *Acceptance:* Each legacy status appears once in the mapping table; migrated tasks land in valid states only.
- **REQ-BE-094 (COULD)** — A temporary compatibility adapter may keep old clients functional during rollout. *Acceptance:* An old-client request against the shim returns a valid legacy-shaped response.

---

## 4. UX, Views & Interaction

Orb visual appearance is owned by §5; this section defines structure, views, interaction, and orb *behavioral* states. Status color is deferred to §5 (monochrome iconography + label only).

### 4.1 Navigation Model & Window Structure

- **REQ-UX-001 (MUST)** — A single primary window with three persistent zones: (a) left sidebar (directory-tree navigator + memory-file access); (b) central main pane switching between Individual Terminals, Summary Dashboard, and Codebase; (c) right drawer housing the Kanban board, collapsible to zero width. *Acceptance:* All three zones are independently resizable via drag handles; collapsing the drawer releases its width to the central pane; re-opening restores its last width within ±1 pt.
- **REQ-UX-002 (MUST)** — The floating orb is an always-visible overlay across every main-pane view, never occluded by any panel, sheet, or popover. *Acceptance:* With every view active and every panel at max width, the orb remains fully hit-testable and visible.
- **REQ-UX-003 (MUST)** — The view switcher has exactly three destinations (Individual Terminals, Summary Dashboard, Codebase), reachable via ⌘1/⌘2/⌘3, a segmented control, and Conductor-driven programmatic navigation. *Acceptance:* ⌘1 switches to Individual Terminals within one rendered frame (≤ 8.3 ms at 120 Hz); ⌘2/⌘3 behave identically.
- **REQ-UX-004 (SHOULD)** — Persist navigation state (active view, sidebar/drawer width, kanban scroll offset) across restarts per project directory.
- **REQ-UX-005 (MUST)** — Every interactive control has a shortcut or is reachable via sequential Tab focus; no action exceeds four keystrokes from any reachable focus position. *Acceptance:* Automated traversal confirms every button/toggle/field is Tab-reachable and no required action exceeds four keystrokes from the document root.

### 4.2 Individual Terminals View

- **REQ-UX-010 (MUST)** — Present all active terminals simultaneously in a responsive grid: 1–2 → 1×1/1×2; 3–4 → 2×2; 5–9 → 3×3; > 9 → 4-column grid with vertical scroll. *Acceptance:* Adding/removing a card triggers a reflow completing within 100 ms wall-clock.
- **REQ-UX-011 (MUST)** — Each card shows: (a) session identifier (short name + numeric index); (b) agent type; (c) live auto-scrolling PTY transcript; (d) a status badge (REQ-UX-060); (e) elapsed wall-clock time. *Acceptance:* The transcript updates within 100 ms of new PTY output arriving; the timer increments every second.
- **REQ-UX-012 (MUST)** — A card can be focused by click or keyboard (arrows to navigate, Return to focus), expanding to fill the central pane in a focus mode showing an untruncated scrollable transcript, the associated task title, and per-session actions (Pause, Stop, Copy output). *Acceptance:* Focus mode activates within one rendered frame; Escape or ⌘W returns to the grid without closing the session.
- **REQ-UX-013 (MUST)** — Transcript rendering obeys the client's **10,000-line virtualized ring buffer** of REQ-PERF-021/022 (only visible rows plus buffer are held as rendered cells); older lines are evicted without interrupting scroll position. *Resolution: the draft's 2,000-line retained buffer and 500 KB figure are superseded by the PERF virtualization budget to remove the conflict.* *Acceptance:* Rendered attributed-string memory per terminal stays within the REQ-PERF-021 4 MB budget with 10,000 lines in scrollback.
- **REQ-UX-014 (SHOULD)** — Cards with an error/warning in their last 10 output lines show a subtle border distinction (per §5) without requiring focus.
- **REQ-UX-015 (MUST)** — "Stop All" via toolbar and ⌃⌥S, with a confirmation alert. *Acceptance:* The alert appears within 50 ms of trigger; after confirmation, stop signals dispatch to all sessions within 500 ms.
- **REQ-UX-016 (COULD)** — A "pin to top" affordance keeps a chosen session in grid position 1 regardless of spawn order.

### 4.3 Summary Dashboard View

- **REQ-UX-020 (MUST)** — A condensed single-screen overview (no scrolling at ≥ 1200 × 800 pt) including: (a) sessions active / total spawned this run; (b) sessions by status (idle, running, blocked, error, complete); (c) aggregate token consumption reported by the orchestrator; (d) elapsed run time; (e) last Conductor decision/log entry. *Acceptance:* All five categories are visible simultaneously at 1200 × 800 pt without scrolling.
- **REQ-UX-021 (MUST)** — Aggregate KPI tiles refresh at most 1 Hz; live streaming data (Conductor log, last event) updates ≤ 200 ms from event arrival. *Acceptance:* Injecting 100 rapid events updates KPI tiles ≤ once/second while the event log reflects the last event within 200 ms.
- **REQ-UX-022 (SHOULD)** — A compact non-interactive timeline of spawn/termination events over the run, rendered at ≤ 2% CPU (one core, Apple M-series).
- **REQ-UX-023 (MUST)** — Feature-complete parity with the Archon V2 web dashboard: every KPI/status surface has a native equivalent. *Acceptance:* A side-by-side audit confirms no KPI category is absent.
- **REQ-UX-024 (SHOULD)** — Clicking a status-category tile navigates to Individual Terminals filtered to that status, pre-scrolled to the first matching card.

### 4.4 Voice Interaction Flow

- **REQ-UX-030 (MUST)** — Two activation modes, selectable in Settings: (a) Push-to-talk (hold a configurable key; default Space when focused, or a global hotkey when not frontmost); (b) Wake-word (a continuously listening on-device detector triggers on a fixed phrase). Only one mode active at a time. *Acceptance:* Push-to-talk begins capture within 50 ms of key press; wake-word transitions the orb to Listening within 300 ms of the wake word completing.
- **REQ-UX-031 (MUST)** — During capture, show a live transcription preview (partial hypotheses rendered incrementally, visually distinguished from finalized text — per §5) in the Conductor's central surface, not a modal. *Acceptance:* Partial hypotheses appear within 500 ms of the corresponding speech segment completing (Apple M-series).
- **REQ-UX-032 (MUST)** — On capture end (key release, or ≥ 1.5 s silence timeout in wake-word mode), present an explicit confirmation showing the final transcription, an estimated terminal count (Conductor pre-flight estimate), and Confirm (⏎)/Discard (Esc). *Acceptance:* The surface appears ≤ 500 ms after transcription finalizes; Esc discards with no side effects; ⏎ dispatches within 100 ms.
- **REQ-UX-033 (MUST)** — The confirmation includes an inline "cap at X terminals" spinner (min 1, max server-side limit, default 8) adjustable without restarting transcription or closing the surface. *Acceptance:* Changing the cap and pressing ⏎ dispatches with the updated cap in the API payload.
- **REQ-UX-034 (MUST)** — If the pre-flight estimate exceeds the cap, show a plain-language warning ("Conductor estimates N terminals needed; cap is M — work may be incomplete") without blocking confirmation. *Acceptance:* With mock estimate N > cap M, the warning is visible before ⏎.
- **REQ-UX-035 (SHOULD)** — The voice flow is fully keyboard-operable (activation key, VoiceOver read-back, cap spinner via arrows, ⏎/Esc).
- **REQ-UX-036 (MUST)** — In push-to-talk with a global hotkey, capture activates even when not frontmost; the app requests only the microphone entitlement and MUST NOT require accessibility permission solely for the hotkey (use a notarization-compatible mechanism). *Acceptance:* The app ships with a valid notarization receipt and the global hotkey activates capture from another app.

### 4.5 Floating Orb: Behavioral States

- **REQ-UX-040 (MUST)** — The orb operates in exactly six named behavioral states, all transitions deterministic and driven by the orchestrator event stream plus local WhisperKit events:

| State | Meaning | Entry | Exit |
|---|---|---|---|
| **Idle** | No active session; not listening | All sessions terminated / no run | Any of the five below |
| **Listening** | Mic active; capturing intent | PTT key down OR wake word | Key release / silence / Discard |
| **Thinking** | Intent dispatched; Conductor planning | Confirmation dispatched | First spawn event OR error |
| **Spawning** | Conductor opening terminals | First spawn event received | All requested sessions open |
| **Streaming** | ≥ 1 session running; PTY flowing | All open and ≥ 1 active | All sessions reach terminal states |
| **Error** | Conductor or session(s) in error | Any unrecoverable error event | User dismisses OR new intent |

*Acceptance:* An automated sequence exercising all transitions (Idle→Listening→Thinking→Spawning→Streaming→Idle; Streaming→Error→Idle) verifies each transition causes exactly the correct next state within 200 ms. *(These six behavioral states are canonical; the §5 hue-zone table REQ-DSN-013 must map to them — see the consolidated Open Question on freezing the Conductor/orb state enumeration.)*
- **REQ-UX-041 (MUST)** — The orb's behavioral state is the single source of truth for orchestration status; no secondary status bar/badge duplicates it. *Acceptance:* A user can identify the current phase from the orb state alone, without reading a textual label.
- **REQ-UX-042 (MUST)** — The orb is user-draggable within the main window; default position bottom-center of the central pane; new position persists across sessions. *Acceptance:* Drag to the top-right quadrant, quit/relaunch; the orb reappears there within ±8 pt.
- **REQ-UX-043 (SHOULD)** — A single click activates voice input (equivalent to PTT) in Idle/Streaming; in Thinking/Spawning it offers "Cancel planning" with a confirmation alert.

### 4.6 Kanban Board

- **REQ-UX-050 (MUST)** — Exactly five columns, fixed order: Queued, In Progress, Blocked, Review, Done. Not renameable/deletable in V3. *Acceptance:* All five render in order at every drawer width ≥ 280 pt. *(Columns map to the backend task state machine REQ-BE-011: Queued ⇄ backlog/ready; In Progress ⇄ in_progress; Blocked ⇄ blocked; Review ⇄ review; Done ⇄ done; `cancelled` is a terminal state surfaced as removal.)*
- **REQ-UX-051 (MUST)** — Each card shows: (a) task title (max 80 chars, ellipsis); (b) assigned session id or "Unassigned"; (c) creation timestamp; (d) a status badge synced to session status (REQ-UX-060). *Acceptance:* A session-status change via the event stream updates the badge within 200 ms.
- **REQ-UX-052 (MUST)** — The Conductor may programmatically create/update (title, column, assignee)/delete cards via the event stream, applied as animated transitions (add: slide-in from column top; move: cross-column fly, 150 ms; remove: fade-out 100 ms). *Acceptance:* 20 Conductor-driven ops at 5/s produce no dropped updates and no frame < 60 Hz during the sequence.
- **REQ-UX-053 (MUST)** — The user may create (+ inline title field), edit (double-click), move (drag-drop), and delete (⌫ with confirmation) cards. *Acceptance:* All four complete without a modal sheet; all are reversible via ⌘Z within the session.
- **REQ-UX-054 (MUST)** — On simultaneous Conductor+user modification of the same card (conflict window < 500 ms), policy is last-write-wins with the user taking precedence; the displaced Conductor change is logged silently, no error alert. *Acceptance:* Injecting a Conductor update and a user edit within 100 ms on the same field yields the user's value; the Conductor log records the displaced op.
- **REQ-UX-055 (SHOULD)** — Dragging a card Queued→In Progress offers a non-blocking banner "Assign this to an available terminal?" that expires after 5 s.
- **REQ-UX-056 (MUST)** — Handle 0–100 cards per column without horizontal overflow (vertical scroll within a column); total up to 500 cards must not degrade scroll below 60 fps. *Acceptance:* With 500 cards (100/column), scrolling each column stays ≥ 60 fps (Metal HUD) on a supported Mac. *(See also REQ-PERF-026: ≥ 90 Hz during drag with up to 200 cards.)*

### 4.7 Session & Task Status Model

- **REQ-UX-060 (MUST)** — All status indicators (terminal badges, kanban badges, dashboard tiles) use one five-state vocabulary — **Idle** (opened, no task started), **Running** (actively executing), **Blocked** (awaiting input/dependency), **Error** (unrecoverable fault), **Done** (completed successfully) — rendered exclusively via monochrome iconography + label (no color; visual treatment per §5). *Acceptance:* A user identifies each of the five from icon + label alone with 100% accuracy after a 30-second orientation.

### 4.8 Codebase View

- **REQ-UX-070 (MUST)** — The left sidebar hosts a directory-tree navigator bound to a single project directory (user-set or inferred from the Conductor's cwd), supporting expand/collapse (⌘→/⌘←), keyboard traversal (↑/↓), and file selection opening a read-only diff/preview in the central pane. *Acceptance:* A 10,000-node tree renders without scroll jank (no frame < 60 fps) and expand/collapse responds ≤ 16 ms.
- **REQ-UX-071 (MUST)** — Show file-change indicators for files modified during the current run (• prefix, styled per §5), updating within 1 s of the change reaching the app. *Acceptance:* Writing to a file shows the indicator within 1 s.
- **REQ-UX-072 (MUST)** — Selecting a file replaces the central pane with a read-only unified diff (if modified this run) or a read-only raw preview otherwise; switching files ≤ 100 ms. *Acceptance:* Selecting 10 files rapidly switches each within 100 ms with no content bleed-through.
- **REQ-UX-073 (MUST)** — The central "personal intelligence" surface is singular: only one preview/diff/Conductor-dialogue surface at a time; no split panes, tab groups, or secondary panels. *Acceptance:* Opening a second file replaces the first; no mechanism splits the central pane.
- **REQ-UX-074 (SHOULD)** — The diff view groups hunks by file section, jumps between hunks via ⌥↓/⌥↑, and shows line-number annotations for original and modified.
- **REQ-UX-075 (COULD)** — A full-text search field (⌘F when the tree has focus) filters the tree to matching names with highlight, supporting basic glob patterns.

### 4.9 Memory Files

- **REQ-UX-080 (MUST)** — Memory files appear in a dedicated collapsible "Memory" section at the bottom of the left sidebar, listing files scoped to the current project directory. *Acceptance:* Memory files are visible within 500 ms of setting the project directory, even with > 1,000 tree nodes.
- **REQ-UX-081 (MUST)** — Selecting a memory file opens it in an editable central-pane text surface; edits auto-save with a 1 s debounce; plain-text and Markdown-render toggle. *Acceptance:* 1 s after the last keystroke, the on-disk file matches the surface content. *(Writes go through the atomic/optimistic protocol of REQ-ARCH-053 / REQ-BE-023.)*
- **REQ-UX-082 (MUST)** — The user can create (+ in the Memory section) and delete (⌫ with confirmation) memory files, reflected on disk immediately. *Acceptance:* Create and delete; `ls` confirms presence/absence within 200 ms.

### 4.10 Empty, Loading & Error States

- **REQ-UX-090 (MUST)** — Every view defines an explicit empty state with a single concise instruction and the relevant activation affordance (e.g. "Speak or type to start"). *Acceptance:* Launching with no active run shows each view's empty state with no blank areas or missing-content placeholders.
- **REQ-UX-091 (MUST)** — Initial data load (sessions, kanban, tree) completes within 2 s of the WebSocket connecting; during load a non-blocking skeleton shimmer (per §5) occupies the view; no spinner modal. *Acceptance:* On a cold launch with 500 ms simulated delay, each view exits skeleton within 2 s; no modal spinner appears.
- **REQ-UX-092 (MUST)** — WebSocket disconnection surfaces as a persistent non-modal banner ("Disconnected from orchestrator — reconnecting…"), auto-dismissed on reconnect. *Acceptance:* Killing the orchestrator shows the banner within 3 s; restarting dismisses it within 3 s of reconnect.
- **REQ-UX-093 (MUST)** — Orchestrator-reported recoverable errors (session crash, Conductor failure) surface as inline cards in the Error column and a Conductor-log entry, no modal; unrecoverable errors (process exit) use a single dismissible alert. *Acceptance:* A session-crash event appears in the Error column within 200 ms with no modal; a process-exit event shows an alert.
- **REQ-UX-094 (SHOULD)** — Error messages use plain language naming the failed component and a next action; no raw stack traces in the UI (only via "Show details").

### 4.11 Accessibility

- **REQ-UX-100 (MUST)** — Every interactive element has an accessibility label, role, and value per macOS conventions; VoiceOver navigates all views, triggers all primary actions, and reads all status without a pointer. *Acceptance:* Full VoiceOver + keyboard traversal announces and activates every actionable element.
- **REQ-UX-101 (MUST)** — Respect system Dynamic Type; all text scales; no clipping/incorrect truncation at xxxLarge. *Acceptance:* At xxxLarge, no text is visually clipped within its container across all three views and the board.
- **REQ-UX-102 (MUST)** — With Reduce Motion enabled, all SwiftUI/Metal animations degrade gracefully: (a) orb state changes use a ≤ 150 ms cross-dissolve instead of fluid morph; (b) card add/move/remove become instant visibility changes; (c) layout reflows use no spring. *Acceptance:* With Reduce Motion on, exercising all transitions shows no motion-heavy effect and full functionality. *(Full substitution table in §5, REQ-DSN-071.)*
- **REQ-UX-103 (MUST)** — All text meets WCAG 2.1 AA contrast at default size (≥ 4.5:1 body, ≥ 3:1 large ≥ 18 pt regular / ≥ 14 pt bold). *Acceptance:* An automated contrast audit on every text style in Light and Dark modes reports no failures.
- **REQ-UX-104 (SHOULD)** — A fully equivalent text-input path (persistent text field in the Conductor surface, same confirmation step as REQ-UX-032) enables operating the app identically without voice.

---

## 5. Visual Design System & Motion

### 5.1 Palette & Design Tokens

- **REQ-DSN-001 (MUST)** — Static UI uses a strictly achromatic palette; no other colors on static surfaces.

| Token | Role | sRGB Hex | P3 (R,G,B) | L\* |
|---|---|---|---|---|
| `ink-0` | Pure black | `#000000` | 0.000,0.000,0.000 | 0 |
| `ink-5` | Near-black surface | `#0D0D0D` | 0.051,0.051,0.051 | 3 |
| `ink-10` | Raised dark surface | `#1A1A1A` | 0.102,0.102,0.102 | 7 |
| `ink-20` | Secondary dark | `#333333` | 0.200,0.200,0.200 | 16 |
| `ink-40` | Mid-grey, disabled text | `#666666` | 0.400,0.400,0.400 | 32 |
| `ink-60` | Secondary text, borders | `#999999` | 0.600,0.600,0.600 | 49 |
| `ink-80` | Primary text on dark | `#CCCCCC` | 0.800,0.800,0.800 | 67 |
| `ink-90` | High-emphasis text/icon | `#E6E6E6` | 0.902,0.902,0.902 | 78 |
| `ink-95` | Near-white surface | `#F3F3F3` | 0.953,0.953,0.953 | 88 |
| `ink-100` | Pure white | `#FFFFFF` | 1.000,1.000,1.000 | 100 |

*Acceptance:* A full-resolution pixel audit of any shipped screen returns zero pixels where R ≠ B or G ≠ B (sRGB) on any non-animation surface; automated in CI per release build.
- **REQ-DSN-002 (MUST)** — Every semantic role resolves to exactly one token; no color literals outside the single canonical token file. *Acceptance:* `grep -rn "Color(red:" Sources/` and `grep -rn "Color(hex:" Sources/` return zero matches outside the token file at every review gate.
- **REQ-DSN-003 (MUST)** — The role→token mapping covers at minimum: `background`, `surface-raised`, `surface-floating`, `border-subtle`, `border-strong`, `text-primary`, `text-secondary`, `text-disabled`, `icon-primary`, `icon-secondary`, `selection-fill`, `selection-border` (mode-specific per §5.9). *Acceptance:* One `DesignTokens.swift` enumerates all roles and per-mode assignments; no other source references a palette step directly (enforced by SwiftLint).

### 5.2 Color Restriction Rule

- **REQ-DSN-011 (MUST)** — Chromatic color (Display-P3 LCH chroma > 0.005) is forbidden on every surface except: (1) the Orb body and its immediate glow/bloom shadow layer; (2) the Orb's listening-state ripple field ≤ 120 pt radius from center; (3) per-frame Conductor state-transition overlays, max bleed radius 200 pt from the Orb boundary, max composited opacity 0.35 over any non-Orb pixel. All other pixels are strictly achromatic at all times, including during layout animations and window resize. *Acceptance:* At any settled frame, a full-window P3 scan finds zero pixels with LCH chroma > 0.005 outside the three surfaces (Metal-readback test in CI).
- **REQ-DSN-012 (MUST)** — Chromatic pixels render in Display P3; the window declares `NSColorSpace.displayP3`. P3-beyond-sRGB values are permitted in the Orb layer and composited without clamping to sRGB before display. *Acceptance:* `CAMetalLayer` introspection confirms `kCGColorSpaceDisplayP3` for the Orb's backing layer at launch; a reference P3 swatch reads outside sRGB gamut on a P3 display.
- **REQ-DSN-013 (MUST)** — Each Conductor state maps to a hue zone within the Orb (normative range + minimum peak chroma; exact trajectories left to the motion designer):

| Conductor State | Hue range (LCH°) | Min P3 chroma at peak |
|---|---|---|
| Idle / resting | 255–290 (blue-violet) | 0.22 |
| Listening | 200–260 (cyan-indigo) | 0.30 |
| Thinking / planning | 280–330 (violet-magenta) | 0.28 |
| Spawning | 160–210 (teal-cyan) | 0.25 |
| Streaming / success | 140–170 (green-teal) | 0.22 |
| Error / blocked | 15–45 (red-orange) | 0.30 |

*Resolution: this table is reconciled to the six canonical orb behavioral states of REQ-UX-040; the draft's "Success / complete" row is mapped to the **Streaming** state's hue zone. Finalizing/splitting a distinct success cue is tracked in the Open Questions.* *Acceptance:* Automated colorimetry of QA reference screenshots per state confirms dominant Orb hue within range and peak chroma ≥ the minimum.
- **REQ-DSN-014 (SHOULD)** — Interpolate hue transitions in LCH (not RGB/HSL) to avoid grey crossings; transition ≤ 600 ms (99% spring-settled).
- **REQ-DSN-015 (MUST)** — The Orb layer produces no color fringing on achromatic UI: `normal` blend within its boundary; the bloom uses a separate lower-res `screen` overlay clipped to the permitted bleed radius (REQ-DSN-011). *Acceptance:* Pixels at exactly 201 pt from Orb center during peak saturation show LCH chroma < 0.005 (∆E < 1 from neutral).

### 5.3 Liquid Glass Surface Classification

- **REQ-DSN-021 (MUST)** — Every visible background surface is exactly one material type (static at component level, except the §5.9 mode switch):

| Material | Description | Surfaces |
|---|---|---|
| `glass-floating` | Blur, refractive rim, specular | Orb container shell, floating command palette, detached inspector popover, toasts |
| `glass-sidebar` | Reduced blur (≤ 20 pt), no rim | Primary sidebar, Conductor presence panel |
| `flat-surface` | Solid achromatic, opaque, no blur | Terminal panels, kanban card bodies, main content bg, menu bar extra |
| `flat-elevated` | Solid, one ramp step from parent | Kanban column headers, selected-row highlight, tab bar |
| `flat-hairline` | 1 px achromatic stroke, no fill | All borders, dividers, resize handles |

*Acceptance:* Every View with a visible background is tagged with exactly one type via an `archonMaterial(_:)` modifier; no other background mechanism (SwiftLint-enforced).
- **REQ-DSN-022 (MUST)** — `glass-floating` conforms to macOS 26 Liquid Glass via the highest-fidelity public API: background blur (`NSVisualEffectView` / `.ultraThinMaterial` / `.regularMaterial`), refractive rim (≤ 1.5 pt, white ≤ 0.5 opacity) on leading/top, inner shadow (≤ 6 pt spread, black ≤ 0.2 opacity) on trailing/bottom. *Acceptance:* Side-by-side with a native macOS 26 Liquid Glass element at 200% zoom shows no perceptible discrepancy in blur radius, rim width, or corner radius to a trained observer.
- **REQ-DSN-023 (MUST)** — No Liquid Glass surface carries a chromatic tint; vibrancy stays colorimetrically neutral. *Acceptance:* A `Color.red` rect behind each `glass-floating` surface reads LCH chroma < 0.03 through the glass at a center sample.
- **REQ-DSN-024 (SHOULD)** — Glass panels occluded > 80% drop the blur render pass (instantaneous, no cross-fade) to save GPU.
- **REQ-DSN-025 (MUST)** — Terminal panels always use `flat-surface` — fully opaque, never translucent/vibrancy — background `ink-5` (dark) or `ink-95` (light), zero alpha. *Acceptance:* A terminal panel over a colorful wallpaper shows zero wallpaper transmission; body-size mono text on `flat-surface` confirms WCAG 2.1 AA (≥ 4.5:1).

### 5.4 Typography Scale

- **REQ-DSN-031 (MUST)** — Non-terminal text uses SF Pro (Display ≥ 20 pt, Text < 20 pt) via `.font(.system(...))` with named semantic roles; SF Mono only for terminal output, code content, and agent command display. No third-party/custom typeface.
- **REQ-DSN-032 (MUST)** — Normative type scale (no size/weight/tracking outside this table except user-configurable terminal mono size 11–18 pt):

| Role | Family | Size | Weight | Line height | Tracking |
|---|---|---|---|---|---|
| `display` | SF Pro Display | 28 | Semibold | Auto | -0.5 |
| `title-1` | SF Pro Display | 22 | Semibold | Auto | -0.3 |
| `title-2` | SF Pro | 17 | Semibold | Auto | -0.2 |
| `body` | SF Pro | 15 | Regular | 22 | 0 |
| `body-emphasis` | SF Pro | 15 | Medium | 22 | 0 |
| `caption` | SF Pro | 12 | Regular | 16 | +0.1 |
| `caption-emphasis` | SF Pro | 12 | Medium | 16 | 0 |
| `mono-body` | SF Mono | 13 | Regular | 19 | 0 |
| `mono-sm` | SF Mono | 11 | Regular | 16 | 0 |

*Acceptance:* A `TextStyle` enum enumerates all roles; Preview snapshot tests assert each renders at its point size ± 0.5 pt and exact weight on the reference display.
- **REQ-DSN-033 (MUST)** — Respect Dynamic Type; all text except terminal content and `mono-sm` fixed-cell labels scales with the nearest macOS text style. *Acceptance:* At "Large", no label clips or overlaps in any primary view (automated snapshot test).
- **REQ-DSN-034 (SHOULD)** — Use `.fontDesign(.default)`; no override of subpixel AA, no synthetic bold/italic.

### 5.5 Spacing & Grid

- **REQ-DSN-041 (MUST)** — All static measurements are multiples of 4 pt; normative tokens `space-xs`=4, `space-sm`=8, `space-md`=16, `space-lg`=24, `space-xl`=32, `space-2xl`=48 pt. Sub-4 pt permitted only for 1-px hairlines and sub-pixel animation offsets. *Acceptance:* View Debugger measurement of the three primary views confirms all inter-element gaps within 0.5 pt of a 4 pt multiple.
- **REQ-DSN-042 (MUST)** — Minimum window 900 × 600 pt; breakpoints: Compact < 1100 pt (sidebar → 48 pt icon rail); Regular 1100–1599 pt (sidebar 220 pt + main); Wide ≥ 1600 pt (sidebar 260 pt + main + optional 280 pt inspector). *Acceptance:* Snapshot tests at 1099/1100/1599/1600 pt in both modes show correct layout, no overlap or clipping.
- **REQ-DSN-043 (MUST)** — Normative corner radii: floating glass panel 16 pt; card/kanban cell 12 pt; button/chip 8 pt; tag/badge 4 pt; input field 6 pt; Orb container circular (radius = 50% diameter); window system-managed.

### 5.6 Iconography

- **REQ-DSN-046 (MUST)** — All functional icons use SF Symbols (macOS 26-compatible); symbol weight matches surrounding text at the same size; no third-party/bitmap icons. *Acceptance:* `grep -rn "Image(named:" Sources/UI/` returns zero matches; only `Image(systemName:)`.
- **REQ-DSN-047 (MUST)** — Icons render achromatic: `icon-primary` (active/selected), `icon-secondary` (default), `icon-disabled` (inactive); no `.tint`/accent, no multicolor SF Symbols. *Acceptance:* Pixel sampling at each icon centroid confirms LCH chroma < 0.01.
- **REQ-DSN-048 (SHOULD)** — Custom Archon glyphs (spawn terminal, Conductor presence, memory file) designed at 24 × 24 pt, 1.5 pt stroke, monochrome vector, integrated as `.symbolset` harmonizing with system SF Symbols.
- **REQ-DSN-049 (MUST)** — Icon sizes align to the grid and use only 16 (inline/caption), 20 (toolbar/row actions), 24 (primary nav), 32 (empty-state illustrations) pt.

### 5.7 Orb & Fluid Motion Language

- **REQ-DSN-051 (MUST)** — The Orb is a persistent always-visible element in its own Metal-backed compositing layer, independent of the SwiftUI hierarchy; the sole animated chromatic field. Default diameter 56 pt (resting), expanding to max 96 pt during active listening; non-modal. *Acceptance:* A UI test asserts the Orb layer's frame is non-zero and in-window bounds on each of the three primary views, unoccluded by any panel/popover/chrome.
- **REQ-DSN-052 (MUST)** — The Orb color field is a Metal fragment shader implementing ≥ two-layer fluid noise (domain-warped simplex or equivalent) evolving continuously; non-repetitive, physically plausible, no visible tiling/banding/regularity. *Acceptance:* A trained observer over 30 s cannot identify a repeating cycle; the time parameter's perceptible repetition period is ≥ 120 s (frame-hash comparison at 1 Hz over 120 s).
- **REQ-DSN-053 (MUST)** — The Orb shader targets 120 Hz and completes all per-frame GPU compute within **4 ms GPU time** on Apple Silicon (Orb shader + bloom combined), per the §6 animation GPU budget. *Acceptance:* A 10 s GPU trace (listening state, peak load) shows p99 combined GPU time ≤ 4 ms/frame and zero dropped frames at 120 Hz on the reference hardware.
- **REQ-DSN-054 (MUST)** — The Orb responds to voice amplitude in real time with ≤ 16 ms latency from audio sample timestamp to first different rendered frame; during listening, outer glow radius and turbulence scale with the amplitude envelope. *Acceptance:* A 2 s amplitude ramp (440 Hz tone) yields monotonically growing glow radius, with no frame where radius decreases against still-increasing amplitude.
- **REQ-DSN-055 (MUST)** — Named motion events use these spring parameters (all critically or lightly underdamped, ≤ one half-oscillation overshoot):

| Motion event | Stiffness (N/m) | Damping (N·s/m) | 99% settle |
|---|---|---|---|
| Orb idle → listening expand | 280 | 24 | ≤ 350 ms |
| Orb listening → idle contract | 200 | 20 | ≤ 450 ms |
| Orb listening → thinking morph | 320 | 26 | ≤ 300 ms |
| Terminal panel spawn (slide+fade) | 240 | 22 | ≤ 400 ms |
| Terminal panel dismiss | 300 | 28 | ≤ 300 ms |
| Kanban card drag-release settle | 350 | 30 | ≤ 250 ms |
| Primary view switch (cross-slide) | 260 | 24 | ≤ 380 ms |
| Sidebar collapse / expand | 220 | 22 | ≤ 420 ms |

*Acceptance:* Each event's measured settle (first motion frame → < 1% overshoot) falls within ± 20% of the stated value; SI constants converted to `Animation.spring(response:dampingFraction:)` via the documented reference (OQ on spring conversion).
- **REQ-DSN-056 (MUST)** — No UI animation uses a linear timing function; every animated change uses (a) a REQ-DSN-055 spring, (b) a custom ease-in-out cubic Bézier (x₁ < 0.5, x₂ > 0.5), or (c) system `.easeInOut` for micro-interactions ≤ 150 ms. Applies to opacity, geometry, layer, and color transitions. *Acceptance:* A SwiftLint rule flags any `Animation.linear`, `CAMediaTimingFunction(name: .linear)`, or `.timingCurve(0,0,1,1,…)`; zero violations at release.
- **REQ-DSN-057 (MUST)** — The idle Orb exhibits continuous low-amplitude breathing: ± 4 pt radius at 0.15 Hz (~6.7 s/breath) plus slow fluid color drift; breathing never fully stops while the Conductor is active. *Acceptance:* Boundary-radius sampling at 2 Hz over 30 s confirms oscillation in [r−4, r+4] pt, period 6.5–7.0 s, and radius change at least once in any 2-second window.
- **REQ-DSN-058 (SHOULD)** — A soft chromatic bloom rendered as a separate Metal layer at 50% resolution, blurred, composited below the Orb with `screen`, updated at 30 Hz regardless of display refresh.
- **REQ-DSN-059 (MUST)** — All non-Orb layout transitions complete within 400 ms (99% settle) and must not push frame render time above 16.7 ms (60 FPS floor) during the transition. *Acceptance:* A Core Animation trace during any transition shows zero frames exceeding 16.7 ms within the transition window. *(Cross-validated against §6; see the reconciliation Open Question.)*
- **REQ-DSN-060 (SHOULD)** — Shallow parallax: the Orb and `glass-floating` panels shift ≤ ± 2 pt with cursor position; cursor updates throttled to 30 Hz; disabled under Reduce Motion.
- **REQ-DSN-061 (MUST)** — User-initiated animations (drag/click/resize) produce a visible first frame within one display frame (≤ 8.3 ms at 120 Hz, ≤ 16.7 ms at 60 Hz) of the input event; no `Task.sleep`/`asyncAfter` before first visual response. *Acceptance:* Hang-Detection and Frame-Delay traces show zero > 16 ms input-to-first-frame instances across all interactive animations.

### 5.8 Reduced-Motion & Energy-Saver Variants

- **REQ-DSN-071 (MUST)** — With Reduce Motion enabled, apply unconditionally (same information, alternative expression): Orb fluid field → static radial gradient; Orb state transition → 120 ms cross-fade between static gradient states; panel spawn/dismiss → 120 ms opacity fade (no translation); view switch → 150 ms cross-fade; kanban drag-release → instant snap; sidebar collapse/expand → 100 ms opacity fade (no width animation); parallax → disabled. *Acceptance:* With `accessibilityDisplayShouldReduceMotion == true`, no animated transform exceeds 2 pt translation, 2% scale, or 2° rotation, and the Orb renders as a static gradient.
- **REQ-DSN-072 (MUST)** — With Low Power Mode active, additionally and silently: Orb shader loop → 30 Hz; bloom disabled (`isHidden = true`); any blur > 10 pt effective radius → solid achromatic `surface-floating` fill. Stacks with Reduce-Motion. *Acceptance:* With Low Power Mode on, GPU counters show ≤ 50% of baseline GPU utilization during Orb animation; bloom `isHidden == true`.
- **REQ-DSN-073 (SHOULD)** — On < 90 Hz displays, springs adapt their integration step to the frame interval so wall-clock settle times stay within REQ-DSN-055 (constants are display-rate-independent).
- **REQ-DSN-074 (MUST)** — Never prevent display sleep or the idle timer; pause the Orb render loop entirely when minimized, occluded, or the display sleeps; resume within one frame of becoming visible. *Acceptance:* With the window minimized 60 s, Energy Log shows zero GPU wakeups attributable to the Orb shader.

### 5.9 Light / Dark Mode

- **REQ-DSN-081 (MUST)** — Default to dark mode independent of system appearance (max Orb contrast, terminal/code legibility, reduced fatigue); user may override to light and the preference persists.
- **REQ-DSN-082 (MUST)** — Light mode fully supported; per-mode role→token mapping:

| Role | Dark | Light |
|---|---|---|
| `background` | `ink-5` | `ink-95` |
| `surface-raised` | `ink-10` | `ink-90` |
| `surface-floating` | `ink-10` | `ink-95` |
| `text-primary` | `ink-90` | `ink-10` |
| `text-secondary` | `ink-60` | `ink-40` |
| `text-disabled` | `ink-40` | `ink-60` |
| `border-subtle` | `ink-20` | `ink-80` |
| `border-strong` | `ink-40` | `ink-60` |
| `icon-primary` | `ink-90` | `ink-10` |
| `icon-secondary` | `ink-60` | `ink-40` |
| `selection-fill` | `ink-20` | `ink-80` |
| `selection-border` | `ink-40` | `ink-60` |

*Acceptance:* Snapshot tests in both modes confirm correct token rendering for every role; switching modes updates all static surfaces within one frame with no stale-color artifacts.
- **REQ-DSN-083 (MUST)** — Mode switch is a 200 ms simultaneous opacity cross-fade of all static surfaces; the Orb color field is visually continuous; no element shifts position. *Acceptance:* A recording shows cross-fade in 200 ± 20 ms, zero position changes, uninterrupted Orb animation.
- **REQ-DSN-084 (SHOULD)** — In light mode `glass-floating` uses `.regularMaterial`; verify transmitted tint stays perceptually achromatic (∆E < 2) over the five most common macOS 26 default wallpaper hues; if exceeded, apply an achromatic overlay ≤ 0.1 opacity.

### 5.10 Design-Grade Acceptance Criteria

- **REQ-DSN-091 (MUST)** — Temporal coherence: a trained observer watching the Orb 60 s in any single state reports no "wrong" moment (no jank, banding, noise tiling, texture discontinuity). Verified frame-by-frame from a 120 Hz recording.
- **REQ-DSN-092 (MUST)** — Spring feel: ≥ 3 designers unfamiliar with Archon rate spring feel "appropriate"/"satisfying" (≥ 4/5) vs SwiftUI default `.spring()` in an A/B test before beta.
- **REQ-DSN-093 (MUST)** — Typographic silence: in a settled view with no active session, a first-time observer reads all labels and identifies the three-level hierarchy within 3 s using only typography (no color/iconography); ≥ 3 observers.
- **REQ-DSN-094 (MUST)** — Contrast near the glow: at peak Orb chroma in dark mode, all `text-primary` labels within 10 pt of the glow boundary maintain ≥ 4.5:1 against their local background. *Acceptance:* Automated contrast sampling of all such pixels during a peak frame asserts ≥ 4.5:1; zero failures.
- **REQ-DSN-095 (MUST)** — Motion economy: no sequence animates more than one independent layer simultaneously unless part of a single logical element (Orb body + glow) or co-triggered by one input; Conductor-initiated spawns are the explicit exception (up to N panels when N terminals spawn in one step). *Acceptance:* No test scenario triggers simultaneous independent animation of > 2 unrelated elements, except spawn sequences where animating panels equal simultaneously spawning terminals.
- **REQ-DSN-096 (SHOULD)** — Pass the "10-second screenshot test": a static screenshot of any primary stable-state view elicits a spontaneous positive quality signal from a macOS-familiar observer before any description.

---

## 6. Performance & Resource Budgets

All hard budgets are for the reference machine (M4 Pro, 24 GB, macOS 26.0, NVMe). Where a lesser/greater machine differs, the requirement notes it.

### 6.1 Memory

- **REQ-PERF-001 (MUST)** — Idle RSS (no terminals, no dictation, no pending work) ≤ **80 MB**. *Acceptance:* 60 s after cold launch, `footprint -q Archon` reports RSS ≤ 80 MB; three passes must all pass.
- **REQ-PERF-002 (MUST)** — Marginal RSS per open terminal ≤ **30 MB**, inclusive of PTY handle, 10,000-line scrollback ring (lines ≤ 512 bytes), attributed-string cache for visible rows, and per-session UI state. *Acceptance:* Opening N = 1, 4, 8 terminals sequentially, incremental RSS per terminal averaged over each batch ≤ 30 MB (Instruments Allocations, Live Bytes).
- **REQ-PERF-003 (MUST)** — With **8 concurrent active terminals** (each producing output, scrollback at 10,000-line cap), total RSS ≤ **340 MB** (= 80 + 8×30 + 20 headroom). *Acceptance:* The stress harness fills 8 terminals' scrollback; Allocations snapshot RSS ≤ 340 MB. *(This is the authoritative budget referenced by REQ-VIS-032.)*
- **REQ-PERF-004 (SHOULD)** — Kanban board, directory tree, and summary dashboard combined add ≤ **15 MB** RSS when all three are visible alongside 8 terminals.
- **REQ-PERF-005 (MUST)** — No runaway growth: over a 30-minute soak with 4 terminals streaming continuously and view-switching, RSS growth above 4-terminal steady-state ≤ **10 MB**. *Acceptance:* Allocations Generations view: leaked bytes < 5 MB; RSS delta < 10 MB.

### 6.2 CPU

- **REQ-PERF-006 (MUST)** — Idle CPU ≤ **1.0%**. *Acceptance:* `top -l 60 -pid <PID>` average ≤ 1.0% over 60 s.
- **REQ-PERF-007 (MUST)** — During a full UI animation, main-thread CPU ≤ **8%** and total process CPU ≤ **20%** (animation is GPU-offloaded; CPU covers geometry, layout, dispatch). *Acceptance:* Time Profiler filtered to animation intervals (os_signpost, REQ-PERF-032): main-thread ≤ 8%, total ≤ 20%, for orb-listen start, orb-dismiss, view-switch.
- **REQ-PERF-008 (MUST)** — With 8 terminals streaming aggregate 5,000 lines/sec, process CPU ≤ **35%** total (≤ 3.5 E-core equivalents). *Acceptance:* Harness drives 8 × 625 lines/sec; `top -l 30` average ≤ 35%.
- **REQ-PERF-009 (SHOULD)** — WhisperKit transcription adds ≤ **25%** process CPU beyond baseline streaming load.

### 6.3 Frame Rate & Animation Smoothness

- **REQ-PERF-010 (MUST)** — All transitions/animations/scrolling target **120 Hz** on ProMotion; frame rate never drops below **90 Hz** during any user-initiated animated transition. *Acceptance:* Core Animation "Frame Rate" over a 10 s sequence (orb activate, view switch, kanban drag, terminal scroll) shows no frame interval > 11.1 ms; zero dropped frames (`MXAnimationMetric`).
- **REQ-PERF-011 (MUST)** — During heavy PTY streaming (8 terminals at peak), UI frame rate not below **60 Hz** (90 Hz remains the target). *Acceptance:* Same instrumentation while the PTY stress harness runs.
- **REQ-PERF-012 (MUST)** — Zero main-thread frames from layout/drawing during any animation; animated layer trees committed before the animation begins. *Acceptance:* Time Profiler main-thread callstacks during animation intervals include no `layoutSubviews`/`updateConstraints`/`drawRect` or SwiftUI layout resolver inside an animation signpost interval.
- **REQ-PERF-013 (MUST)** — Overdraw ≤ **2.0× average** and **3.0× peak** for animated surfaces; Liquid Glass / Orb surfaces are exempt from the 2× average but must not exceed **4.0× peak**. *Acceptance:* Metal System Trace overdraw heatmap on the Orb peak frame, averaged over a 1 s clip, holds these budgets.
- **REQ-PERF-014 (MUST)** — No PTY-output-triggered layout pass blocks the main thread > **4 ms**. *Acceptance:* Over a 30 s PTY stress window, p99 main-thread block from terminal parsing/UI dispatch ≤ 4 ms.
- **REQ-PERF-015 (SHOULD)** — The fluid Orb runs entirely on GPU via Metal/Core Animation; no per-frame CPU interpolation loop for steady-state idle.

### 6.4 Launch Performance

- **REQ-PERF-016 (MUST)** — Cold launch (dock click → first interactive frame: window accepting input, tree populated, Conductor ready) ≤ **2.0 s**. *Acceptance:* App Launch template, 5 cold launches averaged; `MXAppLaunchMetric.histogrammedTimeToFirstDraw` p50 ≤ 1.5 s, p95 ≤ 2.0 s.
- **REQ-PERF-017 (MUST)** — Warm launch (re-activated from background) → first interactive frame ≤ **400 ms**. *Acceptance:* App Launch template warm scenario, p95 ≤ 400 ms.
- **REQ-PERF-018 (SHOULD)** — WhisperKit model load (first dictation per session) ≤ **3.0 s**, async, non-blocking to the main window.

### 6.5 Streaming & PTY Throughput

- **REQ-PERF-019 (MUST)** — Absorb and display **10,000 lines/sec per terminal** without stalling/freezing or blocking other surfaces. *Acceptance:* Piping ≈ 300,000 lines into one terminal in under 30 s (= 10,000 lines/sec), a click on the Kanban surface registers within **200 ms** (os_signpost in the click handler).
- **REQ-PERF-020 (MUST)** — PTY ingestion uses a **16 ms coalescing window** (one 60 Hz frame); bytes within it batch into a single UI update; never one dispatch per line. *Acceptance:* During peak throughput, main-thread UI-update dispatches from terminal output ≤ 63/sec (= 1000/16).
- **REQ-PERF-021 (MUST)** — Scrollback is **virtualized**: only visible rows plus ≤ 200 rows above/below are held as attributed strings/rendered cells; other rows exist only as raw UTF-8 ring-buffer entries. *Acceptance:* With 10,000 lines in scrollback and a 50-row viewport, attributed-string / NSTextStorage / TextKit2 allocation for that terminal ≤ **4 MB** (= 250 rows × ~16 KB).
- **REQ-PERF-022 (MUST)** — Scrollback ring buffer capped at **10,000 lines per terminal**; oldest evicted in O(1); no measurable stall (< 1 ms main-thread per eviction). *Acceptance:* Time Profiler eviction interval p99 ≤ 1 ms.
- **REQ-PERF-023 (SHOULD)** — Aggregate **50,000 lines/sec** across concurrent terminals (e.g. 8 × 6,250) absorbable without exceeding REQ-PERF-008 by more than 15 percentage points.

### 6.6 Concurrent Terminal Scalability

- **REQ-PERF-024 (MUST)** — Support **up to 16 concurrent terminals** without crash/data loss; linear-scaled memory (16 × 30 MB + 80 MB base = **560 MB max RSS**). *Acceptance:* Open 16 terminals, drive each at 200 lines/sec for 5 min: no crash, `footprint` RSS ≤ 560 MB, all sessions still producing output. *(The default safety ceiling is 8 per REQ-BE-004; 16 is the supported hard maximum.)*
- **REQ-PERF-025 (MUST)** — When concurrency would push RAM beyond a **480 MB** soft ceiling, enter **graceful degradation**: suspend scrollback ingestion for off-screen terminals, reduce their coalescing to 1 s, and show a non-blocking status indicator; no PTY output lost (the background ring buffer keeps accumulating). *Acceptance:* On a 16 GB variant (adjusted 300 MB ceiling) with 14 terminals, the indicator appears, on-screen terminals stay ≥ 60 Hz, and off-screen scrollback resumes within 500 ms of being brought into view.
- **REQ-PERF-026 (SHOULD)** — The Kanban board renders and animates up to **200 cards** without dropping below 90 Hz during a drag.
- **REQ-PERF-027 (COULD)** — The directory tree lazily loads subtrees and supports up to **100,000 files** (selective expansion); initial render for a 10,000-file root ≤ **500 ms**.

### 6.7 Thermal & Battery

- **REQ-PERF-028 (MUST)** — Idle energy impact classified **Low**, no fan spin-up (fanless MacBook Air variant: SoC ≤ 45 °C steady-state at idle). *Acceptance:* `powermetrics --samplers cpu_power -n 10` average package power ≤ **300 mW** over 10 min; Activity Monitor shows "Low".
- **REQ-PERF-029 (MUST)** — 4 active terminals at 500 lines/sec aggregate, no dictation: energy **Low or Medium**, SoC package power ≤ **2.5 W**. *Acceptance:* `powermetrics` average over 5 min ≤ 2.5 W.
- **REQ-PERF-030 (MUST)** — Backgrounded (no visible window, no dictation, no terminal output): **zero continuous CPU**; background wakeups ≤ **2/minute** steady-state. *Acceptance:* Energy Log "Background CPU" over 5 min shows ≤ 2 wakeups/minute attributable to the process. *(Excludes the orchestrator process; see Open Questions.)*
- **REQ-PERF-031 (SHOULD)** — With Low Power Mode active, automatically reduce animation target to **60 Hz**, increase the PTY coalescing window to **33 ms**, and suspend the Orb idle animation, within **1 s** of the notification. *(Complements the visual reductions of REQ-DSN-072.)*

### 6.8 Profiling & Acceptance Methodology

- **REQ-PERF-032 (MUST)** — Include `os_signpost` instrumentation at: `archon.launch`; `archon.animation.<name>` (orb-listen, orb-dismiss, view-switch, kanban-drag); `archon.pty.coalesce`; `archon.pty.evict`; `archon.whisper.load`; `archon.degradation.enter`/`.exit`. *Acceptance:* `xctrace record --template "os_signpost"` running the stress harness produces all named intervals; a CI script parses the trace via `xcrun xctrace export` and asserts each duration against its budget, failing CI on any violation.
- **REQ-PERF-033 (MUST)** — A performance regression gate runs in CI on every PR (headless UI-test scenario: idle RSS, 4-terminal RSS, cold launch, PTY coalescing rate); any regression > **10%** above the initial-release baseline blocks merge. *Acceptance:* CI includes `xcodebuild test -testPlan PerformanceGates`; `measure` blocks assert averages against hard limits; the PR check fails on any failed assertion.
- **REQ-PERF-034 (MUST)** — Embed a MetricKit subscriber reporting `MXMemoryMetric`, `MXCPUMetric`, `MXAppLaunchMetric`, `MXAnimationMetric`, `MXAppExitMetric` to a local log file (never remote without explicit opt-in). *Acceptance:* After > 24 h, a payload file exists at `~/Library/Application Support/Archon/metrics/<date>.json` containing ≥ one delivery of each metric type.
- **REQ-PERF-035 (SHOULD)** — Maintain a committed Instruments `.tracetemplate` (Time Profiler, Metal System Trace, Core Animation, Energy Log, Allocations, signpost filter pre-set) runnable via a single `make profile` against the stress harness.

---

## 7. Glossary

- **Agent session / terminal** — One PTY-backed local process running an agent CLI (Claude Code / Codex CLI) operating on the local codebase. "Terminal" is the user-facing name; "agent session" the technical name. One intent may produce several.
- **Conductor** — The single, always-present orchestrating intelligence, powered by the Claude API via the orchestrator. Interprets intent, decides session count and routing. Always singular — one primary presence per app (REQ-ARCH-043).
- **Orchestrator** — The local backend (refactored FastAPI service) that runs the Conductor, spawns/manages terminals, holds the provider key, and exposes loopback HTTP (control) + WebSocket/SSE (streaming) to the client.
- **Orb** — The floating, fluid, Siri-like animated element; the sole locus of color in the UI; reflects the six behavioral states of REQ-UX-040.
- **Memory file** — A directory-scoped, human-readable file (default under `.archon/memory/`) holding persistent guidance/conventions, read by the client and agents, arbitrated for writes.
- **Run** — One end-to-end unit of work from a user intent — Conductor plan through spawned terminal(s) to completion/acceptance. The unit of metrics and review.
- **Task (kanban card)** — A first-class persisted board entity representing a terminal-task. Both Conductor and user may create/modify/move it; moving to `In Progress`/`in_progress` can drive terminal lifecycle.
- **Board column vs task state** — The five user-facing columns (Queued, In Progress, Blocked, Review, Done; REQ-UX-050) map to the backend task state machine (`backlog`/`ready` → Queued; `in_progress`; `blocked`; `review`; `done`; plus terminal `cancelled`; REQ-BE-011).
- **Session status** — The five-state badge vocabulary (Idle, Running, Blocked, Error, Done; REQ-UX-060) used across terminal cards, kanban badges, and dashboard tiles; distinct from board columns and task states.
- **Summary dashboard** — The condensed native overview of all runs/sessions (parity with the V2 web dashboard; REQ-UX-023).
- **Individual-terminals view** — The live grid of each terminal's streaming activity.
- **Reference machine** — Apple M4 Pro, 24 GB, macOS 26.0, NVMe; canonical for all hard budgets.
- **Liquid Glass** — macOS 26 (Tahoe) translucent material system; used for floating/sidebar surfaces, kept colorimetrically neutral (REQ-DSN-021/023).

---

## 8. Decisions Log & Residual Open Items

All 32 original open items are resolved below. **Product (P)** items were decided by the product owner on 2026-07-09; **Engineering-default (E)** items are sensible defaults chosen to avoid ping-pong and are overridable before implementation. Exactly one item remains genuinely **Open (O)**, pending owner input.

### 8.1 Product decisions (owner, 2026-07-09)

- **[P] Q1 Accept semantics → automatic git commit.** Accept commits an agent's changes to the current branch with a generated message referencing the run/task; reject discards the working-tree changes. Local git only (consistent with REQ-VIS-023d). Dedicated-branch strategy is COULD. Refines REQ-VIS-014.
- **[P] Q3 Multi-project → single-project per instance.** One orchestrator instance = one project directory. Session / memory / kanban scoping is single-project; the API does not multiplex projects. Simplifies REQ-BE-004 and ARCH session/memory scoping.
- **[P] Q6 Memory format → agent-native conventions + overlay.** Primary = `CLAUDE.md` / `AGENTS.md`, in-app editable as Markdown; optional `.archon/` overlay for Archon-specific metadata. Both are read into agent context.
- **[P] Q13 Voice → push-to-talk.** A global hotkey gates dictation; WhisperKit runs only while the key is held (zero idle STT cost). Wake-word deferred (COULD, opt-in in Settings). Refines REQ-UX-030 and tightens PERF budgets.

### 8.2 Engineering defaults (overridable before implementation)

- **[E] Q2 / Q5 Supported machines & session ceiling.** Supported = Apple silicon ≥ 16 GB. Hard budgets stated for the 24 GB reference; on 16 GB the graceful ceiling is reduced. Graceful ≥ 8 concurrent terminals, hard max 16 (REQ-PERF-024).
- **[E] Q4 Conductor singularity.** Absolute for V3 — exactly one Conductor; multiple personas/profiles are out of scope (aligns Locked Decision 2).
- **[E] Q7 Memory write authority → orchestrator sole writer.** Client edits flow through the orchestrator API; no direct client file-writing (avoids write concurrency). The `.archon/` overlay is orchestrator-written too.
- **[E] Q8 Orchestrator lifecycle → client-supervised.** The client auto-launches, health-checks, and restarts the local orchestrator; it owns port + token bootstrap.
- **[E] Q9 Auth-token bootstrap → `0600` token file** at a known path, read by the client at startup.
- **[E] Q10 Stream transport → WebSocket only**, as the single primary full-duplex stream; SSE dropped.
- **[E] Q11 Interactive PTY stdin → Conductor-mediated only (MVP).** Direct typing into a live terminal is deferred (COULD); no user-stdin control requirement in V3.
- **[E] Q12 Replay buffer → 2,000 events / 60 s, in-memory** (REQ-BE-043).
- **[E] Q14 Dry-run latency → ≤ 1.5 s;** beyond that the confirmation surface shows "no estimate" rather than blocking.
- **[E] Q15 Kanban → fixed five-column model** with a one-time V2 → V3 migration.
- **[E] Q16 Hotkey → direct notarized (OSS) distribution**, non-accessibility hotkey API; no extra provisioning.
- **[E] Q17 Orb position → persisted per project directory.**
- **[E] Q18 Conductor/orb states → frozen six-state set:** idle, listening, thinking, spawning, streaming, error (drives the REQ-DSN-013 hue table).
- **[E] Q19 / Q22 / Q23 / Q24 Motion & shader locks → design-lock pass at implementation start.** Orb exempt from the 2× overdraw average; the 4 ms GPU and 16.7 ms frame budgets are provisional pending that pass; SI → SwiftUI spring conversion and bloom radius/opacity are locked then.
- **[E] Q20 Liquid Glass → audit macOS 26 GM public APIs at implementation start;** CALayer fallback if public materials are insufficient (REQ-DSN-022).
- **[E] Q21 Parallax → disabled when not standard-windowed** (Stage Manager / full-screen).
- **[E] Q25 WhisperKit tier → base (~145 MB).** Budgets assume base; shipping a larger tier requires raising REQ-PERF-001/003 and re-validating REQ-ARCH-033.
- **[E] Q26 Scrollback → in-memory only (MVP);** no disk flush.
- **[E] Q27 Headless orchestrator budget → accounted under §3.9**, not the §6 client budgets.
- **[E] Q28 CI → self-hosted M-series runner;** re-baseline performance gates on hardware change.
- **[E] Q29 Persistence → SQLite** for kanban / audit / session metadata.
- **[E] Q30 Agent CLIs → generic PTY adapter + per-CLI adapter hooks;** macOS `setrlimit` for per-session limits (REQ-BE-034).
- **[E] Q31 Conductor loop → single Claude call for routing (MVP);** multi-step agentic loop later.
- **[E] Q32 Idle timeout → flag-only (no auto-kill);** reaping by user or Conductor.

### 8.3 Residual open item — RESOLVED

- **[P] Reference machine / RAM → Apple M5 / 32 GB** (measured on the owner's machine on 2026-07-10: `machdep.cpu.brand_string` = Apple M5, `hw.memsize` = 32 GB). All REQ-PERF-* hard budgets keep the M4 Pro / 24 GB figures as the *reference floor* (the owner's M5/32 GB is strictly faster/larger, so budgets passing on reference imply headroom on the real machine — not vice versa). CI/self-hosted runner baselining (Q28) should use M4 Pro-class or note the delta. No open items remain.

## 9. Traceability Note

Requirement IDs are stable and unique within their area prefix (`VIS`, `ARCH`, `BE`, `UX`, `DSN`, `PERF`); because prefixes never collide, no renumbering was required across the merge, and numbering is sequential within each area. Cross-layer requirements that legitimately restate a Locked Decision at different tiers are retained with explicit cross-references rather than deleted, so each layer's acceptance criterion survives: **no provider key** (product REQ-VIS-002 → client REQ-ARCH-040 → server REQ-BE-060/062); **loopback-only** (REQ-ARCH-002/070 → REQ-BE-070); **client auth token** (REQ-ARCH-071/072 ↔ REQ-BE-071); **on-device STT** (REQ-VIS-021 → REQ-ARCH-030); **monochrome UI** (REQ-VIS-022 → REQ-DSN-001/011). Contradictions were resolved toward the Locked Decisions and the authoritative-owner section, with the resolution noted inline: client scrollback sizing unified to the 10,000-line virtualized buffer of §6 (REQ-ARCH-009, REQ-UX-013 reconciled to REQ-PERF-021/022); reference machine and 8-session memory budget unified to M4 Pro / 24 GB / ≤ 340 MB (REQ-VIS-032 → REQ-PERF-003); the orb hue table (REQ-DSN-013) reconciled to the six canonical behavioral states (REQ-UX-040); board columns, task states, and session-status badges disambiguated as three distinct vocabularies with an explicit mapping (Glossary; REQ-UX-050 ↔ REQ-BE-011). Server-side replay buffers, throttling, cap enforcement, plan generation, key custody, and PTY spawning are specified once under `REQ-BE-*` and referenced from `REQ-ARCH-*`; the streaming protocol has a client end (§2.A) and a server end (§3.5) that must be validated against one shared message-catalog document (REQ-BE-051). Every MUST retains its Acceptance Criterion and every quantified budget is preserved verbatim except where two figures directly conflicted, in which case the superseded value is called out at its requirement.