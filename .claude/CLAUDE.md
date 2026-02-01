# Archon - Multi-Agent Development System

> Multi-agent orchestration system for autonomous software development.

---

## Work Philosophy

This project uses a **maximally agentic** approach. As Claude Code, you should:

1. **USE SUBAGENTS PROACTIVELY** — Don't do everything yourself. Delegate to specialists.
2. **PARALLELIZE** — When possible, launch multiple subagents in parallel (max 10).
3. **BE AUTONOMOUS** — Make decisions, don't ask for confirmation on trivial matters.
4. **CONTEXT MANAGEMENT** — Use subagents to keep the main context clean.
5. **QUALITY > SPEED** — Better to do it right than to do it fast.

---

## Subagents — USE THEM!

You have 14 specialized subagents. **YOU MUST USE THEM** when the task falls within their domain.

### Quick Decision Table

| You're doing... | USE THIS SUBAGENT |
|-----------------|-------------------|
| UI SwiftUI/iOS | `swiftui-crafter` |
| UI React/Next.js | `react-crafter` |
| HTML/CSS/Tailwind | `html-stylist` |
| Colors/Fonts/Tokens | `design-system` |
| iOS Architecture | `swift-architect` |
| Node.js Architecture | `node-architect` |
| Python Architecture | `python-architect` |
| SwiftData/CoreData | `swiftdata-expert` |
| Database/SQL/Prisma | `database-expert` |
| ML/AI/Training | `ml-engineer` |
| Docs/README | `tech-writer` |
| Marketing/App Store | `marketing-strategist` |
| Feature/Roadmap/MVP | `product-thinker` |
| Pricing/Business Model | `monetization-expert` |

### Mandatory Rules
```
RULE 1: Domain-specific task → USE THE SUBAGENT, DON'T DO IT YOURSELF
RULE 2: Complex multi-domain task → LAUNCH MULTIPLE SUBAGENTS IN PARALLEL
RULE 3: Codebase exploration → USE SUBAGENT to keep context clean
RULE 4: NEVER do iOS UI without swiftui-crafter
RULE 5: NEVER make architectural decisions without the appropriate architect
RULE 6: NEVER write copy/marketing without marketing-strategist
RULE 7: NEVER define pricing without monetization-expert
```

### Usage Patterns

**Pattern A: Single Specialist**
```
Request: "Create a card component for planets"
Action: Invoke swiftui-crafter
```

**Pattern B: Parallel Multi-Specialist**
```
Request: "Add timer feature with persistence"
Action: Launch in PARALLEL:
  ├── swift-architect → structure/patterns
  ├── swiftui-crafter → UI components
  └── swiftdata-expert → data models
Then: Synthesize the results
```

**Pattern C: Strategic Pipeline**
```
Request: "Can this app generate revenue?"
Action: Launch in SEQUENCE:
  1. product-thinker → value/market analysis
  2. marketing-strategist → positioning/competitors
  3. monetization-expert → pricing/business model
```

**Pattern D: New Project**
```
Request: "Let's create an app for X"
Action:
  1. product-thinker → MVP scope, core features
  2. [swift/node/python]-architect → project structure
  3. design-system → base tokens, palette
  4. tech-writer → initial README
```

---

## MCP — Context7

### Use with Moderation

Context7 is the only available MCP but **HAS AN API COST**.
```
WHEN TO USE CONTEXT7:
✅ Official framework/library documentation
✅ API references you don't know well
✅ Specific problems requiring updated docs

WHEN NOT TO USE CONTEXT7:
❌ Things you already know how to do
❌ Generic best practices
❌ Questions solvable with basic knowledge
❌ As first resort — try without it first

RULE: Use Context7 ONLY if you're stuck or need specific documentation.
      Don't use it preemptively "just in case".
```

---

## Autonomy and Decisions

### YOU CAN DO WITHOUT ASKING
```
✅ Create/modify/delete files in the project
✅ Launch any appropriate subagent
✅ Install necessary dependencies (pip, npm)
✅ Refactor to improve code quality
✅ Add documentation and comments
✅ Fix obvious bugs
✅ Create tests
✅ Format and lint code
✅ Create new folders/structures
✅ Minor naming/convention decisions
```

### ASK BEFORE
```
⚠️ Changing fundamental project architecture
⚠️ Deleting existing working functionality
⚠️ Modifying critical business logic
⚠️ Changing dependencies to different major versions
⚠️ Decisions that significantly impact UX
⚠️ Spending money (external APIs, services)
```

---

## Project Structure
```
~/Tech/Archon/
|
├── .claude/
|   ├── CLAUDE.md             ← This file (read it always!)
│   ├── settings.json         ← Config, hooks, permissions
│   ├── settings.local.json   ← Personal overrides (gitignored)
│   └── agents/               ← 14 project subagents
│       ├── swiftui-crafter.yml
│       ├── react-crafter.yml
│       ├── html-stylist.yml
│       ├── design-system.yml
│       ├── swift-architect.yml
│       ├── node-architect.yml
│       ├── python-architect.yml
│       ├── swiftdata-expert.yml
│       ├── database-expert.yml
│       ├── ml-engineer.yml
│       ├── tech-writer.yml
│       ├── marketing-strategist.yml
│       ├── product-thinker.yml
│       └── monetization-expert.yml
├── orchestrator/             ← Python orchestrator core
├── templates/                ← Terminal system prompts
└── Apps/                     ← Generated projects
```

---

## Code Standards

### Python
- Python 3.11+
- Type hints ALWAYS
- Formatter: Black
- Linter: Ruff
- Docstrings: Google style
- Async/await for I/O operations

### Swift (target projects)
- Swift 5.9+
- SwiftUI for UI
- SwiftData for persistence
- Pattern: MVVM or similar
- Docs with /// for public APIs

### Node.js/TypeScript (target projects)
- TypeScript strict mode
- ESLint + Prettier
- Zod for input validation
- Explicit error handling

### General
- Clear and atomic commits
- One branch per feature
- Updated documentation

---

## REMINDER — READ EVERY SESSION
```
╔══════════════════════════════════════════════════════════════╗
║  ⚡ USE SUBAGENTS — They exist for this, USE THEM!           ║
║  ⚡ PARALLELIZE — Up to 10 subagents simultaneously          ║
║  ⚡ CLEAN CONTEXT — Delegate exploration to subagents        ║
║  ⚡ BE DECISIVE — Don't ask about every little thing         ║
║  ⚡ CONTEXT7 SPARINGLY — It costs, use only when needed      ║
║  ⚡ DOCUMENT — Important decisions should be written down    ║
╚══════════════════════════════════════════════════════════════╝
```

---

## Quick Reference

**Launch explicit subagent:**
```
"Use the swiftui-crafter subagent to create..."
```

**Launch parallel subagents:**
```
"Launch in parallel swift-architect, swiftui-crafter and swiftdata-expert for..."
```

**See available subagents:**
```
/agents
```

---

Created: January 2025
Subagents: 14
MCP: Context7 (moderate use)
