# Codex Specialist Team (v1)

## Purpose
Define a practical Codex specialist structure for focused delivery, clean handoffs, and high autonomy with low manager overhead.

## Team Profiles
All roles use `ChatGPT Codex 5.3`.

| Role | Reasoning | Primary Responsibilities | Typical Deliverables |
|---|---|---|---|
| Python Specialist | `xhigh` | Backend implementation, integrations, data/model logic, performance-sensitive refactors | Service modules, API handlers, migration notes, profiling outcomes |
| UI Specialist | `high` | Frontend/UI flows, accessibility, interaction polish, component-level architecture | UI components, style updates, UX decision notes |
| Core Coding Specialist | `xhigh` | Cross-cutting architecture, complex features, integration glue, hard debugging | Feature implementations, system refactors, interface contracts |
| Docs Specialist | `high` | User/developer documentation, runbooks, ADRs, release notes | README/docs updates, operational guides, decision records |
| Ideas/Research Specialist | `xhigh` | Option discovery, technical tradeoffs, buy-vs-build analysis, experiment design | Research briefs, options matrix, recommendation memos |
| Testing Specialist | `xhigh` | Test strategy, regression prevention, failure triage, reliability gates | Test plans, suites, bug repros, risk reports |

## Creative Researcher Squad
Use this squad for ambiguous or forward-looking work (new product directions, disruptive architecture options, rapid idea validation).

| Squad Role | Reasoning | Responsibilities | Output |
|---|---|---|---|
| Creative Lead | `xhigh` | Frame problem space, define thesis, decide exploration constraints | 1-page hypothesis brief |
| Trend Scout | `high` | Collect patterns/benchmarks from adjacent products and OSS ecosystems | Evidence digest with citations |
| Contrarian Analyst | `xhigh` | Stress-test assumptions, identify failure modes, propose anti-thesis | Risk-first critique |
| Prototype Strategist | `high` | Convert top ideas into testable spikes and measurable success criteria | Experiment backlog + KPI gates |

## Handoff Protocol
Use this for all specialist-to-specialist transfers.

1. **Brief Contract**  
Provide: goal, constraints, deadline, non-goals, and expected artifact path(s).
2. **Assumption Check (max 5 min)**  
Assignee lists key assumptions and proceeds unless blocked by a hard dependency.
3. **Delivery Bundle**  
Include: changed files, tests/checks run, known risks, and explicit next owner.
4. **Acceptance Gate**  
Receiver confirms one of: `accepted`, `accepted-with-followups`, or `rework-requested`.
5. **Escalation Rule**  
If blocked for more than one timebox, escalate with two alternatives and a recommended path.

## Autonomy Workflow
Default workflow for any specialist task:

1. **Interpret intent** into a concrete scope and done criteria.
2. **Plan minimally** (smallest set of edits to produce value).
3. **Execute in timeboxes** (deliver partial value early).
4. **Self-verify** with role-appropriate checks before handoff.
5. **Handoff immediately** once done criteria are met.
6. **Pull next task** from backlog without waiting for synchronous direction.

## Role Routing Rules
- Route high-ambiguity technical choices to `Ideas/Research` first, then `Core Coding`.
- Route risky implementation details to `Python`/`Core Coding` with `Testing` paired early.
- Route user-facing changes through `UI` + `Docs` before release.
- Engage `Creative Researcher Squad` only when requirements are uncertain or innovation is a goal.

