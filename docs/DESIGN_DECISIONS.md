# Archon Design Decisions

> Rationale behind key architectural and design choices in Archon.

---

## Table of Contents

1. [Multi-Terminal Architecture](#1-multi-terminal-architecture)
2. [File-Based IPC](#2-file-based-ipc)
3. [Subagent Specialization](#3-subagent-specialization)
4. [Keyword-Based Routing](#4-keyword-based-routing)
5. [Terminal Role Division](#5-terminal-role-division)
6. [Model Selection (Opus vs Sonnet)](#6-model-selection-opus-vs-sonnet)
7. [Dependency Resolution](#7-dependency-resolution)
8. [Python Orchestrator](#8-python-orchestrator)
9. [Dashboard Architecture](#9-dashboard-architecture)
10. [Error Handling Strategy](#10-error-handling-strategy)

---

## 1. Multi-Terminal Architecture

### Decision
Use 4 parallel Claude Code terminals instead of a single agent.

### Rationale

**Problem:** Single-agent systems hit context limits on complex projects. A single Claude instance trying to design architecture, write UI, implement features, AND write documentation will:
- Exhaust context window quickly
- Lose focus on specialized tasks
- Create bottlenecks in execution

**Solution:** Divide work across specialized terminals:
- **T1**: UI/UX focus (visual, design systems)
- **T2**: Features focus (architecture, data, logic)
- **T3**: Documentation focus (README, marketing)
- **T4**: Strategy focus (product, monetization)

### Benefits
- Each terminal maintains focused context
- Parallel execution reduces total time
- Specialization improves quality
- Failure in one terminal doesn't block others

### Trade-offs
- More complex orchestration logic
- Inter-terminal communication overhead
- Requires Claude Max subscription for parallelism

---

## 2. File-Based IPC

### Decision
Use markdown files for inter-terminal communication instead of sockets, queues, or databases.

### Rationale

**Alternatives Considered:**
| Option | Pros | Cons |
|--------|------|------|
| WebSockets | Real-time, bidirectional | Complex, requires server |
| Redis/RabbitMQ | Robust, scalable | External dependency |
| SQLite | Queryable, ACID | Overkill, SQL overhead |
| **Markdown Files** | Simple, inspectable, debuggable | Polling latency |

**Why Files Won:**
1. **Inspectable**: Can read `.orchestra/messages/t1_inbox.md` directly
2. **Debuggable**: `cat` or `tail -f` to watch messages in real-time
3. **Simple**: No external dependencies or connection management
4. **Persistent**: Survives crashes without special recovery logic
5. **Git-friendly**: Can version control if needed

### Implementation Details

Messages are stored as markdown with YAML-like headers:

```markdown
---
## Message: msg_20250131180000_0001
**From:** t2
**To:** t1
**Type:** artifact
**Time:** 2025-01-31T18:00:00.000000

Content here...
---
```

### Trade-offs
- 2-second polling latency (acceptable for our use case)
- Requires file locking for concurrent writes
- Not suitable for high-frequency messaging

---

## 3. Subagent Specialization

### Decision
Create 14 specialized subagents instead of using general-purpose prompts.

### Rationale

**Problem:** A general "developer" prompt doesn't capture nuances:
- SwiftUI has specific idioms (modifiers, state management)
- Database design requires different thinking than UI
- Marketing copy needs different tone than API docs

**Solution:** Specialized subagents with:
- Domain-specific system prompts
- Technology-appropriate code standards
- Focused tool access
- Expertise-matched model selection

### The 14 Subagents

| Domain | Subagent | Why Specialized |
|--------|----------|-----------------|
| iOS UI | swiftui-crafter | SwiftUI has unique patterns (modifiers, @State, etc.) |
| React | react-crafter | Hooks, JSX, Next.js conventions |
| HTML/CSS | html-stylist | Semantic markup, responsive design |
| Design | design-system | Tokens, variables, consistency |
| iOS Arch | swift-architect | MVVM, Clean Architecture, SPM |
| Node | node-architect | Express patterns, async handling |
| Python | python-architect | FastAPI, type hints, async |
| iOS Data | swiftdata-expert | SwiftData models, queries, migrations |
| DB | database-expert | SQL design, Prisma, indexing |
| ML | ml-engineer | PyTorch, training, inference |
| Docs | tech-writer | Clear, structured documentation |
| Marketing | marketing-strategist | ASO, positioning, copy |
| Product | product-thinker | PRDs, MVP scope, roadmaps |
| Business | monetization-expert | Pricing, models, revenue |

### Trade-offs
- More prompts to maintain
- Requires correct agent selection
- Some tasks span multiple specializations

---

## 4. Keyword-Based Routing

### Decision
Route tasks to terminals based on keyword matching in task descriptions.

### Rationale

**Alternatives Considered:**
1. **Explicit tagging**: User specifies `[T1]` - burdensome
2. **LLM classification**: Ask Claude which terminal - slow, expensive
3. **Rule-based**: Fixed patterns - inflexible
4. **Keyword matching**: Simple, fast, interpretable

**Implementation:**

```python
KEYWORDS = {
    "t1": ["ui", "view", "component", "button", "layout", "style"],
    "t2": ["api", "database", "model", "service", "backend", "logic"],
    "t3": ["readme", "docs", "guide", "tutorial", "changelog"],
    "t4": ["product", "feature", "mvp", "pricing", "strategy"]
}
```

Task description is tokenized, keywords counted, highest score wins.

### Benefits
- Zero latency (no API call)
- Predictable behavior
- Easy to debug and extend
- Handles multiple matches via scoring

### Trade-offs
- May misroute ambiguous tasks
- Requires keyword list maintenance
- Doesn't understand context/intent

---

## 5. Terminal Role Division

### Decision
Divide 4 terminals into UI, Features, Docs, and Strategy.

### Rationale

Based on typical software development phases:

```
Strategy (T4) ──▶ Architecture (T2) ──▶ UI (T1)
                       │                   │
                       ▼                   │
                   Features (T2) ◀─────────┘
                       │
                       ▼
                   Docs (T3)
```

**Why This Division:**

| Terminal | Why Separate |
|----------|--------------|
| T1 (UI) | Visual work has different rhythm, needs design focus |
| T2 (Features) | Core engineering, needs most subagents (6) |
| T3 (Docs) | Often runs last, needs to see complete system |
| T4 (Strategy) | Runs first, guides all other work |

**Subagent Distribution:**
- T1: 4 subagents (visual specialists)
- T2: 6 subagents (most complex tasks)
- T3: 2 subagents (content creation)
- T4: 2 subagents (decision making)

### Trade-offs
- Fixed roles may not fit all projects
- Some tasks don't map cleanly to one terminal
- Imbalanced workload (T2 often busiest)

---

## 6. Model Selection (Opus vs Sonnet)

### Decision
Use Opus for complex reasoning, Sonnet for focused tasks.

### Rationale

**Cost/Performance Trade-off:**

| Model | Speed | Cost | Best For |
|-------|-------|------|----------|
| Opus | Slower | Higher | Architecture, complex logic, nuanced decisions |
| Sonnet | Faster | Lower | Focused tasks, clear requirements, documentation |

**Assignment:**

```
OPUS (Complex Reasoning):
├── swift-architect (architecture decisions)
├── node-architect (system design)
├── python-architect (async patterns)
├── swiftui-crafter (complex UI)
├── react-crafter (hooks, state)
├── ml-engineer (training, inference)
├── product-thinker (strategic decisions)
└── monetization-expert (business strategy)

SONNET (Focused Tasks):
├── html-stylist (markup/CSS)
├── design-system (tokens)
├── swiftdata-expert (data models)
├── database-expert (SQL)
├── tech-writer (documentation)
└── marketing-strategist (copy)
```

### Trade-offs
- Opus tasks may bottleneck on latency
- Sonnet may miss nuance in edge cases
- Cost optimization may affect quality

---

## 7. Dependency Resolution

### Decision
Implement explicit task dependencies with automatic resolution.

### Rationale

**Problem:** Tasks have natural ordering:
- Can't write documentation until features exist
- Can't build UI until architecture is defined
- Can't set pricing until product scope is clear

**Solution:** Tasks declare dependencies:

```python
Task(
    id="t2_features",
    title="Implement core features",
    dependencies=["t2_architecture"]  # Must complete first
)
```

**Resolution Algorithm:**
1. Get all pending tasks
2. Filter to tasks whose dependencies are ALL completed
3. Return as "ready" tasks for execution

```python
def get_ready_tasks(self):
    return [
        task for task in self.pending
        if all(dep.status == COMPLETED for dep in task.dependencies)
    ]
```

### Benefits
- Automatic ordering
- Parallel execution when possible
- Clear execution graph

### Trade-offs
- Circular dependencies crash the system
- Over-specification slows execution
- Under-specification causes race conditions

---

## 8. Python Orchestrator

### Decision
Write the orchestrator in Python (not TypeScript, Go, or Shell).

### Rationale

**Alternatives:**

| Language | Pros | Cons |
|----------|------|------|
| TypeScript | Claude Code native | Adds build step, Node dependency |
| Go | Fast, concurrent | Slower development iteration |
| Shell | Simple | Hard to maintain, no types |
| **Python** | Fast iteration, async, FastAPI | GIL for true parallelism |

**Why Python Won:**
1. **FastAPI**: Beautiful API for dashboard
2. **Async/await**: Natural for subprocess coordination
3. **Type hints**: Self-documenting code
4. **Ecosystem**: Rich libraries (pathlib, dataclasses, json)
5. **Iteration speed**: Quick changes during development

### Implementation Notes
- Python 3.11+ for modern typing
- `asyncio` for concurrent terminal execution
- `dataclasses` for clean data structures
- `pathlib` for cross-platform paths

### Trade-offs
- GIL limits true parallelism (mitigated by subprocesses)
- Runtime type checking (mitigated by strict typing)
- Slower than compiled languages (acceptable for our use)

---

## 9. Dashboard Architecture

### Decision
Build dashboard with FastAPI + vanilla JavaScript (no React/Vue).

### Rationale

**Problem:** Need real-time visibility into orchestrator state.

**Alternatives:**

| Option | Pros | Cons |
|--------|------|------|
| React SPA | Rich UI, ecosystem | Build step, complexity |
| Vue SPA | Simple, reactive | Still needs build |
| Next.js | SSR, modern | Heavyweight for monitoring |
| **FastAPI + Vanilla JS** | No build, single file, simple | Less structured |

**Why Vanilla JS:**
1. Dashboard is monitoring, not interaction-heavy
2. Single HTML file, no build step
3. WebSocket API is simple enough in vanilla JS
4. Minimal dependencies = easier maintenance

### Implementation

```
FastAPI Backend              Vanilla JS Frontend
┌───────────────────┐       ┌───────────────────┐
│ /api/status       │◀──────│ fetch() polling   │
│ /api/tasks        │       │                   │
│ /api/messages     │       │                   │
│ /ws (WebSocket)   │◀═════▶│ WebSocket client  │
└───────────────────┘       └───────────────────┘
```

### Trade-offs
- Less structured frontend code
- No component reusability
- Manual DOM manipulation

---

## 10. Error Handling Strategy

### Decision
Implement retry with exponential backoff and graceful degradation.

### Rationale

**Failure Modes:**
1. **Transient**: Network timeout, temporary Claude overload
2. **Permanent**: Invalid task, missing dependency
3. **Partial**: Task partially completes then fails

**Strategy:**

```python
MAX_RETRIES = 2
BACKOFF = [5, 15, 30]  # seconds

for attempt in range(MAX_RETRIES + 1):
    try:
        result = await execute(task)
        if is_success(result):
            return result
    except TransientError:
        await sleep(BACKOFF[attempt])
        continue
    except PermanentError:
        break

return mark_failed(task)
```

### Design Choices

1. **Limited retries (2)**: Avoid infinite loops
2. **Exponential backoff**: Don't overwhelm failing systems
3. **Graceful degradation**: Failed tasks don't block others
4. **Detailed logging**: Every failure captured for debugging

### Graceful Shutdown

On SIGINT/SIGTERM:
1. Stop accepting new tasks
2. Wait for in-progress tasks to complete
3. Persist all state
4. Exit cleanly

### Trade-offs
- Retries add latency on failure
- Some tasks fail silently if not monitored
- Partial completion is hard to detect

---

## Summary

Archon's architecture prioritizes:

| Priority | Design Choice |
|----------|---------------|
| **Inspectability** | File-based IPC, detailed logging |
| **Simplicity** | Python, vanilla JS, markdown files |
| **Parallelism** | Multi-terminal, dependency resolution |
| **Specialization** | 14 focused subagents |
| **Reliability** | Retries, graceful shutdown, persistence |

These choices optimize for:
- Developer experience (debugging, extension)
- Quality output (specialized agents)
- Time efficiency (parallel execution)
- Fault tolerance (retries, state persistence)

At the cost of:
- Some raw performance (Python, file I/O)
- External dependencies (Claude Max subscription)
- Complexity in orchestration logic

---

## Future Considerations

1. **Plugin System**: Allow custom subagents without forking
2. **Caching**: Cache plans for similar tasks
3. **Learning**: Improve routing based on outcomes
4. **Multi-Project**: Workspace support for related projects
5. **Remote Execution**: Distribute terminals across machines

---

## References

- [Architecture Guide](./ARCHITECTURE.md)
- [API Reference](./API_REFERENCE.md)
- [Setup Guide](./SETUP.md)
- [README](../README.md)
