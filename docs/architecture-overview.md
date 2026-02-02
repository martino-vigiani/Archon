# Archon 2.0 Architecture Overview

> The Organic Multi-Agent Development System

---

## Philosophy: The Garden Model

Archon 2.0 reimagines multi-agent orchestration through the lens of **organic growth** rather than mechanical coordination. Instead of treating AI terminals as machines executing instructions, we model them as **craftspeople in a collaborative workshop**, with Archon serving as the **Gardener** who cultivates their work.

### The Gardener Mindset

Traditional orchestrators work like factory managers: assign tasks, wait for completion, check results. Archon works like a gardener:

- **Observe** the garden constantly (heartbeats, reports, quality levels)
- **Nurture** what's growing well (AMPLIFY)
- **Guide** what's drifting (REDIRECT)
- **Mediate** conflicts between plants competing for resources (MEDIATE)
- **Plant** new seeds where gaps appear (INJECT)
- **Prune** overgrowth that would tangle the garden (PRUNE)

```
                    ┌─────────────────────────────┐
                    │   ARCHON                    │
                    │   The Gardener              │
                    └──────────────┬──────────────┘
                                   │
          ┌────────────────────────┼────────────────────────┐
          │                        │                        │
          ▼                        ▼                        ▼
    ┌───────────┐            ┌───────────┐            ┌───────────┐
    │ Contracts │            │  Quality  │            │ Messages  │
    └─────┬─────┘            └─────┬─────┘            └─────┬─────┘
          │                        │                        │
    ══════╧════════════════════════╧════════════════════════╧══════
                     COLLABORATION LAYER
    ═══════════════════════════════════════════════════════════════
          │              │         │         │              │
     ╭────▼────╮    ╭────▼────╮ ╭──▼──╮ ╭────▼────╮    ╭────▼────╮
     │ [✧] T1 │◄──►│ [▣] T2 │◄►│[♟]T4│◄►│ [✎] T3 │◄──►│ [?] T5 │
     │Craftsman│    │Architect│ │Strat│ │Narrator │    │ Skeptic │
     ╰─────────╯    ╰─────────╯ ╰─────╯ ╰─────────╯    ╰─────────╯
```

---

## The Five Craftspeople

Each terminal embodies a distinct persona with its own philosophy and expertise.

### [✧] T1 - The Craftsman (UI/UX)

**Philosophy:** *"Beauty with purpose. Build first, integrate later."*

The Craftsman focuses on what users see and touch. They don't wait for backend systems to be ready - they create interfaces with mock data and define clear contracts for what they need from other terminals.

**Expertise:**
- SwiftUI, React, HTML/CSS
- Design systems and tokens
- User experience patterns
- Visual polish and animations

**Working Style:**
- Creates UI components independently
- Documents interface expectations as contracts
- Iterates rapidly on visual feedback
- Quality gate: Users can interact with every feature

### [▣] T2 - The Architect (Backend/Features)

**Philosophy:** *"Strong foundations support tall buildings."*

The Architect builds the systems that power the application. They create robust, tested foundations that other terminals can rely on. Every piece of infrastructure comes with tests.

**Expertise:**
- System architecture (MVVM, Clean Architecture)
- Data models and persistence
- API design and implementation
- Testing strategies and TDD

**Working Style:**
- Builds with tests from the start
- Creates interfaces that match T1's contracts
- Documents technical decisions
- Quality gate: All tests pass, APIs are documented

### [✎] T3 - The Narrator (Documentation)

**Philosophy:** *"Every great system has a story. Tell it well."*

The Narrator captures the evolving understanding of the system. They don't write documentation after the fact - they document as the system grows, creating a living record.

**Expertise:**
- Technical writing
- API documentation
- User guides and tutorials
- Architecture decision records

**Working Style:**
- Observes other terminals' work
- Documents patterns as they emerge
- Keeps README and guides current
- Quality gate: New users can understand the system

### [♟] T4 - The Strategist (Product Vision)

**Philosophy:** *"See the whole board. Guide, don't block."*

The Strategist holds the product vision and keeps everyone aligned. They broadcast direction early and often but never become a bottleneck. Their job is to illuminate the path, not to walk it for others.

**Expertise:**
- MVP definition and scope
- Feature prioritization
- Product roadmaps
- Business model alignment

**Working Style:**
- Broadcasts MVP scope within first 2 minutes
- Answers strategic questions asynchronously
- Mediates scope disagreements
- Quality gate: All work aligns with MVP goals

### [?] T5 - The Skeptic (QA/Testing)

**Philosophy:** *"Trust but verify. Question everything."*

The Skeptic is the quality guardian. They don't wait until the end to test - they validate continuously throughout development, catching issues early when they're cheap to fix.

**Expertise:**
- Build validation
- Integration testing
- Contract verification
- Quality gate enforcement

**Working Style:**
- Runs build checks every 2 minutes during Phase 1
- Verifies contracts match implementations
- Reports issues to responsible terminals
- Quality gate: Build passes, contracts verified, tests green

---

## The Quality Gradient

Work in Archon flows through a **Quality Gradient** - a continuous spectrum from initial sketch to production-ready excellence.

```
Quality Gradient
0.0 ═══════════════════════════════════════════════════════════════ 1.0
│ Sketch │  Draft  │ Working │  Solid  │ Polished │ Excellent │
   0.2       0.4       0.5       0.7        0.85        1.0
```

### Quality Levels

| Level | Value | Description | Example |
|-------|-------|-------------|---------|
| **Sketch** | 0.2 | Initial structure, placeholders | Empty view with TODO comments |
| **Draft** | 0.4 | Core functionality roughed in | View renders but lacks styling |
| **Working** | 0.5 | Feature functions correctly | View works with mock data |
| **Solid** | 0.7 | Well-structured, handles edge cases | View handles loading/error states |
| **Polished** | 0.85 | Clean code, good UX | View is responsive, accessible |
| **Excellent** | 1.0 | Production-ready perfection | View is tested, documented, optimized |

### The Ratchet Principle

Quality only moves forward. Once work reaches a quality level, it should never regress. This is enforced through:

1. **Continuous validation** - T5 monitors quality constantly
2. **Contract verification** - Implementations must match contracts
3. **Build gates** - Code must compile at all times
4. **Test requirements** - Tests must pass before proceeding

---

## Manager Interventions

The Gardener (Archon) has five intervention types to nurture the development process.

```
┌─────────────────────────────────────────────────────────────────────┐
│                  ARCHON INTERVENTION TYPES                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   ◉ AMPLIFY    When work flourishes, give it more resources        │
│   ○ REDIRECT   When work drifts, guide it back on course           │
│   ◈ MEDIATE    When terminals conflict, facilitate agreement       │
│   ◆ INJECT     When gaps appear, plant new seeds of work           │
│   ✂ PRUNE      When work tangles, cut away the excess              │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### ◉ AMPLIFY

**When:** A terminal's work is flourishing and others could benefit from more of it.

**Example:** T2's architecture is excellent and T1 is waiting for more APIs.

**Action:** Extend T2's scope, add related tasks, broadcast availability.

### ○ REDIRECT

**When:** A terminal has drifted from the MVP scope or is working on low-priority features.

**Example:** T1 is building dark mode when the core counter UI isn't done.

**Action:** Send clarifying message, reprioritize task queue, reference MVP scope.

### ◈ MEDIATE

**When:** Two terminals disagree on an interface contract or approach.

**Example:** T1 wants required `avatarURL`, T2 says it can't guarantee URLs.

**Action:** Analyze both perspectives, propose compromise, create amended contract.

### ◆ INJECT

**When:** A gap in the work is blocking progress or a critical piece is missing.

**Example:** T5 needs logging infrastructure that no one was assigned to build.

**Action:** Create new task, assign to appropriate terminal, set priority.

### ✂ PRUNE

**When:** Work is becoming over-engineered or scope is expanding beyond MVP.

**Example:** T3 is writing a 50-page architecture guide when a simple README is needed.

**Action:** Cancel excessive tasks, clarify minimal requirements, refocus efforts.

---

## Contract Negotiation

Terminals communicate expectations through **Interface Contracts** - formal agreements about what one terminal needs from another.

```
T1 Proposes ──► T2 Responds ──► T4 Mediates ──► Agreement ──► Implementation ──► T5 Verifies
```

### Contract Lifecycle

1. **PROPOSED** - T1 (or any terminal) documents what it needs
2. **NEGOTIATING** - Receiving terminal reviews and responds
3. **AGREED** - Both parties commit to the interface
4. **IMPLEMENTED** - Providing terminal builds the agreed interface
5. **VERIFIED** - T5 confirms implementation matches contract

### Contract Example

```json
{
  "name": "UserDisplayData",
  "status": "VERIFIED",
  "defined_by": "t1",
  "implemented_by": "t2",
  "verified_by": "t5",
  "interface": {
    "type": "struct",
    "fields": [
      {"name": "id", "type": "UUID", "required": true},
      {"name": "name", "type": "String", "required": true},
      {"name": "avatarURL", "type": "URL?", "required": false}
    ]
  },
  "negotiation_history": [
    "T1 proposed with required avatarURL",
    "T2 responded: cannot guarantee URLs",
    "T4 mediated: make avatarURL optional",
    "Both agreed"
  ]
}
```

### Why Contracts Matter

1. **No blocking** - Terminals don't wait for each other; they work against contracts
2. **Clear expectations** - Mismatches are caught early
3. **Accountability** - Each terminal knows what it committed to
4. **Verification** - T5 can objectively verify compliance

---

## The Growth Phases

Development flows through four organic phases.

```
PHASE 0: SEED                         PHASE 1: SPROUT
┌─────────────────────┐               ┌─────────────────────┐
│        ·            │               │        |            │
│       /|\           │               │       /|\           │
│        |            │               │      / | \          │
│      -----          │               │     /  |  \         │
│   [✧][▣][✎][♟][?]   │               │    T1 T2 T3 T4 T5   │
│                     │               │    ██ ██ ██ ██ ██   │
│  Contracts planted  │               │  All growing        │
│  MVP scope defined  │               │  parallel           │
└─────────────────────┘               └─────────────────────┘

PHASE 2: BLOOM                        PHASE 3: HARVEST
┌─────────────────────┐               ┌─────────────────────┐
│       \|/           │               │        🌳           │
│      --*--          │               │       /||\          │
│       /|\           │               │      / || \         │
│      / | \          │               │     /  ||  \        │
│     T1═══T2         │               │   ████████████      │
│     Integration     │               │   Working Software  │
│     Contracts met   │               │   Tested & Verified │
└─────────────────────┘               └─────────────────────┘
```

### Phase 0: SEED (Planning & Contracts)

**Duration:** 2-5 minutes

**Activities:**
- T4 broadcasts MVP scope to all terminals
- T1 creates interface contracts for T2
- T5 sets up monitoring infrastructure
- All terminals read the plan and prepare

**Quality Target:** 0.2 (Sketch level contracts)

**Exit Criteria:** MVP scope broadcast, initial contracts proposed

### Phase 1: SPROUT (Parallel Build)

**Duration:** 10-20 minutes

**Activities:**
- All terminals build in parallel
- T1 creates UI with mock data
- T2 builds architecture, models, tests
- T3 creates documentation structure
- T5 validates builds every 2 minutes

**Quality Target:** 0.5 (Working level)

**Exit Criteria:** All terminals have working artifacts, build passes

### Phase 2: BLOOM (Integration)

**Duration:** 5-10 minutes

**Activities:**
- T1 connects UI to T2's real APIs
- T2 ensures implementations match contracts
- T5 verifies contract compliance
- T3 updates documentation with real examples

**Quality Target:** 0.7 (Solid level)

**Exit Criteria:** UI uses real data, all contracts verified

### Phase 3: HARVEST (Test & Verify)

**Duration:** 2-5 minutes

**Activities:**
- T5 runs full test suite
- T1 verifies UI compilation and previews
- T3 finalizes documentation
- All quality gates must pass

**Quality Target:** 0.85+ (Polished level)

**Exit Criteria:** All tests pass, documentation complete, build verified

---

## Communication Patterns

### Heartbeats

Every terminal sends a heartbeat every 30 seconds:

```json
{
  "terminal": "t1",
  "status": "working",
  "current_task": "Create ProfileView",
  "progress": "60%",
  "quality": 0.6,
  "files_touched": ["Views/ProfileView.swift"],
  "ready_artifacts": ["UserDisplayData interface"],
  "waiting_for": null
}
```

The Gardener reads these heartbeats to understand the garden's health and decide when to intervene.

### Broadcasts

System-wide messages visible to all terminals:

```markdown
## MVP Scope (from T4)

Counter App v1.0:
- Single counter display
- Increment/decrement buttons
- Reset button

NOT in scope:
- Multiple counters
- Persistence
- Themes
```

### Direct Messages

Terminal-to-terminal communication:

```markdown
## From T1 to T2

I need the Counter model to implement `Identifiable`.
My view uses `ForEach(counters)` which requires it.

Can you add this conformance?
```

---

## Putting It All Together

The organic model creates a development environment where:

1. **Terminals are autonomous** - They don't wait for permission or detailed instructions
2. **Contracts enable parallelism** - Clear interfaces let everyone work simultaneously
3. **Quality is continuous** - Not a final gate but a constant gradient
4. **The Gardener nurtures** - Interventions help rather than control
5. **Growth is natural** - From seed to harvest through organic phases

### Example: Building a Counter App

```
Phase 0 (2 min):
  T4 broadcasts: "Counter with +/- buttons, reset, no persistence"
  T1 proposes: CounterViewModel contract with increment/decrement methods
  T5 sets up build monitoring

Phase 1 (15 min):
  T1 builds CounterView with mock viewModel
  T2 builds CounterViewModel with @Observable, implements contract
  T3 creates README structure
  T5 runs build checks (passes at minute 3, 5, 7...)

Phase 2 (8 min):
  T1 swaps mock for real CounterViewModel
  T2 confirms contract compliance
  T5 verifies: "CounterViewModel matches T1's contract"

Phase 3 (3 min):
  T5 runs: swift build (pass), swift test (pass)
  T3 completes documentation
  Quality: 0.87 (Polished)

Result: Working counter app in ~28 minutes
```

---

## Summary

Archon 2.0's organic architecture transforms multi-agent development from mechanical task execution into collaborative craftsmanship. The Gardener nurtures five specialized craftspeople who work autonomously but in harmony, connected by contracts and quality gradients.

This model produces:
- **Faster results** through true parallelism
- **Higher quality** through continuous verification
- **Better communication** through formal contracts
- **Adaptability** through intelligent interventions
- **Reliability** through the quality ratchet

The garden grows naturally toward working software.

---

*See [diagrams.md](./diagrams.md) for copy-paste ready ASCII diagrams.*
