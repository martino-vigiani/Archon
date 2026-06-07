/* ============================================================
   ARCHON DASHBOARD — SESSIONS VIEW (F14)  ·  UI v3 "MONO"
   Owner: vsess. File: static/js/views/sessions.js

   Multi-session management. Lists every orchestrator run from
   GET /api/sessions as calm monochrome cards: goal, status pill,
   a relative "started" time and the project path. Clicking a card
   selects that session (persists localStorage["archon.session"]
   and navigates back to the dashboard at #/). A "New run" button
   routes to #/new. Running sessions expose a Stop action that
   POSTs /api/sessions/{id}/stop. The list auto-refreshes on a
   short interval while mounted; the timer is cleared on cleanup.

   Integration contract (CONTRACT §6):
     export function mount(container, ctx) -> () => cleanup
     ctx = { sessionId, api(path), ws(path), navigate(hash) }
     ctx.api(path) === fetch('/api' + path + '?session=<id>')

   Design language: MONO — neutral surfaces, large rounded cards,
   pill status badges colored only by semantic state, airy spacing.
   ONLY var(--…) tokens from tokens.css (no hardcoded color / font /
   radius / shadow). Works in dark + light. Entrance uses the shared
   .rise / .rise-stagger classes from motion.css and honors
   prefers-reduced-motion.
============================================================ */

const STORAGE_KEY = "archon.session";
const REFRESH_MS = 4000;

/* Statuses that represent a live, stoppable run. */
const ACTIVE_STATUSES = new Set(["starting", "running", "paused"]);

/* Map a session status → the semantic tone used for its status pill.
   starting=info · running=ok · paused=warn · completed=ok ·
   failed=err · stopped=neutral. Unknowns fall back to neutral. */
const STATUS_TONE = {
  starting: "info",
  running: "ok",
  paused: "warn",
  completed: "ok",
  failed: "err",
  stopped: "neutral",
};

/* Human-friendly verbs for the status pill — kept short and calm. */
const STATUS_LABEL = {
  starting: "starting",
  running: "running",
  paused: "paused",
  completed: "completed",
  failed: "failed",
  stopped: "stopped",
};

/* ── Helpers ──────────────────────────────────────────────────── */

/** HTML-escape user/server text before interpolation. */
function escHtml(str) {
  return String(str == null ? "" : str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/** Strip ANSI/VT escape sequences from any server-originated text. */
// ESC (\x1b) introducer + optional CSI/OSC params + final byte. Escapes are
// written as \x.. so no literal control byte can be corrupted on save.
// eslint-disable-next-line no-control-regex
const ANSI_RE = /\x1b[[\]()#;?]*(?:[0-9]{1,4}(?:;[0-9]{0,4})*)?[0-9A-ORZcf-nqry=><]/g;
function stripAnsi(str) {
  return String(str == null ? "" : str).replace(ANSI_RE, "");
}

/** Clean text: strip ANSI then drop stray C0/C1 control chars. */
// eslint-disable-next-line no-control-regex
const CTRL_RE = /[\x00-\x1f\x7f-\x9f]/g;
function clean(str) {
  return stripAnsi(str).replace(CTRL_RE, "");
}

/**
 * Render an ISO-8601 timestamp as a compact relative time.
 * Returns "·" when the value is missing or unparseable so the UI
 * never shows "NaN".
 */
function relativeTime(iso) {
  if (!iso) return "·";
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return "·";
  const diff = Date.now() - then;
  if (diff < 0) return "just now";
  const sec = Math.floor(diff / 1000);
  if (sec < 45) return "just now";
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.floor(hr / 24);
  if (day < 30) return `${day}d ago`;
  const mon = Math.floor(day / 30);
  if (mon < 12) return `${mon}mo ago`;
  return `${Math.floor(mon / 12)}y ago`;
}

/** First few words of the goal, for a compact card heading. */
function goalText(goal) {
  const g = clean(goal).trim();
  return g || "(untitled run)";
}

/* ── Styles (scoped, token-driven, injected once) ─────────────── */

const STYLE_ID = "archon-sessions-style";
const STYLE = `
/* Page shell — airy, centered, with a single orchestrated entrance. */
.sessions-view {
  padding: 40px 28px 56px;
  max-width: 1120px;
  margin: 0 auto;
}

/* Header: title block + primary "New run" pill, breathing room below. */
.sessions-head {
  display: flex; align-items: flex-end; justify-content: space-between;
  gap: 20px; margin-bottom: 32px; flex-wrap: wrap;
}
.sessions-head-left { min-width: 0; }
.sessions-title {
  font-family: var(--serif);
  font-size: 30px; line-height: 1.05; font-weight: 600;
  letter-spacing: -0.01em; color: var(--text-0); margin: 0;
}
.sessions-sub {
  font-family: var(--sans); font-size: 13px; line-height: 1.5;
  color: var(--text-2); margin-top: 8px;
}

/* Primary action — accent-filled pill, the one vivid call to action. */
.sessions-new-btn {
  font-family: var(--sans); font-size: 13px; font-weight: 600;
  letter-spacing: 0.01em;
  color: var(--accent-fg); background: var(--accent);
  border: 1px solid var(--accent); border-radius: var(--r-pill, 999px);
  padding: 10px 20px; cursor: pointer; flex-shrink: 0;
  display: inline-flex; align-items: center; gap: 7px;
  transition: filter 160ms ease, transform 120ms ease, box-shadow 160ms ease;
}
.sessions-new-btn:hover { filter: brightness(1.06); box-shadow: var(--shadow-accent); }
.sessions-new-btn:active { transform: translateY(1px); }
.sessions-new-btn:focus-visible {
  outline: 2px solid var(--accent); outline-offset: 2px;
}
.sessions-new-btn .plus { font-size: 15px; line-height: 0; opacity: 0.9; }

/* Card grid — wide, generous gaps; never dense. */
.sessions-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 360px), 1fr));
  gap: 18px;
}

/* The card — large radius, neutral surface, calm hover lift. */
.session-card {
  background: var(--bg-1);
  border: 1px solid var(--border-dim);
  border-radius: var(--r-lg);
  padding: 22px 22px 18px;
  display: flex; flex-direction: column; gap: 16px;
  cursor: pointer;
  position: relative;
  box-shadow: var(--shadow-sm);
  transition: border-color 200ms ease, background 200ms ease,
              transform 160ms ease, box-shadow 200ms ease;
}
.session-card:hover {
  border-color: var(--border);
  background: var(--bg-2);
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
}
.session-card:active { transform: translateY(0); }
.session-card:focus-visible {
  outline: 2px solid var(--accent); outline-offset: 2px;
}
/* Currently-selected run gets the accent edge — quiet but unmistakable. */
.session-card.is-current {
  border-color: var(--accent-line);
  box-shadow: var(--shadow-accent);
}
.session-card.is-current::before {
  content: ''; position: absolute; left: 0; top: 18px; bottom: 18px;
  width: 3px; background: var(--accent);
  border-radius: var(--r-pill, 999px);
}

/* Top row: goal heading + status pill. */
.session-card-top {
  display: flex; align-items: flex-start; gap: 14px;
  justify-content: space-between;
}
.session-goal {
  font-family: var(--sans); font-size: 16px; line-height: 1.4;
  color: var(--text-0); font-weight: 600; letter-spacing: -0.005em;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden; min-width: 0;
}

/* Status pill — fully rounded, color carries the only signal. */
.session-pill {
  font-family: var(--mono); font-size: 10px; font-weight: 500;
  letter-spacing: 0.04em; text-transform: lowercase;
  padding: 4px 11px 4px 9px; border-radius: var(--r-pill, 999px);
  border: 1px solid var(--border); color: var(--text-2);
  background: var(--bg-3);
  display: inline-flex; align-items: center; gap: 6px;
  white-space: nowrap; flex-shrink: 0; align-self: flex-start;
}
.session-pill .dot {
  display: inline-block; width: 6px; height: 6px; border-radius: 50%;
  background: currentColor; flex-shrink: 0;
}
.session-pill.tone-ok      { color: var(--ok);   border-color: var(--ok-line);   background: var(--ok-bg); }
.session-pill.tone-err     { color: var(--err);  border-color: var(--err-line);  background: var(--err-bg); }
.session-pill.tone-warn    { color: var(--warn); border-color: var(--warn-line); background: var(--warn-bg); }
.session-pill.tone-info    { color: var(--info); border-color: var(--info-line); background: var(--info-bg); }
.session-pill.tone-neutral { color: var(--text-2); border-color: var(--border); background: var(--bg-3); }
/* Live runs: gently pulsing dot (shared keyframes if present, local fallback). */
.session-pill.is-live .dot { animation: sess-pulse-dot 1.8s ease-in-out infinite; }
@keyframes sess-pulse-dot { 0%,100% { opacity: 1; } 50% { opacity: 0.35; } }

/* Meta row: when it started + where it lives. Mono, quiet. */
.session-meta {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  font-family: var(--mono); font-size: 11px; color: var(--text-3);
  letter-spacing: 0.01em;
}
.session-meta .sep { color: var(--border-hi); }
.session-path {
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  min-width: 0; max-width: 100%;
}

/* Foot: short id on the left, Stop action on the right (live runs only). */
.session-card-foot {
  display: flex; align-items: center; gap: 10px;
  justify-content: space-between;
  padding-top: 14px; margin-top: 2px;
  border-top: 1px solid var(--border-dim);
}
.session-id {
  font-family: var(--mono); font-size: 10px; color: var(--text-3);
  letter-spacing: 0.01em;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0;
}
.session-stop-btn {
  font-family: var(--sans); font-size: 11px; font-weight: 600;
  letter-spacing: 0.01em;
  color: var(--text-2); background: transparent;
  border: 1px solid var(--border); border-radius: var(--r-pill, 999px);
  padding: 5px 14px; cursor: pointer; flex-shrink: 0;
  transition: color 150ms ease, border-color 150ms ease, background 150ms ease;
}
.session-stop-btn:hover {
  color: var(--err); border-color: var(--err-line); background: var(--err-bg);
}
.session-stop-btn:focus-visible {
  outline: 2px solid var(--accent); outline-offset: 2px;
}
.session-stop-btn:disabled { opacity: 0.5; cursor: default; }

/* Loading / empty / error — all on-brand, generous, rounded. */
.sessions-empty, .sessions-loading, .sessions-error {
  text-align: center; padding: 80px 24px;
  font-family: var(--sans); color: var(--text-2);
  border: 1px dashed var(--border); border-radius: var(--r-lg);
  background: var(--bg-1);
}
.sessions-empty .big, .sessions-error .big {
  font-family: var(--serif); font-size: 19px; font-weight: 600;
  letter-spacing: -0.005em; color: var(--text-0); margin-bottom: 8px;
}
.sessions-empty .small {
  font-size: 13px; color: var(--text-2); margin-bottom: 22px; line-height: 1.5;
}
.sessions-error .big { color: var(--err); }
.sessions-loading {
  font-family: var(--mono); font-size: 11px; letter-spacing: 0.08em;
  text-transform: uppercase; color: var(--text-3);
}

.sessions-empty-cta {
  font-family: var(--sans); font-size: 13px; font-weight: 600;
  color: var(--accent-fg); background: var(--accent);
  border: 1px solid var(--accent); border-radius: var(--r-pill, 999px);
  padding: 10px 22px; cursor: pointer;
  transition: filter 160ms ease, transform 120ms ease, box-shadow 160ms ease;
}
.sessions-empty-cta:hover { filter: brightness(1.06); box-shadow: var(--shadow-accent); }
.sessions-empty-cta:active { transform: translateY(1px); }
.sessions-retry {
  font-family: var(--sans); font-size: 13px; font-weight: 600;
  color: var(--text-0); background: transparent;
  border: 1px solid var(--border-hi); border-radius: var(--r-pill, 999px);
  padding: 10px 22px; cursor: pointer;
  transition: background 150ms ease, border-color 150ms ease;
}
.sessions-retry:hover { background: var(--fill-hover); border-color: var(--accent-line); }
.sessions-empty-cta:focus-visible, .sessions-retry:focus-visible {
  outline: 2px solid var(--accent); outline-offset: 2px;
}

/* Local entrance fallback for the page shell when motion.css's .rise
   isn't present. Disabled under reduced-motion. The shared
   .rise / .rise-stagger classes (motion.css) take over when loaded. */
@media (prefers-reduced-motion: no-preference) {
  .sessions-view.sess-fallback-in { animation: sess-view-in 280ms ease both; }
  @keyframes sess-view-in { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
}
`;

function ensureStyle(doc) {
  if (doc.getElementById(STYLE_ID)) return;
  const tag = doc.createElement("style");
  tag.id = STYLE_ID;
  tag.textContent = STYLE;
  doc.head.appendChild(tag);
}

/* ── Rendering ────────────────────────────────────────────────── */

function statusTone(status) {
  return STATUS_TONE[String(status || "").toLowerCase()] || "neutral";
}

function statusLabel(status) {
  const s = String(status || "unknown").toLowerCase();
  return STATUS_LABEL[s] || s;
}

function pillMarkup(status) {
  const s = String(status || "unknown").toLowerCase();
  const tone = statusTone(s);
  const live = ACTIVE_STATUSES.has(s) ? " is-live" : "";
  return (
    `<span class="session-pill tone-${tone}${live}">` +
    `<span class="dot"></span>${escHtml(statusLabel(s))}</span>`
  );
}

function cardMarkup(entry, currentId) {
  const id = String(entry.session_id || "");
  const status = String(entry.status || "unknown").toLowerCase();
  const isCurrent = id && id === currentId;
  const isActive = ACTIVE_STATUSES.has(status);
  const path = entry.project_path ? clean(entry.project_path) : "";
  const started = relativeTime(entry.started_at);

  const stopBtn = isActive
    ? `<button class="session-stop-btn" data-stop="${escHtml(id)}" title="Stop this run">Stop</button>`
    : "";

  return `
    <article class="session-card${isCurrent ? " is-current" : ""}"
             role="button" tabindex="0"
             data-select="${escHtml(id)}"
             aria-label="Open session ${escHtml(goalText(entry.goal))}"
             aria-current="${isCurrent ? "true" : "false"}">
      <div class="session-card-top">
        <div class="session-goal">${escHtml(goalText(entry.goal))}</div>
        ${pillMarkup(status)}
      </div>
      <div class="session-meta">
        <span class="session-started" title="${escHtml(entry.started_at || "")}">started ${escHtml(started)}</span>
        ${path ? `<span class="sep">/</span><span class="session-path" title="${escHtml(path)}">${escHtml(path)}</span>` : ""}
      </div>
      <div class="session-card-foot">
        <span class="session-id" title="${escHtml(id)}">${escHtml(id || "—")}</span>
        ${stopBtn}
      </div>
    </article>`;
}

function listMarkup(entries, currentId) {
  if (!entries.length) {
    return `
      <div class="sessions-empty rise">
        <div class="big">No runs yet</div>
        <div class="small">Launch your first orchestrator run to see it here.</div>
        <button class="sessions-empty-cta" data-new>Start a new run</button>
      </div>`;
  }
  return `<div class="sessions-list rise-stagger">${entries
    .map((e) => cardMarkup(e, currentId))
    .join("")}</div>`;
}

/* ── Mount ────────────────────────────────────────────────────── */

/**
 * Mount the sessions view.
 *
 * @param {HTMLElement} container - host element owned by the shell.
 * @param {object} ctx - { sessionId, api(path), ws(path), navigate(hash) }.
 * @returns {() => void} cleanup that stops the refresh timer.
 */
export function mount(container, ctx) {
  const doc = container.ownerDocument || document;
  ensureStyle(doc);

  const currentId =
    (ctx && ctx.sessionId) ||
    (typeof localStorage !== "undefined" && localStorage.getItem(STORAGE_KEY)) ||
    "";

  let destroyed = false;
  let timer = null;
  let inFlight = false;

  container.innerHTML = `
    <section class="sessions-view rise sess-fallback-in">
      <header class="sessions-head">
        <div class="sessions-head-left">
          <h1 class="sessions-title">Sessions</h1>
          <div class="sessions-sub">Select a run to inspect — or start a new one</div>
        </div>
        <button class="sessions-new-btn" data-new>
          <span class="plus" aria-hidden="true">+</span>New run
        </button>
      </header>
      <div class="sessions-body" aria-live="polite">
        <div class="sessions-loading">Loading sessions…</div>
      </div>
    </section>`;

  const body = container.querySelector(".sessions-body");

  function selectSession(id) {
    if (!id) return;
    try {
      localStorage.setItem(STORAGE_KEY, id);
    } catch {
      /* storage may be unavailable — selection still navigates */
    }
    if (ctx && typeof ctx.navigate === "function") {
      ctx.navigate("#/");
    } else if (typeof location !== "undefined") {
      location.hash = "#/";
    }
  }

  function goNew() {
    if (ctx && typeof ctx.navigate === "function") ctx.navigate("#/new");
    else if (typeof location !== "undefined") location.hash = "#/new";
  }

  async function stopSession(id, btn) {
    if (!id) return;
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Stopping…";
    }
    try {
      await ctx.api(`/sessions/${encodeURIComponent(id)}/stop`, { method: "POST" });
    } catch {
      if (btn) {
        btn.disabled = false;
        btn.textContent = "Stop";
      }
      return;
    }
    // Refresh promptly so the pill reflects the new state.
    refresh();
  }

  function render(entries) {
    if (destroyed) return;
    body.innerHTML = listMarkup(entries, currentId);
  }

  function renderError() {
    if (destroyed) return;
    body.innerHTML = `
      <div class="sessions-error rise">
        <div class="big">Couldn't load sessions</div>
        <button class="sessions-retry" data-retry>Retry</button>
      </div>`;
  }

  async function refresh() {
    if (destroyed || inFlight) return;
    inFlight = true;
    try {
      const res = await ctx.api("/sessions");
      const data = res && typeof res.json === "function" ? await res.json() : res;
      if (destroyed) return;
      const entries = Array.isArray(data) ? data : Array.isArray(data && data.sessions) ? data.sessions : [];
      render(entries);
    } catch {
      if (!destroyed && !body.querySelector(".sessions-list")) renderError();
    } finally {
      inFlight = false;
    }
  }

  // Single delegated click handler for the whole view.
  function onClick(ev) {
    const stopEl = ev.target.closest("[data-stop]");
    if (stopEl) {
      ev.preventDefault();
      ev.stopPropagation();
      stopSession(stopEl.getAttribute("data-stop"), stopEl);
      return;
    }
    if (ev.target.closest("[data-new]")) {
      ev.preventDefault();
      goNew();
      return;
    }
    if (ev.target.closest("[data-retry]")) {
      ev.preventDefault();
      refresh();
      return;
    }
    const card = ev.target.closest("[data-select]");
    if (card) {
      ev.preventDefault();
      selectSession(card.getAttribute("data-select"));
    }
  }

  function onKey(ev) {
    if (ev.key !== "Enter" && ev.key !== " ") return;
    const card = ev.target.closest("[data-select]");
    if (card) {
      ev.preventDefault();
      selectSession(card.getAttribute("data-select"));
    }
  }

  container.addEventListener("click", onClick);
  container.addEventListener("keydown", onKey);

  refresh();
  timer = setInterval(refresh, REFRESH_MS);

  return function cleanup() {
    destroyed = true;
    if (timer) clearInterval(timer);
    timer = null;
    container.removeEventListener("click", onClick);
    container.removeEventListener("keydown", onKey);
    container.innerHTML = "";
  };
}

export default { mount };
