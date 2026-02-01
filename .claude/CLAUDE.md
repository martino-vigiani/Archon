# Archon - Multi-Agent Development System

> Sistema di orchestrazione multi-agente per sviluppo software autonomo.

---

## 🎯 Filosofia di Lavoro

Questo progetto utilizza un approccio **massimamente agentico**. Come Claude Code devi:

1. **USARE PROATTIVAMENTE I SUBAGENT** — Non fare tutto da solo. Delega agli specialisti.
2. **PARALLELIZZARE** — Quando possibile, lancia più subagent in parallelo (max 10).
3. **ESSERE AUTONOMO** — Prendi decisioni, non chiedere conferma per ogni cosa banale.
4. **CONTEXT MANAGEMENT** — Usa i subagent per mantenere il context principale pulito.
5. **QUALITÀ > VELOCITÀ** — Meglio fare bene che fare in fretta.

---

## 🤖 Subagent — USALI!

Hai 14 subagent specializzati. **DEVI USARLI** quando il task rientra nel loro dominio.

### Tabella Decisionale Rapida

| Stai facendo... | USA QUESTO SUBAGENT |
|-----------------|---------------------|
| UI SwiftUI/iOS | `swiftui-crafter` |
| UI React/Next.js | `react-crafter` |
| HTML/CSS/Tailwind | `html-stylist` |
| Colori/Font/Tokens | `design-system` |
| Architettura iOS | `swift-architect` |
| Architettura Node.js | `node-architect` |
| Architettura Python | `python-architect` |
| SwiftData/CoreData | `swiftdata-expert` |
| Database/SQL/Prisma | `database-expert` |
| ML/AI/Training | `ml-engineer` |
| Docs/README | `tech-writer` |
| Marketing/App Store | `marketing-strategist` |
| Feature/Roadmap/MVP | `product-thinker` |
| Pricing/Business Model | `monetization-expert` |

### ⚠️ Regole OBBLIGATORIE
```
REGOLA 1: Task specifico di dominio → USA IL SUBAGENT, NON FARLO TU
REGOLA 2: Task complesso multi-dominio → LANCIA PIÙ SUBAGENT IN PARALLELO
REGOLA 3: Esplorazione codebase → USA SUBAGENT per non sporcare il context
REGOLA 4: MAI fare UI iOS senza swiftui-crafter
REGOLA 5: MAI fare decisioni architetturali senza l'architect appropriato
REGOLA 6: MAI scrivere copy/marketing senza marketing-strategist
REGOLA 7: MAI definire pricing senza monetization-expert
```

### Pattern di Utilizzo

**Pattern A: Singolo Specialista**
```
Richiesta: "Crea un componente card per i pianeti"
Azione: Invoca swiftui-crafter
```

**Pattern B: Parallelo Multi-Specialista**
```
Richiesta: "Aggiungi feature timer con persistenza"
Azione: Lancia in PARALLELO:
  ├── swift-architect → struttura/pattern
  ├── swiftui-crafter → UI componenti
  └── swiftdata-expert → modelli dati
Poi: Sintetizza i risultati
```

**Pattern C: Pipeline Strategica**
```
Richiesta: "Questa app può generare revenue?"
Azione: Lancia in SEQUENZA:
  1. product-thinker → analisi valore/mercato
  2. marketing-strategist → positioning/competitor
  3. monetization-expert → pricing/business model
```

**Pattern D: Nuovo Progetto**
```
Richiesta: "Creiamo un'app per X"
Azione:
  1. product-thinker → MVP scope, features core
  2. [swift/node/python]-architect → struttura progetto
  3. design-system → tokens base, palette
  4. tech-writer → README iniziale
```

---

## 🔌 MCP — Context7

### ⚠️ USA CON MODERAZIONE

Context7 è l'unico MCP disponibile ma **HA UN COSTO API**.
```
QUANDO USARE CONTEXT7:
✅ Documentazione ufficiale di framework/librerie
✅ API reference che non conosci bene
✅ Problemi specifici che richiedono docs aggiornate

QUANDO NON USARE CONTEXT7:
❌ Cose che già sai fare
❌ Best practices generiche
❌ Domande risolvibili con conoscenza base
❌ Prima risorsa — provaci prima senza

REGOLA: Usa Context7 SOLO se sei bloccato o serve documentazione specifica.
         Non usarlo preventivamente "per sicurezza".
```

---

## 🔄 Autonomia e Decisioni

### PUOI FARE SENZA CHIEDERE
```
✅ Creare/modificare/eliminare file nel progetto
✅ Lanciare qualsiasi subagent appropriato
✅ Installare dipendenze necessarie (pip, npm)
✅ Refactoring per migliorare qualità codice
✅ Aggiungere documentazione e commenti
✅ Fixare bug evidenti
✅ Creare test
✅ Formattare e lintare codice
✅ Creare nuove cartelle/strutture
✅ Decisioni di naming/convenzioni minori
```

### CHIEDI PRIMA DI
```
⚠️ Cambiare architettura fondamentale del progetto
⚠️ Eliminare funzionalità esistenti e funzionanti
⚠️ Modificare business logic critica
⚠️ Cambiare dipendenze a major version diverse
⚠️ Decisioni che impattano UX significativamente
⚠️ Spendere soldi (API esterne, servizi)
```

---

## 📁 Struttura Progetto
```
~/Tech/Archon/
|
├── .claude/
|   ├── CLAUDE.md                 ← Questo file (leggilo sempre!)
│   ├── settings.json         ← Config, hooks, permissions
│   ├── settings.local.json   ← Override personali (gitignored)
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
├── orchestrator/             ← Python orchestrator core (TODO)
├── prompts/                  ← System prompts per terminali (TODO)
└── templates/                ← Template per nuovi progetti (TODO)
```

---

## 🛠 Code Standards

### Python
- Python 3.11+
- Type hints SEMPRE
- Formatter: Black
- Linter: Ruff
- Docstrings: Google style
- Async/await per I/O operations

### Swift (progetti target)
- Swift 5.9+
- SwiftUI per UI
- SwiftData per persistenza
- Pattern: MVVM o simile
- Docs con /// per API pubbliche

### Node.js/TypeScript (progetti target)
- TypeScript strict mode
- ESLint + Prettier
- Zod per validation input
- Error handling esplicito

### Generale
- Commits chiari e atomici
- Un branch per feature
- Documentazione aggiornata

---

## 🚨 REMINDER — LEGGILO OGNI SESSIONE
```
╔══════════════════════════════════════════════════════════════╗
║  ⚡ USA I SUBAGENT — Esistono per questo, USALI!             ║
║  ⚡ PARALLELIZZA — Fino a 10 subagent contemporanei          ║
║  ⚡ CONTEXT PULITO — Delega esplorazione ai subagent         ║
║  ⚡ SII DECISIVO — Non chiedere per ogni virgola             ║
║  ⚡ CONTEXT7 CON PARSIMONIA — Costa, usalo solo se serve     ║
║  ⚡ DOCUMENTA — Decisioni importanti vanno scritte           ║
╚══════════════════════════════════════════════════════════════╝
```

---

## 📚 Quick Reference

**Lanciare subagent esplicito:**
```
"Usa il subagent swiftui-crafter per creare..."
```

**Lanciare subagent paralleli:**
```
"Lancia in parallelo swift-architect, swiftui-crafter e swiftdata-expert per..."
```

**Vedere subagent disponibili:**
```
/agents
```

---

Creato: Gennaio 2025
Subagent: 14
MCP: Context7 (uso moderato)