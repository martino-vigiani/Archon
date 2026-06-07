// ============================================================
// ARCHON DASHBOARD — APP LOGIC / SPA SHELL
// Owned by: shell agent. Router + nav + session scoping + the live dashboard
// (render + WS + window manager + theme + metrics + stuck banner + prompt
// expander + adherence badge). The dashboard is route '#/'; the other routes
// (#/new #/sessions #/chat #/files #/workspace) are mounted from sibling view
// modules via the hash router.
// ============================================================

/* ═══════════════════════════════════════════════════════════
   ARCHON DASHBOARD — VANILLA JS, STRICT MONOCHROME
   Data-driven: no hardcoded terminal IDs anywhere.
═══════════════════════════════════════════════════════════ */

'use strict';

// ── Toast (self-contained, no external dependency) ──────────────────────────
const toastRoot = document.getElementById('toast-root');
function showToast(message, type = 'info') {
  const el = document.createElement('div');
  el.className = `toast t-${type}`;
  el.textContent = message;
  toastRoot.appendChild(el);
  requestAnimationFrame(() => {
    requestAnimationFrame(() => el.classList.add('in'));
  });
  const remove = () => {
    el.classList.replace('in', 'out');
    el.addEventListener('transitionend', () => el.remove(), { once: true });
  };
  setTimeout(remove, 3200);
  el.addEventListener('click', remove);
}

// ── Session scoping ─────────────────────────────────────────────────────────
// A "session" = one orchestrator run. localStorage["archon.session"] may be null
// → the backend defaults to the newest running session. Every fetch + the WS URL
// carry ?session=<id> when an id is set, so the whole dashboard is session-aware.
const SESSION_KEY = 'archon.session';

function readSavedSession() {
  try {
    const v = localStorage.getItem(SESSION_KEY);
    return v && v.trim() ? v.trim() : null;
  } catch { return null; }
}

// ── State ────────────────────────────────────────────────────────────────────
const state = {
  ws: null,
  wsReady: false,
  retryDelay: 1000,
  retryTimer: null,
  pollTimer: null,
  knownWorkers: new Set(),   // ids we've rendered cards for
  lastData: {},
  sessionId: readSavedSession(),   // null → newest running
  dashboardMounted: false,         // whether the live loop (WS/poll) is running
  connected: false,                // socket live? (gates the run controls)
  paused: false,                   // last-known run paused state
  runState: '',                    // last-known run state (running/idle/…)
  ctrlBusy: false                  // a pause/resume request is in flight
};

// Build the session query suffix ("" or "?session=<id>"/"&session=<id>").
function sessionQS(hasQuery = false) {
  if (!state.sessionId) return '';
  return `${hasQuery ? '&' : '?'}session=${encodeURIComponent(state.sessionId)}`;
}

// Append ?session=<id> to an /api path, merging with any existing query string.
function apiUrl(path) {
  const p = path.startsWith('/') ? path : `/${path}`;
  return `${p}${sessionQS(p.includes('?'))}`;
}

// Session-scoped fetch — the single chokepoint every dashboard request flows
// through, so adding the session param is impossible to forget.
function apiFetch(path, opts) {
  return fetch(apiUrl(path), opts);
}

// ── DOM Refs ─────────────────────────────────────────────────────────────────
const connDot    = document.getElementById('conn-dot');
const connLabel  = document.getElementById('conn-label');
const workerGrid = document.getElementById('worker-grid');
const workerCount= document.getElementById('worker-count');

// ── Persisted UI state (window manager + theme) ────────────────────────────────
// Schema:
//   localStorage["archon.theme"]  = "dark" | "light"
//   localStorage["archon.layout"] = JSON {
//     sizes:        { [workerId]: "sm"|"md"|"lg" },  // per-card size
//     docked:       [workerId, …],                   // closed → in dock
//     layout:       "grid" | "split",                // #worker-grid data-layout
//     dockCollapsed: boolean                          // #worker-dock data-collapsed
//   }
const THEME_KEY  = 'archon.theme';
const LAYOUT_KEY = 'archon.layout';
const VALID_SIZES = new Set(['sm', 'md', 'lg']);

const layoutState = {
  sizes: {},          // { id: 'sm'|'md'|'lg' }
  docked: new Set(),  // closed worker ids
  layout: 'grid',     // 'grid' | 'split'
  dockCollapsed: false
};

function loadLayoutState() {
  try {
    const raw = localStorage.getItem(LAYOUT_KEY);
    if (!raw) return;
    const obj = JSON.parse(raw);
    if (obj && typeof obj === 'object') {
      if (obj.sizes && typeof obj.sizes === 'object') {
        for (const [id, size] of Object.entries(obj.sizes)) {
          if (VALID_SIZES.has(size)) layoutState.sizes[id] = size;
        }
      }
      if (Array.isArray(obj.docked)) layoutState.docked = new Set(obj.docked.map(String));
      if (obj.layout === 'grid' || obj.layout === 'split') layoutState.layout = obj.layout;
      layoutState.dockCollapsed = !!obj.dockCollapsed;
    }
  } catch {}
}

function saveLayoutState() {
  try {
    localStorage.setItem(LAYOUT_KEY, JSON.stringify({
      sizes: layoutState.sizes,
      docked: [...layoutState.docked],
      layout: layoutState.layout,
      dockCollapsed: layoutState.dockCollapsed
    }));
  } catch {}
}

// ── Theme ──────────────────────────────────────────────────────────────────────
function applyTheme(theme) {
  const t = theme === 'light' ? 'light' : 'dark';
  document.documentElement.dataset.theme = t;
  const btn = document.getElementById('btn-theme');
  if (btn) {
    // The button shows a moon/sun glyph swapped purely by CSS on [data-theme];
    // never overwrite its innerHTML — only keep the aria-label accurate.
    btn.setAttribute('aria-label', t === 'dark' ? 'Switch to light theme' : 'Switch to dark theme');
  }
}

function initTheme() {
  let saved = 'dark';
  try { saved = localStorage.getItem(THEME_KEY) || 'dark'; } catch {}
  applyTheme(saved);
}

function toggleTheme() {
  const cur = document.documentElement.dataset.theme === 'light' ? 'light' : 'dark';
  const next = cur === 'dark' ? 'light' : 'dark';
  applyTheme(next);
  try { localStorage.setItem(THEME_KEY, next); } catch {}
}

// Apply persisted theme BEFORE first paint to avoid a flash.
initTheme();
loadLayoutState();

// ── Utilities ────────────────────────────────────────────────────────────────
function fmtQuality(v) {
  const n = parseFloat(v) || 0;
  return n.toFixed(2);
}

function fmtPct(v) {
  return `${Math.round((parseFloat(v) || 0) * 100)}%`;
}

function fmtTs(ts) {
  if (ts == null || ts === '') return '·';
  const s = String(ts).trim();
  // Already a "HH:MM" or "HH:MM:SS" string — render verbatim
  if (/^\d{1,2}:\d{2}(:\d{2})?$/.test(s)) return s;
  // ISO / epoch — try parsing
  try {
    const d = new Date(s);
    if (!isNaN(d.getTime())) {
      const hh = String(d.getHours()).padStart(2,'0');
      const mm = String(d.getMinutes()).padStart(2,'0');
      const ss = String(d.getSeconds()).padStart(2,'0');
      return `${hh}:${mm}:${ss}`;
    }
  } catch {}
  // Unparseable — show a dim placeholder, never "NaN:NaN:NaN"
  return '·';
}

function safeText(el, val) {
  const s = val == null ? '' : String(val);
  if (el.textContent !== s) el.textContent = s;
}

function safeAttr(el, attr, val) {
  const s = String(val ?? '');
  if (el.getAttribute(attr) !== s) el.setAttribute(attr, s);
}

function safeClass(el, cls, on) {
  if (on) el.classList.add(cls); else el.classList.remove(cls);
}

// ── Connection status display ─────────────────────────────────────────────────
function setConnStatus(status) {
  // .pulse-live (motion.css) breathes the dot only while connected; other
  // states (reconnecting/down) stay calm and neutral.
  connDot.className = `conn-dot ${status}${status === 'live' ? ' pulse-live' : ''}`;
  const labels = { live: 'live', reconnecting: 'reconnecting', error: 'down' };
  safeText(connLabel, labels[status] || status);
  // Run controls are only meaningful over a live socket.
  state.connected = (status === 'live');
  refreshRunControls();
}

// ── Summary strip ─────────────────────────────────────────────────────────────
function updateSummary(payload) {
  const s = payload.status || {};
  const st = (s.state || 'idle').toLowerCase();

  // State badge + hero state-dot (MONO: the dot is colour-coded by state).
  const badge = document.getElementById('sum-state');
  badge.className = `state-badge ${st}`;
  safeText(badge, st.toUpperCase());
  const stateRing = document.getElementById('sum-state-ring');
  if (stateRing) stateRing.className = `hero-ring state-${st}`;

  // Quality — drive the hidden ARIA bar (legacy) AND the MONO SVG ring.
  const qa = parseFloat(s.quality_average ?? s.flow_state?.quality_average ?? 0);
  document.getElementById('sum-q-fill').style.width = fmtPct(qa);
  safeText(document.getElementById('sum-q-val'), fmtQuality(qa));
  safeAttr(document.getElementById('sum-q-bar-aria'), 'aria-valuenow', qa);
  const qRing = document.getElementById('sum-q-ring');
  if (qRing) {
    // r=26 → circumference ≈ 163.36; offset shrinks as quality rises.
    const CIRC = 163.36;
    const frac = Math.max(0, Math.min(1, qa));
    qRing.style.strokeDashoffset = (CIRC * (1 - frac)).toFixed(1);
    // High quality leans toward the live hue for a subtle "trending up" read.
    qRing.setAttribute('stroke', frac >= 0.8 ? 'var(--ok)' : 'var(--accent)');
  }

  // Task counts
  const t = s.tasks || {};
  safeText(document.getElementById('tc-pending'),   t.pending_count   ?? 0);
  safeText(document.getElementById('tc-progress'),  t.in_progress_count ?? 0);
  safeText(document.getElementById('tc-completed'), t.completed_count ?? 0);
  safeText(document.getElementById('tc-failed'),    t.failed_count    ?? 0);

  // Flow state
  const flow = s.flow_state?.overall_flow || '';
  safeText(document.getElementById('sum-flow'), flow || '—');

  // Project
  const proj = s.project || {};
  safeText(document.getElementById('hdr-project-name'), proj.name || '—');
  safeText(document.getElementById('hdr-project-path'), proj.path || '—');

  // Paused / run state => reflect in the run controls (active + disabled).
  state.paused = !!s.paused;
  state.runState = st;
  refreshRunControls();
}

// Single source of truth for the Pause / Resume control. Reflects the real run
// state (active), and disables actions that are impossible right now: offline,
// a request in flight, or a no-op for the current state (pause while paused,
// resume while running). This is the toggle semantics a stateful control needs.
function refreshRunControls() {
  const pauseBtn  = document.getElementById('btn-pause');
  const resumeBtn = document.getElementById('btn-resume');
  if (!pauseBtn || !resumeBtn) return;
  const live = state.connected, busy = state.ctrlBusy, paused = state.paused;
  const running = state.runState === 'running';
  pauseBtn.classList.toggle('active', paused);
  resumeBtn.classList.toggle('active', !paused && running);
  pauseBtn.disabled  = !live || busy || paused;
  resumeBtn.disabled = !live || busy || !paused;
  pauseBtn.classList.toggle('pending', busy);
  resumeBtn.classList.toggle('pending', busy);
  const why = !live ? ' (disconnected)' : (busy ? ' (working…)' : '');
  pauseBtn.title  = 'Pause orchestration' + why;
  resumeBtn.title = 'Resume orchestration' + why;
}

// ── Metrics strip (live throughput / completion / elapsed) ──────────────────────
function fmtElapsed(sec) {
  const n = Math.max(0, Math.floor(parseFloat(sec) || 0));
  const h = Math.floor(n / 3600);
  const m = Math.floor((n % 3600) / 60);
  const s = n % 60;
  if (h > 0) return `${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
  return `${m}:${String(s).padStart(2,'0')}`;
}

// Metrics live at payload.metrics on the WS path; on the HTTP poll path they ride
// inside the status payload (status.metrics). Prefer the top-level block, fall back.
function metricsOf(payload) {
  const top = payload.metrics;
  if (top && typeof top === 'object' && Object.keys(top).length) return top;
  const inStatus = payload.status && payload.status.metrics;
  return (inStatus && typeof inStatus === 'object') ? inStatus : {};
}

function updateMetrics(payload) {
  const m = metricsOf(payload);
  // completion_pct is 0..100 from the backend; clamp defensively.
  const comp = Math.max(0, Math.min(100, parseFloat(m.completion_pct) || 0));
  const fill = document.getElementById('m-completion-fill');
  if (fill) fill.style.width = `${comp}%`;
  safeText(document.getElementById('m-completion-val'), `${Math.round(comp)}%`);
  const aria = document.getElementById('m-completion-aria');
  if (aria) safeAttr(aria, 'aria-valuenow', Math.round(comp));

  const tp = parseFloat(m.throughput_per_min) || 0;
  const tpEl = document.getElementById('m-throughput');
  if (tpEl) tpEl.innerHTML = `${tp.toFixed(1)}<span class="metric-unit">/min</span>`;

  safeText(document.getElementById('m-elapsed'), fmtElapsed(m.elapsed_sec));
}

// Per-worker live progress %, surfaced inside each worker card.
function perWorkerMetrics(payload) {
  const m = metricsOf(payload);
  const pw = m.per_worker;
  return (pw && typeof pw === 'object') ? pw : {};
}

// ── Stuck / needs-input banner ──────────────────────────────────────────────────
function updateStuckBanner(payload) {
  const banner = document.getElementById('stuck-banner');
  if (!banner) return;
  const status = payload.status || {};
  // Prefer top-level payload fields (F15), fall back to status.* for robustness.
  const stuck = !!(payload.stuck ?? status.stuck);
  const needs = payload.needs_input ?? status.needs_input ?? null;
  const active = stuck || (needs && (needs.question || needs.worker));

  if (!active) {
    if (!banner.hidden) banner.hidden = true;
    return;
  }
  banner.hidden = false;
  const worker = needs && needs.worker ? String(needs.worker).toUpperCase() : null;
  const q = (needs && needs.question) ? String(needs.question) : '';
  // The F15 watchdog raises a low-confidence "no progress for Ns" stall that is
  // often a false positive (a long, quiet `--print` task). Treat it more gently
  // than a real agent question: calmer tag, quieter styling, polite live region.
  const watchdog = /no progress for\s*\d+\s*s|intervene,?\s*redirect,?\s*or wait/i.test(q);
  banner.dataset.kind = watchdog ? 'watch' : 'input';
  banner.setAttribute('aria-live', watchdog ? 'polite' : 'assertive');
  const tag = banner.querySelector('.stuck-banner-tag');
  if (tag) safeText(tag, watchdog ? 'Heads up' : 'Needs input');
  const msg = watchdog
    ? (worker ? `${worker} has been quiet for a while — likely a long task. Nudge it or wait.`
              : 'An agent has been quiet for a while — likely a long task. Nudge it or wait.')
    : (q ? (worker ? `${worker}: ${q}` : q)
         : (worker ? `${worker} is stuck and waiting for direction.`
                   : 'An agent is stuck and waiting for direction.'));
  safeText(document.getElementById('stuck-msg'), msg);
  // Stash the target worker so the reply can be routed as an inject to that worker.
  banner.dataset.worker = worker ? String(needs.worker) : '';
}

// ── Worker card lifecycle ─────────────────────────────────────────────────────
function stateDotClass(st) {
  const map = {
    idle: 'wsd-idle',
    busy: 'wsd-busy',
    error: 'wsd-error',
    not_started: 'wsd-not_started'
  };
  return map[st] || 'wsd-idle';
}

function buildWorkerCard(id) {
  const article = document.createElement('article');
  // `.rise` = shared entrance animation from motion.css (staggered fade/translate-up).
  article.className = 'worker-card rise';
  article.id = `wcard-${id}`;
  article.setAttribute('role', 'listitem');
  article.setAttribute('aria-label', `Agent ${id}`);

  // Escape the worker id everywhere it enters the innerHTML template — it is
  // server-derived data (could be a dynamic w{N} id or, defensively, anything)
  // so it must never be interpolated raw. Attribute uses get escHtml(id); the
  // visible text node gets escHtml(id.toUpperCase()).
  const idEsc = escHtml(id);
  const idEscUpper = escHtml(id.toUpperCase());

  // MONO worker card: animated status "filament" on the top edge of busy
  // cards, an avatar + pulsing state dot, runtime chip, quality bar, adherence
  // pill, output well and the existing mode controls. Every data-ref the render
  // loop (updateWorkerCard) reads is preserved verbatim.
  article.innerHTML = `
    <span class="wc-filament" aria-hidden="true"></span>
    <div class="worker-card-top wc-head">
      <div class="wc-avatar" aria-hidden="true">${idEsc}<span class="worker-state-dot statedot wsd-not_started" data-ref="dot"></span></div>
      <div class="wc-titles" style="min-width:0;flex:1">
        <div class="worker-id-wrap">
          <span class="worker-id wc-id">${idEscUpper}</span>
          <span class="worker-lane-tag" data-ref="lane"></span>
          <span class="worker-state-label wc-state" data-ref="state-label">NOT STARTED</span>
        </div>
        <div class="worker-spec wc-role" data-ref="spec">—</div>
        <div class="worker-task wc-current no-task" data-ref="task">idle</div>
      </div>
      <div class="worker-card-controls wc-ctrls">
        <button class="worker-btn worker-resize" data-ref="resize" title="Cycle size" aria-label="Cycle size for ${idEsc}">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M9 3H3v6M15 21h6v-6M21 3l-7 7M3 21l7-7"/></svg>
        </button>
        <button class="worker-btn worker-close" data-ref="close" title="Dock" aria-label="Dock ${idEsc}">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M18 6L6 18M6 6l12 12"/></svg>
        </button>
      </div>
    </div>
    <div class="worker-runtime wc-runtime" data-ref="runtime">
      <span class="rt-provider" data-ref="rt-provider">—</span>
      <span class="rt-model" data-ref="rt-model">—</span>
      <span class="rt-effort" data-ref="rt-effort">—</span>
      <span class="rt-adherence" data-ref="rt-adherence" title="Output adherence to task" style="display:none"></span>
    </div>
    <div class="worker-quality wc-quality">
      <span class="q-label">Quality</span>
      <div class="q-bar" role="progressbar" aria-valuemin="0" aria-valuemax="1">
        <div class="q-bar-fill" data-ref="q-fill" style="width:0%"></div>
      </div>
      <span class="q-val" data-ref="q-val">0.00</span>
    </div>
    <div class="worker-progress" data-ref="progress-row" style="display:none">
      <span class="q-label">Progress</span>
      <div class="metric-bar" role="progressbar" aria-valuemin="0" aria-valuemax="100">
        <div class="metric-bar-fill" data-ref="prog-fill" style="width:0%"></div>
      </div>
      <span class="q-val" data-ref="prog-val">0%</span>
    </div>
    <div class="worker-subagents" data-ref="subagents-row" style="display:none"></div>
    <pre class="worker-output wc-output" data-ref="output" aria-label="Worker ${idEsc} output"></pre>
    <div class="worker-prompt">
      <button class="prompt-toggle" data-ref="prompt-toggle" aria-expanded="false" aria-label="View prompt sent to ${idEsc}">View prompt sent ▾</button>
      <div class="prompt-panel" data-ref="prompt-panel" hidden></div>
    </div>
    <div class="worker-controls">
      <span class="wc-label">EFF</span>
      <select class="wc-select" data-ref="sel-effort" aria-label="Effort for ${idEsc}">
        <option value="">inherit</option>
        <option value="low">low</option>
        <option value="medium">med</option>
        <option value="high">high</option>
        <option value="xhigh">xhi</option>
        <option value="max">max</option>
      </select>
      <span class="wc-label">MDL</span>
      <select class="wc-select" data-ref="sel-model" aria-label="Model for ${idEsc}">
        <option value="">inherit</option>
        <option value="cheap">cheap</option>
        <option value="standard">std</option>
        <option value="deep">deep</option>
      </select>
      <label class="wc-checkbox-wrap" title="Plan mode">
        <input type="checkbox" data-ref="chk-plan" aria-label="Plan mode for ${idEsc}">
        <span class="wc-label">PLAN</span>
      </label>
      <button class="wc-apply" data-worker-id="${idEsc}" aria-label="Apply mode to ${idEsc}">Apply</button>
    </div>
  `;

  // Apply button handler
  article.querySelector('[data-ref="dot"]');  // just ensure refs work
  const applyBtn = article.querySelector('.wc-apply');
  applyBtn.addEventListener('click', () => applyWorkerMode(id, article));

  // Window-manager controls
  getRef(article, 'resize').addEventListener('click', () => cycleWorkerSize(id, article));
  getRef(article, 'close').addEventListener('click', () => dockWorker(id));

  // "View prompt sent" expander — lazy-loads the captured prompt record (F8).
  getRef(article, 'prompt-toggle').addEventListener('click', () => togglePrompt(id, article));

  // Apply persisted size for this card right away (default 'md').
  applyWorkerSize(article, layoutState.sizes[id] || 'md');

  return article;
}

function getRef(card, ref) {
  return card.querySelector(`[data-ref="${ref}"]`);
}

function updateWorkerCard(id, info, output) {
  let card = document.getElementById(`wcard-${id}`);
  let isNew = false;
  if (!card) {
    card = buildWorkerCard(id);
    workerGrid.appendChild(card);
    isNew = true;
    state.knownWorkers.add(id);
    // Also add to inject target select
    syncInjectTargetSelect();
  }

  const st = (info.state || 'not_started').toLowerCase();

  // State dot
  const dot = getRef(card, 'dot');
  dot.className = `worker-state-dot ${stateDotClass(st)}`;

  // State label
  const stLabel = getRef(card, 'state-label');
  const stText = st.replace('_', ' ').toUpperCase();
  safeText(stLabel, stText);
  const stClass = st === 'error' ? 'st-error' : st === 'busy' ? 'st-busy' : '';
  stLabel.className = `worker-state-label${stClass ? ' ' + stClass : ''}`;

  // Card state class — swap only the state-* token so the base classes
  // (.worker-card and the .rise entrance from motion.css) survive each tick.
  for (const c of [...card.classList]) {
    if (c.startsWith('state-')) card.classList.remove(c);
  }
  card.classList.add('worker-card', `state-${st}`);

  // Lane tag (dynamic workers may have a lane capability)
  const laneEl = getRef(card, 'lane');
  const lane = info.lane || '';
  safeText(laneEl, lane ? lane.toUpperCase() : '');
  laneEl.style.display = lane ? '' : 'none';

  // Focus / specialization subtitle
  const spec = info.focus || info.specialization || '';
  safeText(getRef(card, 'spec'), spec || '—');

  // Task
  const taskEl = getRef(card, 'task');
  const taskText = info.current_task || null;
  safeText(taskEl, taskText || 'idle');
  taskEl.className = `worker-task${taskText ? '' : ' no-task'}`;

  // Runtime chip — ALWAYS visible. Surfaces provider + model + effort.
  // (The old standalone mode badge was removed — effort now lives only here,
  // in .rt-effort, so the top-right cluster holds just the resize/close buttons.)
  // Prefer the human-readable labels from the status payload (model_label /
  // effort_label, added by dapi); fall back gracefully to the raw fields.
  safeText(getRef(card, 'rt-provider'), info.provider || 'claude');
  const modelLabel = info.model_label || info.model || 'default';
  safeText(getRef(card, 'rt-model'), modelLabel);
  const effortLabel = info.effort_label || info.mode || 'inherit';
  safeText(getRef(card, 'rt-effort'), effortLabel);

  // Subagents chips (array of names)
  const saRow = getRef(card, 'subagents-row');
  const saList = Array.isArray(info.subagents) ? info.subagents : [];
  if (saList.length > 0) {
    saRow.style.display = '';
    const chips = saList.map(name =>
      `<span class="sa-chip">${escHtml(String(name))}</span>`
    ).join('');
    saRow.innerHTML = chips;
  } else {
    saRow.style.display = 'none';
    saRow.innerHTML = '';
  }

  // Quality
  const ql = parseFloat(info.quality_level) || 0;
  getRef(card, 'q-fill').style.width = fmtPct(ql);
  safeText(getRef(card, 'q-val'), fmtQuality(ql));

  // Adherence badge — how well the worker's output tracked its task (F11).
  const adhEl = getRef(card, 'rt-adherence');
  const adhRaw = info.adherence;
  if (adhEl) {
    if (typeof adhRaw === 'number' && !Number.isNaN(adhRaw)) {
      const pct = Math.round(Math.max(0, Math.min(1, adhRaw)) * 100);
      adhEl.style.display = '';
      safeText(adhEl, `ADH ${pct}%`);
      // 3-tier semantic coloring driven by tokens (ok / warn / err).
      const tier = adhRaw >= 0.7 ? 'ok' : adhRaw >= 0.4 ? 'warn' : 'err';
      adhEl.className = `rt-adherence adh-${tier}`;
    } else {
      adhEl.style.display = 'none';
    }
  }

  // Per-worker live progress % (from metrics.per_worker, F9).
  const progRow = getRef(card, 'progress-row');
  const pw = state.perWorker && state.perWorker[id];
  const progPct = pw ? parseFloat(pw.progress_pct) : NaN;
  if (progRow) {
    if (!Number.isNaN(progPct)) {
      const p = Math.max(0, Math.min(100, progPct));
      progRow.style.display = '';
      getRef(card, 'prog-fill').style.width = `${p}%`;
      safeText(getRef(card, 'prog-val'), `${Math.round(p)}%`);
    } else {
      progRow.style.display = 'none';
    }
  }

  // Output
  if (output != null) {
    const outEl = getRef(card, 'output');
    const tail = String(output).slice(-800);
    if (outEl.textContent !== tail) {
      outEl.textContent = tail;
      // Auto-scroll only if already at bottom
      if (outEl.scrollHeight - outEl.scrollTop < outEl.clientHeight + 40) {
        outEl.scrollTop = outEl.scrollHeight;
      }
    }
  }
}

function removeStaleWorkers(activeIds) {
  const activeSet = new Set(activeIds);
  for (const id of [...state.knownWorkers]) {
    if (!activeSet.has(id)) {
      const card = document.getElementById(`wcard-${id}`);
      if (card) card.remove();
      state.knownWorkers.delete(id);
    }
  }
}

function updateWorkerCount(n) {
  safeText(workerCount, n > 0 ? `(${n})` : '');
}

// P0 — the Workers grid must never be a blank void. With no live worker we show
// either skeletons (socket still connecting) or an instructive empty state
// (connected, simply no run) so "no run" never reads as "broken".
function renderWorkersPlaceholder(count) {
  if (!workerGrid) return;
  const empty = document.getElementById('worker-empty');
  const skel  = document.getElementById('worker-skel-wrap');
  if (count > 0) {                       // real workers present → clear placeholders
    if (empty) empty.remove();
    if (skel) skel.remove();
    return;
  }
  if (!state.connected) {                // connecting / offline → skeletons
    if (empty) empty.remove();
    if (!skel) {
      const wrap = document.createElement('div');
      wrap.id = 'worker-skel-wrap';
      wrap.style.display = 'contents';
      wrap.setAttribute('aria-hidden', 'true');
      for (let i = 0; i < 3; i++) wrap.appendChild(buildSkeletonCard());
      workerGrid.appendChild(wrap);
    }
    return;
  }
  // Connected, no workers → teach the next step.
  if (skel) skel.remove();
  if (!empty) workerGrid.appendChild(buildWorkersEmptyState());
}

function buildSkeletonCard() {
  const card = document.createElement('div');
  card.className = 'worker-skel';
  const row = document.createElement('div');
  row.className = 'sk-row';
  const avatar = document.createElement('div');
  avatar.className = 'sk sk-avatar shimmer';
  const line = document.createElement('div');
  line.className = 'sk sk-line shimmer';
  row.append(avatar, line);
  const short = document.createElement('div');
  short.className = 'sk sk-line short shimmer';
  const bar = document.createElement('div');
  bar.className = 'sk sk-bar shimmer';
  card.append(row, short, bar);
  return card;
}

function buildWorkersEmptyState() {
  const box = document.createElement('div');
  box.id = 'worker-empty';
  box.className = 'worker-empty rise';
  box.setAttribute('role', 'status');

  const ico = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  ico.setAttribute('class', 'worker-empty-ico');
  ico.setAttribute('viewBox', '0 0 24 24');
  ico.setAttribute('fill', 'none');
  ico.setAttribute('stroke', 'currentColor');
  ico.setAttribute('stroke-width', '1.6');
  ico.innerHTML = '<rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/>'
    + '<rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/>';

  const title = document.createElement('div');
  title.className = 'worker-empty-title';
  safeText(title, 'No agents running');

  const sub = document.createElement('div');
  sub.className = 'worker-empty-sub';
  safeText(sub, 'When a run is going, every agent shows up here with its model, effort, progress and live output. Start one to watch it work.');

  const cta = document.createElement('a');
  cta.className = 'worker-empty-cta';
  cta.href = '#/new';
  safeText(cta, 'Start a run →');

  box.append(ico, title, sub, cta);
  return box;
}

// ── Window manager: size / dock / split / reconcile ─────────────────────────────
const workerDock   = document.getElementById('worker-dock');
const dockChips    = document.getElementById('dock-chips');
const SIZE_CYCLE   = { md: 'lg', lg: 'sm', sm: 'md' };

function applyWorkerSize(card, size) {
  const s = VALID_SIZES.has(size) ? size : 'md';
  card.setAttribute('data-size', s);
}

function cycleWorkerSize(id, card) {
  const cur = card.getAttribute('data-size') || 'md';
  const next = SIZE_CYCLE[cur] || 'md';
  applyWorkerSize(card, next);
  layoutState.sizes[id] = next;
  saveLayoutState();
}

function dockWorker(id) {
  layoutState.docked.add(id);
  saveLayoutState();
  reconcileWindowState();
}

function restoreWorker(id) {
  layoutState.docked.delete(id);
  saveLayoutState();
  reconcileWindowState();
}

function renderDock() {
  if (!workerDock || !dockChips) return;
  // Only show chips for workers that are both docked AND actually known.
  const ids = [...layoutState.docked].filter(id => state.knownWorkers.has(id));

  // Build a set for diffing existing chips.
  const wanted = new Set(ids);
  for (const chip of [...dockChips.children]) {
    if (!wanted.has(chip.dataset.workerId)) chip.remove();
  }
  const existing = new Set([...dockChips.children].map(c => c.dataset.workerId));
  for (const id of ids) {
    if (existing.has(id)) continue;
    const chip = document.createElement('button');
    chip.className = 'dock-chip';
    chip.dataset.workerId = id;
    chip.setAttribute('aria-label', `Restore ${id}`);
    chip.title = `Restore ${id.toUpperCase()}`;
    chip.textContent = id.toUpperCase();
    chip.addEventListener('click', () => restoreWorker(id));
    dockChips.appendChild(chip);
  }

  safeAttr(workerDock, 'data-empty', ids.length === 0 ? 'true' : 'false');
  safeAttr(workerDock, 'data-collapsed', layoutState.dockCollapsed ? 'true' : 'false');
  // The toggle holds a #dock-toggle-label span (hidden when collapsed) plus an
  // arrow text node — flip only the arrow, never the label.
  const dockBtn = document.getElementById('dock-toggle');
  if (dockBtn) {
    const arrow = layoutState.dockCollapsed ? ' ›' : ' ‹';
    const last = dockBtn.lastChild;
    if (last && last.nodeType === Node.TEXT_NODE) last.textContent = arrow;
    dockBtn.setAttribute('aria-label', layoutState.dockCollapsed ? 'Expand agent dock' : 'Collapse agent dock');
  }
}

// Re-apply all persisted window state to the live DOM. Called after every render
// so the update loop never clobbers user-applied sizes / docked / layout.
function reconcileWindowState() {
  // Layout (grid vs split)
  safeAttr(workerGrid, 'data-layout', layoutState.layout);
  const layoutBtn = document.getElementById('btn-layout');
  if (layoutBtn) layoutBtn.textContent = layoutState.layout === 'grid' ? 'SPLIT' : 'GRID';

  // Per-card size + docked visibility
  for (const id of state.knownWorkers) {
    const card = document.getElementById(`wcard-${id}`);
    if (!card) continue;
    applyWorkerSize(card, layoutState.sizes[id] || 'md');
    const isDocked = layoutState.docked.has(id);
    card.setAttribute('data-docked', isDocked ? 'true' : 'false');
    card.style.display = isDocked ? 'none' : '';
  }

  renderDock();
}

// ── Apply worker mode ─────────────────────────────────────────────────────────
async function applyWorkerMode(id, card) {
  const effort = getRef(card, 'sel-effort').value;
  const model  = getRef(card, 'sel-model').value;
  const plan   = getRef(card, 'chk-plan').checked;

  const body = { target: id, plan };
  if (effort) body.effort = effort;
  if (model)  body.model_tier = model;

  try {
    const r = await apiFetch('/api/control/mode', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    if (r.ok) showToast(`Mode applied to ${id.toUpperCase()}`, 'success');
    else showToast(`Couldn't apply the mode (server returned ${r.status}).`, 'error');
  } catch (e) {
    showToast(`Couldn't reach the server: ${e.message}`, 'error');
  }
}

// ── Prompt expander (view prompt sent to a worker, F8) ──────────────────────────
async function togglePrompt(id, card) {
  const panel = getRef(card, 'prompt-panel');
  const btn = getRef(card, 'prompt-toggle');
  if (!panel || !btn) return;
  const open = panel.hidden;   // about to open if currently hidden
  if (!open) {
    panel.hidden = true;
    btn.setAttribute('aria-expanded', 'false');
    btn.textContent = 'VIEW PROMPT SENT ▾';
    return;
  }
  panel.hidden = false;
  btn.setAttribute('aria-expanded', 'true');
  btn.textContent = 'HIDE PROMPT ▴';
  await loadPrompt(id, panel);
}

async function loadPrompt(id, panel) {
  panel.innerHTML = '<div class="prompt-loading">loading…</div>';
  try {
    const r = await apiFetch(`/api/terminal-prompt/${encodeURIComponent(id)}`);
    if (!r.ok) { panel.innerHTML = `<div class="prompt-empty">no prompt (${r.status})</div>`; return; }
    const data = await r.json();
    const prompts = Array.isArray(data.prompts) ? data.prompts : [];
    if (prompts.length === 0) { panel.innerHTML = '<div class="prompt-empty">no prompt captured yet</div>'; return; }
    const rec = prompts[prompts.length - 1];   // most recent
    const meta = [
      rec.model ? `MODEL ${rec.model}` : '',
      rec.effort ? `EFFORT ${rec.effort}` : '',
      rec.permission_mode ? `MODE ${rec.permission_mode}` : '',
      rec.task_id ? `TASK ${String(rec.task_id).slice(0,8)}` : ''
    ].filter(Boolean).join('  ·  ');
    const sys = rec.system ? String(rec.system) : '';
    const body = rec.body ? String(rec.body) : '';
    panel.innerHTML = `
      ${meta ? `<div class="prompt-meta">${escHtml(meta)}</div>` : ''}
      ${sys ? `<div class="prompt-sub">SYSTEM</div><pre class="prompt-text">${escHtml(sys)}</pre>` : ''}
      <div class="prompt-sub">PROMPT</div>
      <pre class="prompt-text">${escHtml(body || '(empty)')}</pre>
    `;
  } catch (e) {
    panel.innerHTML = `<div class="prompt-empty">error: ${escHtml(e.message)}</div>`;
  }
}

// ── Inject target select sync ─────────────────────────────────────────────────
function syncInjectTargetSelect() {
  const sel = document.getElementById('inj-target');
  const existing = new Set([...sel.options].map(o => o.value));
  for (const id of state.knownWorkers) {
    if (!existing.has(id)) {
      const opt = document.createElement('option');
      opt.value = id; opt.textContent = id.toUpperCase();
      sel.appendChild(opt);
    }
  }
  // Remove stale options (keep '' = auto)
  for (const opt of [...sel.options]) {
    if (opt.value !== '' && !state.knownWorkers.has(opt.value)) opt.remove();
  }
}

// ── Inject form ───────────────────────────────────────────────────────────────
document.getElementById('inject-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const title = document.getElementById('inj-title').value.trim();
  if (!title) { showToast('Add a task title first.', 'error'); return; }

  const target = document.getElementById('inj-target').value || null;
  const effort = document.getElementById('inj-effort').value || null;
  const model  = document.getElementById('inj-model').value  || null;
  const plan   = document.getElementById('inj-plan').checked;
  const desc   = document.getElementById('inj-desc').value.trim();

  const body = { title, priority: 'high', plan };
  if (desc)   body.description = desc;
  if (target) body.target = target;
  if (effort) body.effort = effort;
  if (model)  body.model_tier = model;

  try {
    const r = await apiFetch('/api/control/inject', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    if (r.ok) {
      showToast('Task added to the queue.', 'success');
      document.getElementById('inj-title').value = '';
      document.getElementById('inj-desc').value  = '';
    } else {
      showToast(`Couldn't add the task (server returned ${r.status}).`, 'error');
    }
  } catch (e) {
    showToast(`Couldn't reach the server: ${e.message}`, 'error');
  }
});

// ── Pause / Resume ────────────────────────────────────────────────────────────
async function sendRunControl(action) {
  if (state.ctrlBusy || !state.connected) return;
  state.ctrlBusy = true; refreshRunControls();
  try {
    const r = await apiFetch(`/api/control/${action}`, { method: 'POST' });
    if (r.ok) {
      showToast(action === 'pause' ? 'Paused' : 'Resumed', 'info');
      state.paused = (action === 'pause');
    } else {
      showToast(`Couldn't ${action} the run (server returned ${r.status}). It's still ${action === 'pause' ? 'running' : 'paused'}.`, 'error');
    }
  } catch (e) {
    showToast(`Couldn't reach the server: ${e.message}`, 'error');
  } finally {
    state.ctrlBusy = false; refreshRunControls();
  }
}

document.getElementById('btn-pause').addEventListener('click', () => sendRunControl('pause'));
document.getElementById('btn-resume').addEventListener('click', () => sendRunControl('resume'));
refreshRunControls();  // start disabled until the socket reports live

// ── Keyboard shortcuts for the operator's hot loop ──────────────────────────
// p = pause/resume toggle · i = focus the inject-task title. Ignored while the
// user is typing in a field so it never eats real input.
document.addEventListener('keydown', (e) => {
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  const t = e.target;
  if (t && (t.isContentEditable ||
            /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName || ''))) return;
  if (routeDashboard && routeDashboard.hidden) return;  // dashboard route only
  const k = e.key.toLowerCase();
  if (k === 'p') {
    e.preventDefault();
    sendRunControl(state.paused ? 'resume' : 'pause');
  } else if (k === 'i') {
    const inj = document.getElementById('inj-title');
    if (inj) { e.preventDefault(); inj.focus(); }
  }
});

// ── Config toggles ────────────────────────────────────────────────────────────
async function sendConfig(key, val) {
  try {
    const r = await apiFetch('/api/control/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ [key]: val })
    });
    if (!r.ok) showToast(`Couldn't save that setting (server returned ${r.status}).`, 'error');
  } catch (e) { showToast(`Error: ${e.message}`, 'error'); }
}

document.getElementById('tog-model-tiering').addEventListener('change', (e) => {
  sendConfig('model_tiering', e.target.checked);
});
document.getElementById('tog-effort-dial').addEventListener('change', (e) => {
  sendConfig('effort_dial', e.target.checked);
});
document.getElementById('tog-dynamic-agents').addEventListener('change', (e) => {
  sendConfig('dynamic_agents', e.target.checked);
});

// Reflect the live config truth onto the header toggles (read-only mirror).
// Only writes when the payload actually carries the boolean, to avoid stomping
// a user's just-clicked state when dapi hasn't surfaced the flags yet.
function reflectConfigToggles(status) {
  const map = {
    'tog-model-tiering':  status.model_tiering,
    'tog-effort-dial':    status.effort_dial,
    'tog-dynamic-agents': status.dynamic_agents
  };
  for (const [elId, val] of Object.entries(map)) {
    if (typeof val !== 'boolean') continue;
    const el = document.getElementById(elId);
    if (el && el.checked !== val) el.checked = val;
  }
}

// ── Tasks panel ───────────────────────────────────────────────────────────────
function renderTaskList(containerId, tasks) {
  const container = document.getElementById(containerId);
  if (!tasks || tasks.length === 0) {
    container.innerHTML = '<div class="empty-state">No tasks here yet.</div>';
    return;
  }

  // Build a set of current task IDs in DOM
  const existingEls = {};
  for (const child of container.children) {
    const tid = child.dataset.taskId;
    if (tid) existingEls[tid] = child;
  }
  const incoming = new Set(tasks.map(t => String(t.id || t.title)));

  // Remove stale
  for (const [tid, el] of Object.entries(existingEls)) {
    if (!incoming.has(tid)) el.remove();
  }

  // Add or update
  for (const task of tasks) {
    const tid = String(task.id || task.title);
    let row = existingEls[tid];
    if (!row) {
      row = document.createElement('div');
      row.className = 'task-row';
      row.dataset.taskId = tid;
      row.setAttribute('role', 'listitem');
      container.appendChild(row);
    }
    const q = fmtQuality(task.quality_level);
    const cancelBtn = containerId === 'tasks-progress' && task.id
      ? `<button class="task-cancel-btn" aria-label="Cancel task ${escHtml(task.id)}" data-cancel-id="${escHtml(task.id)}">&times;</button>`
      : '';
    row.innerHTML = `
      <span class="task-id" title="${escHtml(task.id || '')}">${escHtml(String(task.id || '—').slice(0,6))}</span>
      <span class="task-title">${escHtml(task.title || '—')}</span>
      <span class="task-assignee">${escHtml(task.assigned_to || '—')}</span>
      <span class="task-quality">${q}</span>
      ${cancelBtn}
    `;
    if (cancelBtn) {
      row.querySelector('.task-cancel-btn')?.addEventListener('click', () => cancelTask(task.id));
    }
  }
}

async function cancelTask(taskId) {
  try {
    const r = await apiFetch('/api/control/cancel', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_id: taskId })
    });
    if (r.ok) showToast('Task cancelled', 'info');
    else showToast(`Couldn't cancel the task (server returned ${r.status}).`, 'error');
  } catch (e) { showToast(`Error: ${e.message}`, 'error'); }
}

// ── Log / Events feeds ────────────────────────────────────────────────────────
function renderFeed(containerId, entries, buildRow, emptyPlaceholder = '—') {
  const container = document.getElementById(containerId);
  if (!entries || entries.length === 0) {
    container.innerHTML = `<div class="empty-state">${escHtml(emptyPlaceholder)}</div>`;
    delete container.dataset.populated;
    return;
  }
  container.dataset.populated = '1';

  // Collapse consecutive identical entries into one row + a ×N badge, so a noisy
  // repeated message (e.g. a watchdog re-escalation) doesn't bury real activity.
  const collapsed = [];
  for (const entry of entries) {
    const sig = String(entry.message || entry.raw || entry.name || (entry.data ? JSON.stringify(entry.data) : JSON.stringify(entry)));
    const last = collapsed[collapsed.length - 1];
    if (last && last.sig === sig) { last.count++; last.entry = entry; }  // keep the most recent in the run
    else collapsed.push({ sig, count: 1, entry });
  }

  const fragment = document.createDocumentFragment();
  for (const c of collapsed) {
    const row = buildRow(c.entry);
    if (c.count > 1) {
      const badge = document.createElement('span');
      badge.className = 'feed-count';
      badge.textContent = `×${c.count}`;
      badge.title = `${c.count} identical entries collapsed`;
      row.appendChild(badge);
    }
    fragment.appendChild(row);
  }
  container.innerHTML = '';
  container.appendChild(fragment);
}

function buildLogRow(entry) {
  const row = document.createElement('div');
  row.className = 'feed-entry';
  const type = (entry.type || 'state').toLowerCase();
  const ts = fmtTs(entry.timestamp);
  row.innerHTML = `
    <span class="feed-ts">${ts}</span>
    <span class="feed-tag t-${type}">${type.slice(0,6).toUpperCase()}</span>
    <span class="feed-msg">${escHtml(entry.message || entry.raw || '')}</span>
  `;
  return row;
}

function eventTypeClass(type) {
  // Map common event type prefixes to CSS class suffixes
  const t = type.toLowerCase().replace(/[^a-z0-9]/g, '_');
  if (t.startsWith('task_sta'))  return 't-task_sta';
  if (t.startsWith('task_com'))  return 't-task_com';
  if (t.startsWith('task_fai'))  return 't-task_fai';
  if (t.startsWith('subagent'))  return 't-subagent';
  if (t.startsWith('intervent')) return 't-intervnt';
  if (t.startsWith('error'))     return 't-error';
  if (t.startsWith('routing'))   return 't-routing';
  if (t.startsWith('decision'))  return 't-decision';
  if (t.startsWith('info'))      return 't-info';
  return '';
}

function buildEventRow(event) {
  const row = document.createElement('div');
  row.className = 'feed-entry';
  const type = (event.type || 'event').toLowerCase();
  const cls = eventTypeClass(type);
  const ts = fmtTs(event.timestamp);
  const msg = event.message
    ? event.message
    : (event.data ? JSON.stringify(event.data) : JSON.stringify(event));
  row.innerHTML = `
    <span class="feed-ts">${ts}</span>
    <span class="feed-tag ${cls}">${type.slice(0,8).toUpperCase().replace(/_/g,'·')}</span>
    <span class="feed-msg">${escHtml(String(msg).slice(0,200))}</span>
  `;
  return row;
}

function buildSubagentRow(sa) {
  const row = document.createElement('div');
  row.className = 'subagent-row';
  row.setAttribute('role', 'listitem');
  row.innerHTML = `
    <span class="sa-ts">${fmtTs(sa.timestamp)}</span>
    <span class="sa-name">${escHtml(sa.name || '—')}</span>
    <span class="sa-via">via ${escHtml(sa.terminal || '?')}</span>
    <span class="sa-task">${escHtml(sa.task || '')}</span>
  `;
  return row;
}

function escHtml(str) {
  return String(str)
    .replace(/&/g,'&amp;')
    .replace(/</g,'&lt;')
    .replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;')
    .replace(/'/g,'&#39;');
}

// ── Full render from payload ──────────────────────────────────────────────────
function applyPayload(payload) {
  if (!payload) return;
  state.lastData = payload;

  // Summary
  updateSummary(payload);

  // Live metrics strip + stuck banner
  updateMetrics(payload);
  updateStuckBanner(payload);

  // Cache per-worker metrics so updateWorkerCard can read progress %.
  state.perWorker = perWorkerMetrics(payload);

  // Workers
  const terminals = payload.status?.terminals || {};
  const outputs   = payload.terminal_outputs || {};
  const ids = Object.keys(terminals);

  for (const id of ids) {
    updateWorkerCard(id, terminals[id] || {}, outputs[id] ?? null);
  }
  removeStaleWorkers(ids);
  updateWorkerCount(ids.length);
  renderWorkersPlaceholder(ids.length);
  syncInjectTargetSelect();

  // Reflect global toggle truth (best-effort; only when the payload carries it).
  reflectConfigToggles(payload.status || {});

  // Re-apply persisted window state so the live update never wipes it.
  reconcileWindowState();

  // Tasks
  const tasks = payload.tasks || {};
  renderTaskList('tasks-progress', tasks.in_progress || []);
  renderTaskList('tasks-pending',  tasks.pending     || []);

  // Log
  const log = payload.orchestrator_log || [];
  renderFeed('orch-log', log, buildLogRow, 'No orchestrator activity yet.');

  // Events
  const events = payload.events || [];
  renderFeed('events-feed', events, buildEventRow, 'No events yet.');

  // Subagents — always render so placeholder shows when empty
  const sas = payload.subagents || [];
  renderFeed('subagents-feed', sas, buildSubagentRow, 'No subagents invoked yet.');
}

// ── HTTP fallback poll ────────────────────────────────────────────────────────
async function fetchAll() {
  try {
    const [statusRes, tasksRes, logRes] = await Promise.all([
      apiFetch('/api/status'),
      apiFetch('/api/tasks'),
      apiFetch('/api/orchestrator-log')
    ]);

    const status = statusRes.ok ? await statusRes.json() : {};
    const tasks  = tasksRes.ok  ? await tasksRes.json()  : {};
    // /api/orchestrator-log returns {entries:[...]}, not a bare array.
    const logBody = logRes.ok ? await logRes.json() : {};
    const log = Array.isArray(logBody) ? logBody : (logBody.entries || []);

    // Fetch terminal outputs for known workers. The endpoint returns a JSON object
    // {terminal_id, role, output, ...}; take .output (NOT the raw body) so the panel
    // shows the real output, matching the WS path's plain-string shape.
    const ids = Object.keys(status.terminals || {});
    const outputFetches = ids.map(id =>
      apiFetch(`/api/terminal-output/${id}`)
        .then(r => r.ok ? r.json() : null)
        .then(j => [id, j && typeof j.output === 'string' ? j.output : ''])
        .catch(() => [id, ''])
    );
    const outputPairs = await Promise.all(outputFetches);
    const terminal_outputs = Object.fromEntries(outputPairs);

    applyPayload({ status, tasks, orchestrator_log: log, terminal_outputs, events: [], subagents: [] });
  } catch (e) {
    // Silently fail — connection indicator already shows status
  }
}

function startPoll() {
  if (state.pollTimer) return;
  state.pollTimer = setInterval(fetchAll, 5000);
  fetchAll();
}

function stopPoll() {
  if (state.pollTimer) { clearInterval(state.pollTimer); state.pollTimer = null; }
}

// ── WebSocket ─────────────────────────────────────────────────────────────────
function connectWS() {
  if (state.ws) {
    try { state.ws.close(); } catch {}
    state.ws = null;
  }

  setConnStatus('reconnecting');

  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  // Session-scope the stream: ws://host/ws?session=<id> (omitted → newest running).
  const ws = new WebSocket(`${proto}://${location.host}/ws${sessionQS(false)}`);
  state.ws = ws;

  ws.addEventListener('open', () => {
    state.wsReady = true;
    state.retryDelay = 1000;
    setConnStatus('live');
    stopPoll();
  });

  ws.addEventListener('message', (evt) => {
    try {
      const msg = JSON.parse(evt.data);
      if (msg.type === 'update' || msg.status) {
        applyPayload(msg);
      }
    } catch {}
  });

  ws.addEventListener('close', () => {
    state.wsReady = false;
    setConnStatus('reconnecting');
    startPoll();
    scheduleReconnect();
  });

  ws.addEventListener('error', () => {
    state.wsReady = false;
    setConnStatus('error');
    startPoll();
  });
}

function scheduleReconnect() {
  if (state.retryTimer) return;
  state.retryTimer = setTimeout(() => {
    state.retryTimer = null;
    // Exponential backoff, cap 30s
    state.retryDelay = Math.min(state.retryDelay * 1.6, 30000);
    connectWS();
  }, state.retryDelay);
}

// ── Live-loop lifecycle (WS + poll) ─────────────────────────────────────────────
// Tear down the WS + poll cleanly. Used on session change and on dashboard unmount.
function stopLiveLoop() {
  if (state.retryTimer) { clearTimeout(state.retryTimer); state.retryTimer = null; }
  stopPoll();
  if (state.ws) {
    try {
      // Drop reconnect handlers first so an intentional close doesn't trigger one.
      state.ws.onclose = null;
      state.ws.onerror = null;
      state.ws.close();
    } catch {}
    state.ws = null;
  }
  state.wsReady = false;
}

function startLiveLoop() {
  state.retryDelay = 1000;
  connectWS();
  // Kick off a first poll immediately so the UI isn't blank while WS connects.
  fetchAll();
}

// Drop all rendered worker cards + cached payload so a session switch doesn't
// leave stale workers from the previous session on screen.
function clearWorkerCards() {
  for (const id of [...state.knownWorkers]) {
    const card = document.getElementById(`wcard-${id}`);
    if (card) card.remove();
    state.knownWorkers.delete(id);
  }
  syncInjectTargetSelect();
  state.lastData = {};
  state.perWorker = {};
}

// Re-point the UI at a new session.
//  - Dashboard route ('#/'): rebuild the worker set + restart the live loop.
//  - A non-dashboard view route (#/chat, #/files, …): re-mount the view with
//    fresh ctx so it re-scopes (e.g. chat picks up the new chatSessionId/offset)
//    instead of keeping the previous session's state.
// When no view is mounted and the dashboard is off, there's nothing live to
// re-scope (the next mount reads the current sessionId anyway).
function reconnectForSession() {
  clearWorkerCards();
  if (state.dashboardMounted) {
    stopLiveLoop();
    startLiveLoop();
  } else if (activeView.hash && typeof activeView.remount === 'function') {
    activeView.remount();
  }
}

// ── Session switcher ─────────────────────────────────────────────────────────────
function setSession(id) {
  const next = id && String(id).trim() ? String(id).trim() : null;
  if (next === state.sessionId) return;
  state.sessionId = next;
  try {
    if (next) localStorage.setItem(SESSION_KEY, next);
    else localStorage.removeItem(SESSION_KEY);
  } catch {}
  reconnectForSession();
}

const sessionSelect = document.getElementById('session-select');

// Re-read the persisted session from localStorage and adopt it if it changed.
// Other views (e.g. the Sessions view) set localStorage["archon.session"] then
// navigate to '#/'; this lets the dashboard pick up that selection on mount.
function syncSessionFromStorage() {
  const saved = readSavedSession();
  if (saved !== state.sessionId) {
    state.sessionId = saved;
    if (sessionSelect) sessionSelect.value = saved || '';
    return true;
  }
  return false;
}

// Populate the switcher from /api/sessions. Shows "goal · status" per session.
async function refreshSessions() {
  if (!sessionSelect) return;
  let list = [];
  try {
    const r = await fetch('/api/sessions');   // registry is global, not scoped
    if (r.ok) {
      const data = await r.json();
      if (Array.isArray(data)) list = data;
    }
  } catch {}

  const cur = state.sessionId || '';
  const frag = document.createDocumentFragment();
  const def = document.createElement('option');
  def.value = '';
  def.textContent = 'newest running';
  frag.appendChild(def);

  let curStillExists = false;
  for (const s of list) {
    const sid = s.session_id || s.id;
    if (!sid) continue;
    if (sid === cur) curStillExists = true;
    const opt = document.createElement('option');
    opt.value = sid;
    const goal = (s.goal || sid).toString();
    const short = goal.length > 40 ? goal.slice(0, 39) + '…' : goal;
    const st = (s.status || '').toString();
    opt.textContent = st ? `${short} · ${st}` : short;
    frag.appendChild(opt);
  }
  sessionSelect.innerHTML = '';
  sessionSelect.appendChild(frag);
  // Keep the current selection if it's still a known session; else fall back to default.
  sessionSelect.value = (cur && curStillExists) ? cur : '';
}

sessionSelect?.addEventListener('change', (e) => setSession(e.target.value));

// ── Stuck-banner reply ───────────────────────────────────────────────────────────
// Route the reply to the stalled worker as a high-priority inject (text → task).
document.getElementById('stuck-form')?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const input = document.getElementById('stuck-input');
  const text = input ? input.value.trim() : '';
  if (!text) return;
  const banner = document.getElementById('stuck-banner');
  const target = banner && banner.dataset.worker ? banner.dataset.worker : null;
  const body = { title: text, priority: 'high' };
  if (target) body.target = target;
  try {
    const r = await apiFetch('/api/control/inject', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    if (r.ok) { showToast('Reply sent', 'success'); if (input) input.value = ''; }
    else showToast(`Couldn't send your reply (server returned ${r.status}).`, 'error');
  } catch (err) { showToast(`Couldn't reach the server: ${err.message}`, 'error'); }
});

// ── Window-manager controls (header + section) ──────────────────────────────────
document.getElementById('btn-theme')?.addEventListener('click', toggleTheme);

document.getElementById('btn-layout')?.addEventListener('click', () => {
  layoutState.layout = layoutState.layout === 'grid' ? 'split' : 'grid';
  saveLayoutState();
  reconcileWindowState();
});

document.getElementById('dock-toggle')?.addEventListener('click', () => {
  layoutState.dockCollapsed = !layoutState.dockCollapsed;
  saveLayoutState();
  renderDock();
});

// ── Feed tabs (MONO: 3 stacked feeds collapsed into one tabbed panel) ───────
// Each tab's data-feed names the id of the feed container it reveals. The render
// loop keeps populating ALL three feeds (orch-log / events-feed / subagents-feed);
// only one is visible at a time. Pure view toggle — no render logic touched.
function initFeedTabs() {
  const tabs = [...document.querySelectorAll('.feed-tab')];
  if (!tabs.length) return;
  function activate(targetId, focus = false) {
    for (const tab of tabs) {
      const on = tab.dataset.feed === targetId;
      tab.classList.toggle('active', on);
      tab.setAttribute('aria-selected', on ? 'true' : 'false');
      tab.tabIndex = on ? 0 : -1;            // roving tabindex (real tablist)
      const panel = document.getElementById(tab.dataset.feed);
      if (panel) panel.hidden = !on;
    }
    if (focus) {
      const sel = tabs.find((t) => t.dataset.feed === targetId);
      if (sel) sel.focus();
    }
  }
  tabs.forEach((tab, i) => {
    tab.addEventListener('click', () => activate(tab.dataset.feed));
    tab.addEventListener('keydown', (e) => {
      let j = null;
      if (e.key === 'ArrowRight' || e.key === 'ArrowDown') j = (i + 1) % tabs.length;
      else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') j = (i - 1 + tabs.length) % tabs.length;
      else if (e.key === 'Home') j = 0;
      else if (e.key === 'End') j = tabs.length - 1;
      if (j !== null) { e.preventDefault(); activate(tabs[j].dataset.feed, true); }
    });
  });
  // Default to the first tab's feed (Orchestrator).
  activate(tabs[0].dataset.feed);
}
initFeedTabs();

// ═══════════════════════════════════════════════════════════════════════════════
//  ROUTER SHELL
//  '#/' = the live dashboard (this file); other routes mount sibling view modules.
// ═══════════════════════════════════════════════════════════════════════════════
const routeDashboard = document.getElementById('route-dashboard');
const viewContainer  = document.getElementById('view');
const navLinks       = [...document.querySelectorAll('#route-nav .nav-link')];

// Tracks the currently-mounted NON-dashboard view route so a session change can
// re-scope it. A view's ctx exposes sessionId via a live getter, but the view
// already captured the OLD sessionId in its internal state (chatSessionId,
// fetch offsets, …) at mount time — so we must fully re-mount (cleanup + mount)
// to pick up the new session, mirroring what a fresh navigation would do.
const activeView = {
  hash: null,        // e.g. '#/chat' — null when the dashboard route is active
  remount: null      // () => void : tears down + re-mounts this view with fresh ctx
};

// Context handed to every view module (CONTRACT §11).
const ctx = {
  get sessionId() { return state.sessionId; },
  // Session-scoped, /api-prefixed fetch. `path` may be with or without a leading
  // '/api' — we normalise so callers can pass '/sessions' or '/api/sessions'.
  api(path, opts) {
    let p = String(path || '');
    if (!p.startsWith('/')) p = '/' + p;
    if (!p.startsWith('/api/') && p !== '/api') p = '/api' + p;
    return apiFetch(p, opts);
  },
  // Session-scoped WebSocket for a given ws path (e.g. '/ws').
  ws(path) {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    let p = String(path || '/ws');
    if (!p.startsWith('/')) p = '/' + p;
    return new WebSocket(`${proto}://${location.host}${p}${sessionQS(p.includes('?'))}`);
  },
  navigate: (hash) => { location.hash = hash; }
};

// Dashboard mount/unmount fns registered as the '#/' route.
// The dashboard markup lives in the persistent #route-dashboard element (not in
// the router's shared #view container), so this mount fn just toggles visibility
// and drives the live loop. The passed container (#view) is hidden while active.
function mountDashboard(/* container, ctx */) {
  // The dashboard route ('#/') is the live loop, not a view module — clear any
  // active-view tracking so session changes drive the loop, not a re-mount.
  activeView.hash = null;
  activeView.remount = null;
  if (viewContainer) viewContainer.hidden = true;
  if (routeDashboard) routeDashboard.hidden = false;
  // Adopt a session another view may have selected before navigating here.
  const sessionChanged = syncSessionFromStorage();
  if (!state.dashboardMounted) {
    state.dashboardMounted = true;
    reconcileWindowState();
    if (sessionChanged) clearWorkerCards();   // drop stale cards before the loop
    startLiveLoop();
    refreshSessions();   // refresh the switcher options + selection
  } else if (sessionChanged) {
    reconnectForSession();
    refreshSessions();
  }
  return () => {
    if (routeDashboard) routeDashboard.hidden = true;
    state.dashboardMounted = false;
    stopLiveLoop();
  };
}

// Fallback mount for a sibling view module that hasn't landed yet (parallel build).
function mountPlaceholder(label) {
  return (container) => {
    container.innerHTML = `
      <section class="route-empty">
        <div class="route-empty-tag">${escHtml(label.toUpperCase())}</div>
        <div class="route-empty-msg">This view is not available yet.</div>
      </section>`;
    return () => { container.innerHTML = ''; };
  };
}

// Sync the nav active state to the current hash.
function syncNavActive(hash) {
  const h = hash || '#/';
  for (const a of navLinks) {
    const on = a.dataset.route === h;
    a.classList.toggle('active', on);
    if (on) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
  }
}

// The set of non-dashboard routes → their view module path.
const VIEW_ROUTES = [
  ['#/new',       './views/new-run.js'],
  ['#/sessions',  './views/sessions.js'],
  ['#/chat',      './views/chat.js'],
  ['#/files',     './views/files.js'],
  ['#/workspace', './views/workspace.js']
];

// Load a view module's mount fn, falling back to a placeholder if missing.
async function loadViewMount(path, label) {
  try {
    const mod = await import(path);
    if (mod && typeof mod.mount === 'function') return mod.mount;
  } catch {}
  return mountPlaceholder(label);
}

// A SYNCHRONOUS route wrapper for a lazily-imported view module.
//
// The router stores cleanup only when mountFn returns a function *synchronously*
// (an async mountFn would return a Promise and its cleanup would be lost). So we
// toggle chrome synchronously, return a sync cleanup, and mount the imported view
// asynchronously — guarding against a cancel that lands before the import resolves.
function makeViewRoute(path, label) {
  const hash = `#/${label}`;
  return (container, viewCtx) => {
    // Show the view container, hide the dashboard, and stop the live loop.
    if (routeDashboard) routeDashboard.hidden = true;
    state.dashboardMounted = false;
    stopLiveLoop();
    if (viewContainer) viewContainer.hidden = false;

    let cancelled = false;
    let viewCleanup = null;

    // Mount (or re-mount) the view's body into the container. Tears down any
    // previously-mounted instance first so a re-mount picks up fresh ctx.
    function mountBody() {
      if (typeof viewCleanup === 'function') { try { viewCleanup(); } catch {} }
      viewCleanup = null;
      container.innerHTML = '<div class="route-empty"><div class="route-empty-msg">loading…</div></div>';
      loadViewMount(path, label).then((mount) => {
        if (cancelled) return;
        container.innerHTML = '';
        try {
          const ret = mount(container, viewCtx);
          if (typeof ret === 'function') viewCleanup = ret;
        } catch (e) {
          container.innerHTML = `<div class="route-empty"><div class="route-empty-msg">view error: ${escHtml(e.message)}</div></div>`;
        }
      });
    }

    mountBody();

    // Record this as the active view so a session change can re-scope it
    // (re-mount with fresh ctx → the view re-reads ctx.sessionId).
    activeView.hash = hash;
    activeView.remount = () => { if (!cancelled) mountBody(); };

    // Sync cleanup the router can store: cancels a pending mount + tears down a
    // mounted view, then clears the container.
    return () => {
      cancelled = true;
      if (activeView.hash === hash) { activeView.hash = null; activeView.remount = null; }
      if (typeof viewCleanup === 'function') { try { viewCleanup(); } catch {} }
      viewCleanup = null;
      if (container) container.innerHTML = '';
      if (viewContainer) viewContainer.hidden = true;
    };
  };
}

// Bootstrap the router. Sibling modules (router.js + views/*.js) are imported
// dynamically with graceful fallback so the dashboard still works even if a
// sibling owner hasn't delivered their file yet.
async function bootstrap() {
  await refreshSessions();
  // Refresh the session list periodically so newly spawned runs appear.
  setInterval(refreshSessions, 15000);

  let router = null;
  try {
    router = await import('./router.js');
  } catch {
    router = null;
  }

  // Keep nav active-state in sync independent of which router drives navigation.
  window.addEventListener('hashchange', () => syncNavActive(location.hash || '#/'));

  if (router && typeof router.registerRoute === 'function' && typeof router.start === 'function') {
    // Real router: it passes a single shared container + ctx to every mountFn.
    // The dashboard route shows #route-dashboard (its DOM is persistent); view
    // routes render into the shared #view container.
    router.registerRoute('#/', (container, c) => mountDashboard(container, c));
    for (const [hash, path] of VIEW_ROUTES) {
      const label = hash.replace('#/', '') || 'dashboard';
      router.registerRoute(hash, makeViewRoute(path, label));
    }
    syncNavActive(location.hash || '#/');
    router.start({ container: viewContainer, ctx, fallback: '#/' });
  } else {
    // No router.js — drive a minimal hash router inline so routing still works.
    inlineRouter();
  }
}

// Minimal self-contained hash router used only as a fallback if router.js is
// absent. Mirrors the real router's behaviour (sync mount + cleanup contract).
function inlineRouter() {
  const routeMap = new Map(VIEW_ROUTES.map(([h, p]) => [h, makeViewRoute(p, h.replace('#/', ''))]));
  let cleanup = null;
  let current = null;

  function render() {
    let hash = location.hash || '#/';
    if (hash !== '#/' && !routeMap.has(hash)) { location.hash = '#/'; return; }
    if (current === hash) return;
    if (typeof cleanup === 'function') { try { cleanup(); } catch {} }
    cleanup = null;
    current = hash;
    syncNavActive(hash);
    const mountFn = hash === '#/' ? mountDashboard : routeMap.get(hash);
    const ret = mountFn(viewContainer, ctx);
    if (typeof ret === 'function') cleanup = ret;
  }

  window.addEventListener('hashchange', render);
  if (!location.hash) location.hash = '#/';
  render();
}

// Expose navigate for any inline consumers / debugging parity with ctx.navigate.
function navigate(hash) { location.hash = hash; }

// Kick everything off.
bootstrap();
