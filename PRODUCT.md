# Product

## Register

product

## Users

The owner/operator of Archon — a single power-user (the "CEO" in Archon's own
metaphor) who launches and steers autonomous multi-agent software builds. They
sit in front of the control-plane dashboard (localhost:8420) while 1–N Claude
Code terminals work in parallel, watching what each agent is doing, which model
and effort tier it's running, and how close it is to done. Context is
high-focus, technical, often long-running sessions. As a power-user they
tolerate information density and value keyboard reach and shortcuts, but the
original pain was *not knowing what was happening or which models were in use* —
so legibility of state beats raw density.

## Product Purpose

Archon orchestrates parallel Claude Code agents that build software
autonomously. The dashboard is the cockpit: it makes an otherwise invisible
swarm observable and steerable. Three jobs carry equal weight:

- **Observe** — at a glance, what each agent is doing, which model/effort, task
  progress, quality, files produced, prompts sent.
- **Control** — pause/resume, inject tasks, set per-worker mode, intervene in
  real time.
- **Launch** — start and configure new runs (working dir, agent roster, model
  tier, effort, plan mode).

Success = the operator always knows the state of the orchestration and can
redirect it in seconds, without reading logs or guessing.

## Brand Personality

Calm, technical, precise. A serious instrument, not a toy and not a billboard.
Voice is direct and concrete: it names what is happening (state, model, effort)
in plain terms. Color and motion are restraint by default and meaning when
present — neutral monochrome surfaces with a single accent and semantic status
colors that only appear where they carry information. The feeling is quiet
confidence and total transparency, never spectacle.

## Anti-references

This must NOT look like any of these:

- **Generic SaaS slop** — purple-gradient-on-white, identical card grids,
  tiny uppercase eyebrow above every section, the hero-metric template.
- **An overloaded ops dashboard** (Grafana/Datadog density) — walls of widgets,
  everything shouting at once, no breathing room.
- **A playful consumer app** — cartoon-rounded, emoji-strewn, friendly-to-a-fault;
  it would undercut "serious instrument".
- **Dated gray enterprise** — 1990s Bootstrap, dead grays, naked tables, zero
  character.

The target sits between these: distinctive and warm-enough to feel crafted,
quiet and dense-capable enough to feel like a real tool.

## Design Principles

1. **Signal, not noise.** Color, motion, and density all carry meaning. The
   default state is calm; emphasis is earned, never ambient.
2. **Orchestration is transparent.** The operator must always be able to see
   what each agent is doing and *which model / effort* it runs — surfacing this
   is the product's reason to exist, not an afterthought.
3. **Power within reach, not in your face.** Progressive disclosure: strong
   controls (inject, per-worker mode, model/effort) are one gesture away but
   don't crowd the default view.
4. **Serious instrument.** Craft and restraint over decoration; legible,
   rounded, confident — never toy-like, never dated-gray.
5. **Accessible by default.** WCAG AA contrast, visible focus, keyboard reach,
   and reduced-motion are gates on every surface, not a later pass.

## Accessibility & Inclusion

WCAG AA is the standard (contrast ≥4.5:1 body / ≥3:1 large; focus rings on the
accent; full keyboard reach). `prefers-reduced-motion` is honored everywhere
(entrance/pulse animations have a hard reset). Status is never encoded by color
alone — pair semantic color with text/label/shape (e.g. state pills carry
words, the live dot pairs with a label).
