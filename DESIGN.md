# Design

Visual system for the Archon control-plane dashboard. Name: **MONO**. Captured
from the shipped implementation (`orchestrator/static/css/tokens.css`,
`app.css`, `motion.css`, and the per-view modules). Source of truth for tokens
is `tokens.css`; this document is the human-readable map. Every value is a CSS
custom property — components reference `var(--…)`, never hardcoded literals.

## Theme

Modern minimalist control plane. True-neutral grey ladder, ONE vivid indigo
accent, vivid semantic status colors. **Color is signal, never decoration** —
hue appears only where it carries meaning (state, the primary action, data viz).
Everything is rounded; surfaces are calm and airy; depth is carried by soft
neutral shadows and whisper-quiet film grain (`--grain-opacity` ≤0.04).

Two themes, both first-class, switched via `document.documentElement.dataset.theme`
(persisted in `localStorage['archon.theme']`, applied pre-paint to avoid FOUC):

- **Dark (default):** near-black neutral page, never `#000`.
- **Light:** paper-white page, deep neutral ink.

Color strategy: **Restrained** — tinted-neutral surfaces + a single accent
holding well under 10% of the surface, status color used sparingly as signal.

## Color

OKLCH-reasoned, shipped as hex. All pairings verified WCAG AA on their surface.

### Surfaces (neutral ladder)
| Role | Token | Dark | Light |
|------|-------|------|-------|
| Page | `--bg` | `#0b0b0d` | `#f5f5f6` |
| Card base | `--bg-1` | `#141417` | `#ffffff` |
| Raised / hover | `--bg-2` | `#1c1c20` | `#fbfbfc` |
| Chips / controls | `--bg-3` | `#26262b` | `#ebebed` |
| Recessed wells (logs) | `--bg-sunk` | `#08080a` | `#f0f0f2` |

### Ink (neutral, AA on bg AND card)
| Role | Token | Dark | Light |
|------|-------|------|-------|
| Primary | `--text-0` | `#f4f4f5` | `#161619` |
| Secondary | `--text-1` | `#c2c2c8` | `#3d3d44` |
| Tertiary / labels | `--text-2` | `#9a9aa2` | `#65656d` |
| Faint | `--text-3` | `#7a7a82` | `#7f7f88` |

> Note: small secondary text (≤10px) uses `--text-2`, not `--text-3`, to clear
> AA on card surfaces. `--text-3` is for faint/decorative use on the page bg.

### Hairlines
`--border-dim / --border / --border-hi` = white @ 6/10/18% (dark), black @
7/12/20% (light).

### Accent — ONE vivid indigo
| Token | Dark | Light | Use |
|-------|------|-------|-----|
| `--accent` | `#7c8cff` | `#4f46e5` | signal: text, icons, focus ring, data viz |
| `--accent-deep` | `#5560ee` | `#4338ca` | primary pill FILL (white text AA ≥4.5) |
| `--accent-soft` | indigo @ 14%/10% | — | soft chip fill, focus glow |
| `--accent-line` | indigo @ 40%/38% | — | accent-tinted edge |
| `--accent-fg` | `#ffffff` | on-accent text |

### Semantic status — vivid, each with base / `-bg` soft fill / `-line` edge
| State | Token | Dark | Light |
|-------|-------|------|-------|
| ok (live/done) | `--ok` | `#4ade80` | `#0d7044` |
| error (failed) | `--err` | `#f87171` | `#dc2626` |
| warn (paused) | `--warn` | `#fbbf24` | `#a16207` |
| info (starting) | `--info` | `#60a5fa` | `#2563eb` |
| route (subagent/experimental) | `--route` | `#c084fc` | `#7c3aed` |

Status is never color-alone: pills carry words, the live dot pairs with a label.

## Typography

Three families, contrast-paired (display grotesque + humanist sans + technical
mono — not three of the same axis). Loaded from Google Fonts. Token names kept
for compat (`--serif` is now the display grotesque, not a serif).

| Role | Token | Family | Use |
|------|-------|--------|-----|
| Display | `--serif` | **Bricolage Grotesque** (400–700) | headings, wordmark, big numerals |
| Body / UI | `--sans` | **Hanken Grotesk** (400–700) | body, labels, controls |
| Mono | `--mono` | **Geist Mono** (400–600) | ids, runtime chips, logs, metrics, paths |

Rules: hierarchy via scale + weight (≥1.25 step ratio); display headings use
`text-wrap: balance`; uppercase reserved for short labels/eyebrows/badges only;
no all-caps body; body line length capped ~65–75ch.

## Spacing & Radii

- **Radii (everything rounded):** `--r-sm` 10px (inputs), `--r` 16px (cards/
  panels), `--r-lg` 24px (large containers, canvases), `--r-pill` 999px
  (buttons, chips, badges, toggles). No sharp 2–4px corners.
- **Spacing:** comfortable, varied for rhythm (not a flat scale). Panels breathe;
  density is opt-in via progressive disclosure, never the default.

## Elevation

Soft, NEUTRAL, layered shadows — no colored glows except for meaning:
`--shadow-sm / -md / -lg`, plus `--shadow-accent` (focus/active accent surfaces)
and `--glow-live` (live-state ring, ok-green). `--surface-grad` is a subtle
2-stop neutral gradient for the hero tile.

## Motion

Shared, token-driven, in `motion.css`. Intentional and quiet; eased-out.
- `.rise` — entrance fade + translateY(12px→0), ~260ms ease-out.
- `.rise-stagger > *` — auto-staggered children (10 steps @ ~46ms, then settles).
- `.pulse-live` — gentle pulsing ring/dot on `--ok` for live status.
- `.bubble-in` — chat-message / toast pop-in. `.shimmer` — skeleton loading.

**Reduced motion is a hard gate:** a `@media (prefers-reduced-motion: reduce)`
block resets animation/transition/transform to none and forces opacity:1 so no
entrance leaves content invisible. Reveals enhance already-visible defaults
(never gate content visibility on a transition).

## Components

- **Buttons / chips / badges:** pill (`--r-pill`). Primary = `--accent-deep`
  fill + `--accent-fg`; secondary = neutral surface + hairline. One accent-full
  surface per view (e.g. Launch, Inject).
- **Cards / panels:** `--r`/`--r-lg`, `--bg-1` on `--bg`, hairline border, soft
  shadow, gentle hover-lift. Cards used only where they're the right affordance;
  never nested.
- **Worker card:** signature element — animated status "filament" on the top
  edge of busy cards, avatar + pulsing state dot, runtime/model chip (mono),
  quality bar, adherence pill, output well, mode controls behind disclosure.
- **Status pill:** semantic color by state (starting=info, running/done=ok,
  paused=warn, failed=err), word label always present.
- **Tabbed feed panel:** Orchestrator / Events / Subagents collapsed into one
  tabbed surface (progressive disclosure of deep logs).
- **Inputs / selects:** `--r-sm`, neutral surface, accent focus ring.
- **Toasts, stuck banner, empty/loading/error states:** all on-brand, present on
  every route.

## Layout

- SPA hash-router shell: sticky header (brand · routes · session switcher ·
  connection · pause/resume · theme) + a calmer sub-bar (project crumb + run-mode
  toggles). Dashboard `#/` = metrics band, workers grid + dock (left), right rail
  (Direct Control / Tasks / tabbed feeds). Other routes mount into a shared view
  container.
- Flexbox for 1D, Grid for 2D; responsive grids via
  `repeat(auto-fit, minmax(…, 1fr))`. Calm, airy default; depth on demand.

## Accessibility

WCAG AA throughout: body ≥4.5:1, large ≥3:1, placeholders 4.5:1 (verified, e.g.
feed timestamps moved `--text-3`→`--text-2` to clear AA). Visible accent focus
rings, full keyboard reach, status never color-alone, `prefers-reduced-motion`
honored. Dashboard binds to 127.0.0.1 only (local tool).
