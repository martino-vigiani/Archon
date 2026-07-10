# Archon V3 — Client ⇄ Orchestrator API Contract (FROZEN)

**Status:** Normative · Frozen at implementation start (2026-07-10)
**Protocol version:** `pv = 1` (major `1`, minor `0`)
**Audience:** Swift client team (`client/`) and Python backend team (`orchestrator/v3/`).
This is the single source of truth both sides implement against **without coordinating**. Where it conflicts with `REQUIREMENTS_V3.md`, this contract and `BUILD_ADDENDUM_V3.md` win. Every field name is **snake_case**. Every timestamp is **RFC 3339 UTC, millisecond precision** (`2026-07-10T14:03:22.481Z`).

> Traceability: satisfies REQ-ARCH-001..012, REQ-ARCH-020..027, REQ-ARCH-040..044, REQ-ARCH-050..055, REQ-ARCH-070..075; REQ-BE-040..046, REQ-BE-050..053, REQ-BE-070..072; Addendum §A3 (zero-footprint / provenance guard), §C. Engineering defaults Q8/Q9/Q10/Q12/Q14/Q15/Q18.

---

## 0. Terminology & IDs

| Term | Meaning |
|---|---|
| Orchestrator | The local Python (FastAPI) backend. Single-project per instance (Q3). Holds the Claude key. Spawns Claude Code PTY sessions. |
| Client | The native macOS app (`client/`). Supervises the orchestrator (Q8): launches it, reads the token file, health-checks, restarts. |
| Session / terminal | One PTY-backed Claude Code process. Identified by `session_id`. |
| Card / task | One kanban entity. Identified by `card_id`. |
| Plan | A Conductor proposal produced from an intent. Identified by `plan_id`. |
| Provenance / `initiator` | Who caused a mutation: `user` or `conductor`. Project-dir writes require `user` (Addendum §A3). |

**ID formats** (all strings, opaque to the client except for ordering rules stated):
- `session_id`, `card_id`, `plan_id`, `intent_id`, `action_id`, `event_id` — **ULID** (26 chars, Crockford base32, lexicographically sortable). Servers MUST emit ULIDs; clients MUST treat them as opaque.
- `project_id` — `sha256_hex(canonical_project_path)` — lowercase 64-hex. Deterministic; both sides compute it identically from the absolute, symlink-resolved project path.
- `request_id` — client-generated ULID for idempotency (spawn, confirm, intent).

---

## 1. Transport, Discovery, Auth, Versioning

### 1.1 Base URL & binding
- REST control plane: `http://127.0.0.1:<port>/v3/...` — HTTP/1.1, loopback only (`127.0.0.1`, never `::1`-only reliance; bind `127.0.0.1`).
- Stream plane: **exactly one** WebSocket `ws://127.0.0.1:<port>/v3/stream` (WS-only per Q10; **no SSE, no polling fallback**).
- The orchestrator MUST refuse to bind any non-loopback interface by default (REQ-BE-070).

### 1.2 Discovery & token file (Q8/Q9, Addendum §A3)
The orchestrator is client-supervised. All runtime state lives **outside the project directory** under:

```
$SUPPORT = ~/Library/Application Support/Archon
$PROJECT_STATE = $SUPPORT/projects/<project_id>/
```

At startup the orchestrator **atomically** writes a handshake file (write-temp-then-rename), mode **`0600`**, owner-only:

```
$PROJECT_STATE/runtime.json          # 0600
```

```json
{
  "pv": 1,
  "port": 51423,
  "pid": 88412,
  "token": "b6f1c0d9e2a74f... (64 hex chars, 256-bit)",
  "project_id": "9f2c...",
  "project_path": "/Users/mara/subralabs-v2",
  "started_at": "2026-07-10T14:03:22.481Z"
}
```

- The client polls for this file after spawning the orchestrator (or is told the path directly), reads `port` + `token`, and connects.
- `token` = `secrets.token_hex(32)`. The orchestrator MUST refuse to start if it cannot create the file `0600`, and MUST refuse to read a `token`-bearing file that is group/world-readable.
- On clean shutdown the orchestrator deletes `runtime.json`. A stale file (pid dead) MUST be ignored by the client.
- **Nothing is ever written inside the project directory** by the app/orchestrator except via an explicit `initiator: user` action or agent PTY work (Addendum §A3).

### 1.3 Authentication (every request, both planes)
Bearer token from the `0600` file above.

- **REST:** `Authorization: Bearer <token>` header on **every** `/v3` request (including `GET /v3/health`).
- **WebSocket:** `ws://127.0.0.1:<port>/v3/stream?token=<token>`. The client SHOULD also send `Authorization: Bearer <token>` when its WS stack allows headers; the server accepts either but **requires at least one**.
- Comparison is constant-time. Missing/invalid token → `401 unauthorized` (REST) or WS close code **`1008`** (policy violation) before the socket is usable.
- **Origin guard (REQ-BE-072):** the WS upgrade `Origin`, if present, must have a loopback host (`127.0.0.1`/`localhost`/`::1`); otherwise close `1008`. Header-less non-browser clients are allowed through the origin check but still need the token.

### 1.4 Versioning & negotiation (REQ-ARCH-004, REQ-BE-052)
- `pv` is the protocol **major** version; `1`. Minor changes are **additive-only** (new optional fields, new event `type`s).
- The client sends `Archon-Protocol-Version: 1` on the WS handshake query as `&pv=1` and on REST as header `Archon-Protocol-Version: 1`.
- **Major mismatch** (client `pv` ≠ server major): REST → `409 incompatible_version`; WS → server sends one `error` frame `code=incompatible_version` then closes `1008`. No best-effort parsing.
- **Unknown `type` / unknown fields:** receivers ignore them without disconnecting (REQ-ARCH-006, REQ-BE-045). Both sides MUST tolerate additive fields.
- Capabilities are advertised in `GET /v3/health.capabilities` and the WS `hello` frame.

### 1.5 Idempotency (REQ-ARCH-021)
Mutating POSTs that create sessions/plans accept a `request_id` (body field; also honored as `Idempotency-Key` header). Re-sending the same `request_id` returns the **same** authoritative resource (same `session_id`/`plan_id`), never a duplicate. Idempotency records are retained ≥ 10 min.

### 1.6 Error envelope (REQ-BE-053)
Every non-2xx REST response and every WS `error` payload uses:

```json
{
  "error": {
    "code": "revision_conflict",
    "message": "Card revision 7 is stale; current is 9.",
    "retriable": false,
    "details": { "card_id": "01J...", "expected_revision": 9 }
  }
}
```

**Code registry** (stable; `code` ↔ HTTP status):

| `code` | HTTP | retriable | Meaning |
|---|---|---|---|
| `unauthorized` | 401 | false | Missing/invalid bearer token |
| `forbidden` | 403 | false | Authenticated but not allowed |
| `incompatible_version` | 409 | false | Protocol major mismatch |
| `not_found` | 404 | false | Unknown resource |
| `validation_error` | 422 | false | Malformed request body/params |
| `revision_conflict` | 409 | false | Optimistic-concurrency stale write |
| `cap_exceeded` | 409 | false | Would exceed the user/session cap |
| `ceiling_reached` | 409 | false | Would exceed the hard ceiling (default 8) |
| `illegal_transition` | 409 | false | Disallowed kanban state move |
| `memory_write_denied` | 403 | false | Owner/access-class rejects the write |
| `conductor_write_forbidden` | 403 | false | Non-`user` provenance on a project write (§A3) |
| `memory_too_large` | 413 | false | File exceeds per-file limit |
| `memory_quota_exceeded` | 409 | false | Scope file/byte quota exceeded |
| `path_escape` | 400 | false | Path resolves outside the declared scope |
| `plan_expired` | 410 | false | Plan TTL elapsed before confirm |
| `plan_already_confirmed` | 409 | false | Plan already executed; re-confirm refused (retry with the same `request_id` replays the original result) |
| `session_not_found` | 404 | false | Unknown `session_id` |
| `rate_limited` | 429 | true | Too many requests |
| `orchestrator_error` | 500 | true | Internal failure |
| `provider_error` | 502 | true | Upstream Claude API error |

---

## 2. REST Endpoints (control plane, all under `/v3`)

All require `Authorization: Bearer <token>`. All bodies/responses `application/json; charset=utf-8`.

### 2.1 Health & capabilities — `GET /v3/health`
No side effects. Used for supervision/health-checks.

**200**
```json
{
  "status": "ok",
  "pv": 1,
  "orchestrator_version": "3.0.0",
  "project_id": "9f2c...",
  "uptime_s": 412.8,
  "provider_ready": true,
  "conductor_state": "idle",
  "session_count": 2,
  "capabilities": {
    "stream_transport": "websocket",
    "replay_events": 2000,
    "replay_window_s": 60,
    "hard_ceiling": 8,
    "supported_provider": "claude_code",
    "memory_kinds": ["CLAUDE.md", "AGENTS.md", "overlay"],
    "dry_run_max_s": 1.5
  }
}
```
`status` ∈ `ok | degraded | starting`. On major mismatch, `GET /v3/health` still answers 200 (so the client can read `pv`); mutating calls return `incompatible_version`.

### 2.2 Project info — `GET /v3/project`
Single-project instance (Q3). No mutation endpoint exists for project selection — the project is fixed for the instance lifetime.

**200**
```json
{
  "project_id": "9f2c...",
  "path": "/Users/mara/subralabs-v2",
  "name": "subralabs-v2",
  "provider": "claude_code",
  "opened_at": "2026-07-10T14:03:20.001Z",
  "git": { "is_repo": true, "branch": "main", "head": "a1b2c3d", "dirty": false },
  "state_dir": "~/Library/Application Support/Archon/projects/9f2c.../"
}
```

### 2.3 Sessions (Claude Code PTY lifecycle)

Session object (canonical shape, returned by list/detail and in events):
```json
{
  "session_id": "01J8Z...",
  "state": "running",
  "status": "running",
  "provider": "claude_code",
  "cwd": "/Users/mara/subralabs-v2/packages/api",
  "card_id": "01J8Y...",
  "initiator": "conductor",
  "request_id": "01J8X...",
  "pid": 90233,
  "created_at": "2026-07-10T14:03:25.100Z",
  "started_at": "2026-07-10T14:03:25.412Z",
  "ended_at": null,
  "exit_code": null,
  "exit_reason": null,
  "idle_flagged": false,
  "last_activity_at": "2026-07-10T14:05:02.900Z",
  "last_output_seq": 4821,
  "elapsed_s": 97.4
}
```
- **`state`** (lifecycle, REQ-ARCH-020): `requested | spawning | running | completed | failed | killed` (transient `reconnecting` is client-only, never emitted). The client MUST NOT infer `completed` from output.
- **`status`** (five-state badge vocabulary, REQ-UX-060): `idle | running | blocked | error | done`.
- `exit_reason` when set ∈ `normal | killed | crash_recovery | resource_exceeded | spawn_failed`.

#### `GET /v3/sessions` — list (authoritative snapshot, REQ-ARCH-026)
**200** `{ "sessions": [ <session>, ... ], "count": 2, "ceiling": 8, "cap": { "regime": "auto", "value": null } }`
`regime` ∈ `auto | user`; `value` is the user cap when `regime=user`.

#### `POST /v3/sessions` — spawn
Body:
```json
{
  "request_id": "01J8X...",
  "cwd": "/Users/mara/subralabs-v2/packages/api",
  "card_id": "01J8Y...",
  "initiator": "user",
  "prompt": "Run the test suite and fix failures",
  "cap": 4
}
```
- `cwd` MUST resolve inside the project directory (else `path_escape`/400).
- `initiator` ∈ `user | conductor`. `prompt`, `card_id`, `cap` optional.

**201** → `{ "session": <session> }` (state `spawning` or `running`).
**202** `spawn_deferred` (admission control, REQ-BE-005): `{ "deferred": true, "reason": "insufficient_ram", "queued_request_id": "01J8X..." }` — a `session_spawned` (or `error`) event follows when it drains.
**409** `cap_exceeded` | `ceiling_reached`. Re-sent `request_id` → the original `201` result.

#### `GET /v3/sessions/{session_id}` — detail
**200** `{ "session": <session>, "recent_output_seq_range": { "first": 4200, "last": 4821 } }`
**404** `session_not_found`.

#### `POST /v3/sessions/{session_id}/kill` — terminate
Body (optional): `{ "grace_ms": 5000, "force": true }`. Idempotent (REQ-ARCH-023). Graceful SIGTERM then SIGKILL after grace (default 5000 ms).
**202** `{ "session_id": "...", "state": "killed", "accepted": true }` — resolves to `killed` (or `completed` if it already finished) via a `session_state` event. No further `pty_output` for that session renders after the terminal event.
**404** `session_not_found`.

#### `POST /v3/sessions/{session_id}/flag-idle` — flag (no auto-kill, Q32)
Marks an idle session for user/Conductor attention; never kills.
Body (optional): `{ "flagged": true }` (default true; `false` clears).
**200** `{ "session_id": "...", "idle_flagged": true }`.

> **Interactive stdin is deferred (Q11).** There is intentionally **no** `POST /v3/sessions/{id}/input` in `pv=1`. Reserved for a later minor version behind a capability flag.

### 2.4 Conductor (intent → plan → confirm/execute)

#### `POST /v3/conductor/message` — submit intent, get plan + dry-run estimate
Body:
```json
{
  "request_id": "01J8W...",
  "text": "Split the checkout refactor across two terminals and add tests",
  "source": "voice_transcript",
  "context": {
    "active_dir": "/Users/mara/subralabs-v2/packages/checkout",
    "selected_card_id": null,
    "cap": 4
  }
}
```
`source` ∈ `text | voice_transcript` (only finalized text ever leaves the client — REQ-ARCH-032). Planning streams as `conductor_state` events; this call returns once the plan is assembled (single Claude routing call, Q31).

**200**
```json
{
  "intent_id": "01J8W...",
  "plan": {
    "plan_id": "01J8V...",
    "summary": "Two terminals: one refactors checkout, one writes tests.",
    "proposed_session_count": 2,
    "applied_cap": 4,
    "ceiling": 8,
    "final_count": 2,
    "reduction_reason": null,
    "actions": [
      {
        "action_id": "01J8V1",
        "kind": "spawn_session",
        "cwd": "/Users/mara/subralabs-v2/packages/checkout",
        "prompt": "Refactor checkout flow...",
        "card_ref": "new:refactor-checkout",
        "rationale": "Primary refactor work",
        "destructive": false
      },
      {
        "action_id": "01J8V2",
        "kind": "create_card",
        "column": "in_progress",
        "title": "Refactor checkout flow",
        "destructive": false
      }
    ]
  },
  "dry_run": {
    "estimate_ready": true,
    "estimated_session_count": 2,
    "estimated_tokens": 48000,
    "estimated_duration_s": 320,
    "warnings": ["Estimate exceeds cap? no"]
  },
  "expires_at": "2026-07-10T14:08:25.000Z"
}
```
- `actions[].kind` ∈ `spawn_session | create_card | update_card | move_card | delete_card | kill_session | propose_memory_edit`. `destructive: true` for kill/delete (REQ-ARCH-042).
- `card_ref`: either an existing `card_id` or `new:<slug>` (bound to the card the sibling `create_card` action produces).
- **Dry-run (Q14):** if the estimate cannot be produced within `dry_run_max_s` (1.5 s), the call still returns with `dry_run.estimate_ready = false` and null figures (surface as "no estimate"); a later `dry_run_result` WS event MAY deliver it. Never blocks past 1.5 s.
- Nothing is spawned/mutated yet (confirm regime). In `auto_apply` mode the client immediately calls confirm.

#### `POST /v3/conductor/plans/{plan_id}/confirm` — execute the plan
Body (optional overrides): `{ "request_id": "01J8U...", "cap": 2, "auto_apply": false }`.
**200**
```json
{
  "plan_id": "01J8V...",
  "status": "executing",
  "created_session_ids": ["01J8Z..."],
  "created_card_ids": ["01J8Y..."],
  "applied_cap": 2,
  "final_count": 2
}
```
Applied actions then surface as `session_spawned` / `kanban_updated` events. **410** `plan_expired` if past `expires_at`. Partial application reports per-action results in `status: "partial"` with an `action_results` array `[{action_id, ok, error?}]` (REQ-ARCH-085). **Idempotent (§1.4):** re-sending the same `request_id` replays the original confirm result and never re-executes; a plan executes at most once, so a re-confirm with a *different* `request_id` after execution returns **409** `plan_already_confirmed`.

#### `POST /v3/conductor/plans/{plan_id}/cancel` — discard an unconfirmed/executing plan
**200** `{ "plan_id": "...", "status": "cancelled" }`. Cancels planning (REQ-UX-043) without killing already-running sessions unless the action was `destructive` and not yet applied.

### 2.5 Kanban (5 fixed columns, Q15)

**Columns are fixed, ordered, non-renameable:** `queued, in_progress, blocked, review, done` (REQ-UX-050). Backend task states map: `backlog`/`ready`→`queued`, `in_progress`, `blocked`, `review`, `done`, terminal `cancelled`→removed.

Card object:
```json
{
  "card_id": "01J8Y...",
  "title": "Refactor checkout flow",
  "body": "Extract the payment adapter...",
  "column": "in_progress",
  "ordinal": 0,
  "priority": "high",
  "provenance": "conductor",
  "session_id": "01J8Z...",
  "status": "running",
  "revision": 3,
  "created_at": "2026-07-10T14:03:25.400Z",
  "updated_at": "2026-07-10T14:05:10.220Z"
}
```
- `priority` ∈ `low | normal | high`. `provenance` ∈ `user | conductor`. `status` = five-state badge (§2.3). `revision` = monotonic int for optimistic concurrency (REQ-BE-015). `ordinal` = 0-based position within its column.

#### `GET /v3/kanban` — snapshot
**200**
```json
{
  "columns": ["queued", "in_progress", "blocked", "review", "done"],
  "cards": [ <card>, ... ],
  "board_revision": 57
}
```

#### `POST /v3/kanban/cards` — create
Body: `{ "request_id": "01J...", "title": "…", "body": "…", "column": "queued", "priority": "normal", "provenance": "user" }`
**201** `{ "card": <card> }`. `provenance` ∈ `user | conductor` (both go through one validated path — REQ-BE-013). New card appended to the target column (highest `ordinal`).

#### `GET /v3/kanban/cards/{card_id}` — read
**200** `{ "card": <card> }` · **404** `not_found`.

#### `PATCH /v3/kanban/cards/{card_id}` — edit fields
Body: `{ "base_revision": 3, "title": "…", "body": "…", "priority": "high", "provenance": "user" }` (any subset of mutable fields).
**200** `{ "card": <card> }` (revision incremented) · **409** `revision_conflict` (stale `base_revision`).

#### `POST /v3/kanban/cards/{card_id}/move` — move column and/or reorder
Body: `{ "base_revision": 3, "to_column": "review", "to_ordinal": 1, "provenance": "user" }`
- Column change → validated against the state machine (`illegal_transition`/409 for disallowed moves, e.g. `done`→`in_progress`).
- **Reorder within the same column** = move with `to_column` equal to current column and a new `to_ordinal`. Server re-packs sibling ordinals contiguously.
- Moving to `in_progress` is the canonical spawn/bind trigger (REQ-BE-014); moving to `done`/removal releases the bound session.
**200** `{ "card": <card>, "board_revision": 58 }` · **409** `revision_conflict` | `illegal_transition`.

#### `DELETE /v3/kanban/cards/{card_id}` — delete
Query/body: `?base_revision=3` (or body `{ "base_revision": 3, "provenance": "user" }`).
**200** `{ "card_id": "...", "deleted": true }` · **409** `revision_conflict`.

### 2.6 Memory files (CLAUDE.md / AGENTS.md discovered per-directory + overlay)

**Provenance rule (Addendum §A3, hard):** project-directory writes require `initiator: "user"`. Any write with `initiator != "user"` (i.e. conductor-originated) is rejected **`403 conductor_write_forbidden`** and audited. The Conductor may only *propose* an edit (as a `propose_memory_edit` plan action); it never writes.

Memory file object:
```json
{
  "scope_dir": "/Users/mara/subralabs-v2/packages/api",
  "filename": "CLAUDE.md",
  "kind": "CLAUDE.md",
  "location": "project",
  "size": 2048,
  "mtime": "2026-07-09T18:11:02.000Z",
  "owner": "user",
  "revision": 4,
  "checksum": "sha256:1a2b...",
  "editable": true
}
```
- `kind` ∈ `CLAUDE.md | AGENTS.md | overlay`. `location` ∈ `project | overlay`.
- `project` files are the agent-native `CLAUDE.md`/`AGENTS.md` discovered per-directory (Q6), stored **in the project tree** — mutated only by explicit user save (§A3 exception b).
- `overlay` files hold Archon-specific metadata and live **outside** the project under `$PROJECT_STATE/memory-overlay/<rel_dir>/` (never `.archon/` in the project — §A3).

#### `GET /v3/memory` — list discovered files across the project
Optional `?scope_dir=<abs>` to scope to one directory (must be inside project).
**200**
```json
{
  "scopes": [
    {
      "scope_dir": "/Users/mara/subralabs-v2",
      "files": [ <memory_file>, ... ]
    }
  ]
}
```

#### `GET /v3/memory/file` — read one file
Query: `?scope_dir=<abs>&filename=CLAUDE.md`
**200** `{ "file": <memory_file>, "content": "# Project guidance\n..." }`
**400** `path_escape` (scope/filename escapes project) · **404** `not_found`.

#### `PUT /v3/memory/file` — write (user-initiated only)
Body:
```json
{
  "scope_dir": "/Users/mara/subralabs-v2/packages/api",
  "filename": "CLAUDE.md",
  "content": "# Updated guidance\n...",
  "base_revision": 4,
  "base_checksum": "sha256:1a2b...",
  "initiator": "user"
}
```
- Atomic write-temp-then-rename with optimistic-concurrency guard (REQ-BE-023, REQ-ARCH-053): stale `base_revision`/`base_checksum` → **409** `revision_conflict`.
- `initiator != "user"` → **403** `conductor_write_forbidden`. Owner/access-class denial → **403** `memory_write_denied`.
- `> 1 MB` → **413** `memory_too_large`. Scope quota (32 MB / 512 files) → **409** `memory_quota_exceeded`. Path escape / symlink escape → **400** `path_escape` (no filesystem write).
**200** `{ "file": <memory_file> }` (revision incremented, new checksum).

#### `DELETE /v3/memory/file` — delete (user-initiated only)
Query/body: `?scope_dir=<abs>&filename=NOTES.md` + `{ "base_revision": 4, "initiator": "user" }`.
Same provenance/escape rules. **200** `{ "deleted": true }`.

### 2.7 Event replay cursor — `GET /v3/events`
REST convenience for replay outside a live socket (mirrors the WS `resume`; REQ-BE-043). Buffer window = 2000 events / 60 s.
Query: `?after_seq=4820&limit=500`
**200**
```json
{
  "events": [ <envelope>, ... ],
  "from_seq": 4821,
  "next_seq": 4999,
  "truncated": false
}
```
`truncated: true` when `after_seq` predates the buffer — the client MUST then re-fetch full snapshots via `GET /v3/sessions` + `GET /v3/kanban` and resume the socket from the newest `seq` (REQ-ARCH-008).

---

## 3. WebSocket Stream Protocol (`/v3/stream`)

Single full-duplex socket (Q10). Server→client is a **globally-ordered event stream**; client→server carries small control frames (subscribe/resume/ping).

### 3.1 Envelope (every server→client frame)
```json
{
  "v": 1,
  "seq": 4821,
  "ts": "2026-07-10T14:05:02.900Z",
  "type": "pty_output",
  "session_id": "01J8Z...",
  "payload": { "...": "..." }
}
```
- **Required:** `seq`, `ts`, `type`, `payload`. `v` (protocol major) is always present. `session_id` present only on session-scoped events; `task_id`/`plan_id` present on board/plan-scoped events.
- **`seq`** is a **single, connection-independent, monotonic, gap-free** counter across ALL events on this orchestrator instance (REQ-BE-042). It is the **replay cursor**: the client tracks the highest `seq` seen and resumes from it. A gap in `seq` → the client issues `resume` (REQ-ARCH-005).
- `pty_output` additionally carries a **per-session** `stream_seq` inside `payload` for byte-ordering/gap detection of that one session (REQ-ARCH-005), independent of the global `seq`.
- Unknown `type` → ignore, do not disconnect.

### 3.2 Handshake
On connect (after auth) the server sends **exactly one** `hello`, then the live stream. Full state snapshots are fetched via REST (`GET /v3/sessions`, `GET /v3/kanban`) — the socket carries deltas.

```json
{ "v": 1, "seq": 4820, "ts": "...", "type": "hello",
  "payload": {
    "pv": 1,
    "orchestrator_version": "3.0.0",
    "current_seq": 4820,
    "replay_window_events": 2000,
    "replay_window_s": 60,
    "resume_supported": true,
    "conductor_state": "streaming"
  } }
```

### 3.3 Client → server control frames
```json
{ "type": "resume", "after_seq": 4700 }
{ "type": "subscribe",   "topics": ["session", "kanban", "conductor"] }
{ "type": "unsubscribe", "topics": ["memory"] }
{ "type": "ping", "id": "c-01" }
```
- **`resume`**: replays buffered events with `seq > after_seq` in order, then live. If `after_seq` predates the buffer, the server replies with a fresh `hello` carrying `"truncated": true`; the client then does a full REST snapshot resync.
- **`subscribe`/`unsubscribe`** (REQ-BE-045): topics = `session | pty_output | kanban | conductor | memory | policy`. Default (no subscribe frame) = all topics. Off-screen sessions SHOULD unsubscribe/`pty_output` or the server reduces their rate (REQ-ARCH-012).
- **`ping`** → server `pong` (see below). Reconnect is client-driven with exponential backoff (≤500 ms start, ≤15 s cap; REQ-ARCH-007) and MUST NOT spawn/kill/duplicate anything.

### 3.4 Event type catalog (server → client)

| `type` | Scope key | Purpose |
|---|---|---|
| `hello` | — | One-time handshake / resume-truncation notice |
| `heartbeat` | — | Liveness (≤ 15 s), also carries `current_seq` |
| `session_spawned` | `session_id` | A new session was created (user/conductor/deferred-drain) |
| `session_state` | `session_id` | Lifecycle + status transition |
| `pty_output` | `session_id` | Chunked, base64 terminal bytes |
| `kanban_updated` | `task_id`* | Card/column delta (created/updated/moved/deleted/snapshot) |
| `conductor_state` | — | One of the six orb states + optional thinking text |
| `memory_changed` | — | A memory file changed (API or out-of-band) |
| `dry_run_result` | `plan_id`* | Async dry-run estimate for a pending plan |
| `error` | optional | Typed error not tied to a REST response |

\* carried inside `payload` (and mirrored at envelope top-level where present).

#### `heartbeat` (REQ-ARCH-011, REQ-BE-046)
```json
{ "v":1, "seq":4990, "ts":"...", "type":"heartbeat",
  "payload": { "current_seq": 4990 } }
```
Two consecutive missed heartbeats (~30 s) → client marks stale and reconnects. Server also answers a client `ping` with:
```json
{ "v":1, "seq":4991, "ts":"...", "type":"heartbeat", "payload": { "pong": "c-01", "current_seq": 4991 } }
```

#### `session_spawned`
```json
{ "v":1, "seq":4822, "ts":"...", "type":"session_spawned", "session_id":"01J8Z...",
  "payload": { "session": { /* full session object, §2.3 */ } } }
```

#### `session_state`
```json
{ "v":1, "seq":4901, "ts":"...", "type":"session_state", "session_id":"01J8Z...",
  "payload": {
    "state": "completed",
    "status": "done",
    "exit_code": 0,
    "exit_reason": "normal",
    "idle_flagged": false,
    "last_activity_at": "2026-07-10T14:07:41.100Z",
    "elapsed_s": 421.0
  } }
```
Also used for `session.resource_exceeded` (REQ-BE-034) by emitting `state:"failed", exit_reason:"resource_exceeded", "limit":"rss"` in payload.

#### `pty_output` (chunked + base64, REQ-ARCH-005/009/010)
```json
{ "v":1, "seq":4830, "ts":"...", "type":"pty_output", "session_id":"01J8Z...",
  "payload": {
    "stream_seq": 512,
    "encoding": "base64",
    "bytes": "G1swbUhlbGxvIHdvcmxkG1tt...",
    "dropped": false,
    "dropped_bytes": 0
  } }
```
- `bytes` = base64 of **raw PTY bytes** (ANSI/UTF-8 preserved; client owns terminal parsing).
- `stream_seq` is per-session, monotonic, gap-free. A gap → client `resume`.
- **Server-side coalescing/backpressure (REQ-BE-044, REQ-ARCH-009):** the server batches bytes into chunks (target ≤ 16 ms / ≤ 32 KiB per chunk), bounds each connection's queue, and when a consumer is slow **coalesces** then **drops-with-marker** on the `pty_output` topic: it emits a chunk with `"dropped": true, "dropped_bytes": N` and resets `stream_seq` continuity via the marker (client shows an "output truncated" break). Kanban/conductor/memory topics are **never** dropped — a hopelessly slow consumer on those is disconnected with an `error` (`code=rate_limited`), forcing a clean resync.
- Client rendering: coalesce to ≤ 1 UI update per session per frame (REQ-ARCH-010); render in `stream_seq` order only.

#### `kanban_updated`
```json
{ "v":1, "seq":4850, "ts":"...", "type":"kanban_updated", "task_id":"01J8Y...",
  "payload": {
    "op": "moved",
    "card": { /* full card object, §2.5 */ },
    "from": { "column": "queued", "ordinal": 2 },
    "to":   { "column": "in_progress", "ordinal": 0 },
    "board_revision": 58
  } }
```
- `op` ∈ `snapshot | created | updated | moved | deleted`.
- `snapshot` payload: `{ "op":"snapshot", "cards":[...], "board_revision":57 }` (sent on request/resync; steady state is deltas). One move → exactly one event (REQ-BE-016); the board is reconstructable from the event stream alone.
- `deleted` payload omits `card`, carries `{ "op":"deleted", "card_id":"...", "board_revision":59 }`.

#### `conductor_state` (six orb states, REQ-UX-040 / Q18)
```json
{ "v":1, "seq":4823, "ts":"...", "type":"conductor_state",
  "payload": {
    "state": "thinking",
    "detail": "Planning: 2 terminals for checkout refactor",
    "plan_id": "01J8V...",
    "intent_id": "01J8W..."
  } }
```
- `state` ∈ `idle | listening | thinking | spawning | streaming | error`.
- The server owns/emits `idle | thinking | spawning | streaming | error`. **`listening` is client-local** (WhisperKit push-to-talk); the client sets the orb to `listening` and never expects the server to drive it. The server MUST accept but ignore a client `listening` (it is not a control frame). `detail` is optional human-readable "thinking" text for the Conductor surface.

#### `memory_changed` (REQ-BE-026)
```json
{ "v":1, "seq":4870, "ts":"...", "type":"memory_changed",
  "payload": {
    "scope_dir": "/Users/mara/subralabs-v2/packages/api",
    "filename": "CLAUDE.md",
    "kind": "CLAUDE.md",
    "op": "updated",
    "revision": 5,
    "checksum": "sha256:9c8d...",
    "initiator": "user"
  } }
```
`op` ∈ `created | updated | deleted`. Emitted for both API writes and detected out-of-band edits (agent/git/manual) so the client refreshes without polling (REQ-ARCH-054).

#### `dry_run_result` (async estimate, Q14)
Emitted only when the synchronous `POST /v3/conductor/message` returned `estimate_ready: false`.
```json
{ "v":1, "seq":4824, "ts":"...", "type":"dry_run_result", "plan_id":"01J8V...",
  "payload": {
    "estimate_ready": true,
    "estimated_session_count": 2,
    "estimated_tokens": 48000,
    "estimated_duration_s": 320,
    "warnings": []
  } }
```

#### `error`
```json
{ "v":1, "seq":4999, "ts":"...", "type":"error", "session_id":"01J8Z...",
  "payload": { "error": {
    "code": "provider_error",
    "message": "Claude API returned 529 (overloaded); retrying with backoff.",
    "retriable": true,
    "details": { "attempt": 1 }
  } } }
```
Recoverable errors surface inline (Error column + Conductor log); the Conductor enters orb `error` and recovers (Addendum §A4). Running terminals are unaffected by Conductor/provider errors.

### 3.5 Backpressure & coalescing summary (normative)
| Topic | Slow-consumer policy |
|---|---|
| `pty_output` | Coalesce → **drop-with-marker** (`dropped:true`, `dropped_bytes`); bounded queue; server RSS bounded |
| `kanban`, `conductor`, `memory`, `policy` | **Never drop.** On unrecoverable lag, `error(code=rate_limited)` + disconnect → client resync |
- Per-connection queues are bounded; no unbounded server growth (REQ-BE-044). Aggregate client stream buffer ≤ 64 MiB (REQ-ARCH-009). Replay buffer = 2000 events / 60 s in memory (Q12).

---

## 4. Versioning & Change Policy
- `pv=1`. Additive changes (new optional fields, new event `type`s, new `capabilities` keys) ship as **minor** and MUST NOT break either side; receivers ignore unknowns.
- Breaking changes (renamed/removed fields, changed enum semantics) require a **major** bump; the server then rejects `pv=1` clients with `incompatible_version`.
- Both teams treat the JSON shapes in §2–§3 as the frozen contract. Any change is a PR to this file first, agreed before code.

---

## Appendix A — End-to-end example (voice → plan → spawn → stream)
1. Client (push-to-talk) transcribes locally, sets orb `listening`.
2. `POST /v3/conductor/message` `{source:"voice_transcript", text:"…", context:{cap:4}}` → `200` plan (`plan_id`, 2 actions, dry-run estimate). Orb `thinking` (from `conductor_state`).
3. User confirms → `POST /v3/conductor/plans/{plan_id}/confirm` `{cap:2}` → `200 executing`.
4. WS: `conductor_state:spawning` → `session_spawned` ×2 → `kanban_updated:created` ×2 → `conductor_state:streaming`.
5. WS: `pty_output` chunks (base64, per-session `stream_seq`), coalesced ≤ 1/frame/session.
6. On finish: `session_state:completed/done`, `kanban_updated:moved`→`review`, orb `idle`.
7. Disconnect mid-run → client reconnects, sends `resume{after_seq}`; if truncated, re-fetches `GET /v3/sessions` + `GET /v3/kanban` and resumes from newest `seq`. No terminals killed or duplicated.
