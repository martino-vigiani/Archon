# Zerobot / Nanobot / Clawdbot / OpenClaw Assessment

## Scope
Assessment of potential implementation in Archon: feasibility, architecture options, major risks, phased rollout, and recommended sequence.

## Feasibility Snapshot
| Candidate | Feasibility | Why |
|---|---|---|
| Zerobot | High | Fits existing orchestrator control points and policy checks. |
| Nanobot | Medium-High | Can run as focused micro-task workers with bounded scope. |
| Clawdbot | Medium | Valuable for code intelligence, but requires indexing and access controls. |
| OpenClaw | Medium-Low | Most flexible but highest governance and compatibility burden. |

## Working Assumptions
- `Zerobot`: policy/guardrail bot for validation, routing, and unsafe-action prevention.
- `Nanobot`: short-lived, narrow-scope execution bot (single objective, tight timeout).
- `Clawdbot`: repository intelligence bot (search, context assembly, dependency mapping).
- `OpenClaw`: external plugin/protocol interface for third-party bot ecosystems.

## Architecture Options
### Option A: In-Process Bot Modules (recommended start)
- Implement each bot as a strategy module wired into:
  - `orchestrator/orchestrator.py`
  - `orchestrator/planner.py`
  - `orchestrator/validator.py`
  - `orchestrator/task_queue.py`
  - `orchestrator/message_bus.py`
- Pros: fastest delivery, low ops overhead, simple observability.
- Cons: tighter coupling, harder independent scaling.

### Option B: Sidecar Workers via Message Bus
- Keep orchestrator core thin; run bots as separate worker processes exchanging typed events.
- Pros: better isolation and independent scaling.
- Cons: higher operational complexity and retry/idempotency overhead.

### Option C: External Bot Gateway (OpenClaw-first)
- Expose a stable integration boundary for external bot providers.
- Pros: extensibility and ecosystem reach.
- Cons: trust, authN/authZ, versioning, and supply-chain risk become first-order problems.

## Key Risks and Controls
| Risk | Impact | Mitigation |
|---|---|---|
| Prompt/data injection through bot context | High | Strict context sanitization, allowlisted tools, immutable policy layer (Zerobot). |
| Runaway autonomy (loops, cost spikes) | High | Timebox caps, step budgets, hard stop conditions, per-bot quotas. |
| Conflicting edits across bots | Medium-High | File ownership locks, contract-first handoffs, merge arbitration by core orchestrator. |
| Weak traceability | Medium | Structured event logs and bot decision records by task ID. |
| OpenClaw supply-chain/security risk | High | Signed plugins, sandboxing, permission manifests, staged trust levels. |

## Phased Rollout
1. **Phase 0: Interface Spec (1 week)**
- Define bot contract schema, lifecycle hooks, and telemetry model.

2. **Phase 1: Zerobot MVP (1-2 weeks)**
- Add policy checks and execution gating in orchestrator flow.
- Run in shadow mode first (observe decisions without blocking).

3. **Phase 2: Nanobot Pilot (1-2 weeks)**
- Introduce 1-2 narrow task classes (for example: small refactor, test-fix pass).
- Enforce strict scope, timeout, and rollback behavior.

4. **Phase 3: Clawdbot Discovery (2-3 weeks)**
- Build repository indexing + context retrieval with permission-aware filtering.
- Start read-only; no direct write actions.

5. **Phase 4: OpenClaw Controlled Beta (2-4 weeks)**
- Only after security gates are proven.
- Launch with signed integrations and constrained capability profiles.

## Recommendation
- Start with **Option A** and deliver **Zerobot + Nanobot first**.
- Introduce **Clawdbot** after telemetry and policy controls are stable.
- Treat **OpenClaw** as a later-stage extensibility layer, not an MVP dependency.

## Go / No-Go Criteria
Go only if all are true:
- Policy violations are blocked deterministically in staging.
- Bot actions are fully traceable by task and file.
- Autonomy guardrails cap cost/time and prevent infinite loops.
- Conflict resolution path is proven with multi-bot concurrent edits.

No-Go triggers:
- Non-deterministic policy enforcement.
- Unbounded retries or uncontrolled execution time.
- External plugin execution without signed trust and sandbox controls.

