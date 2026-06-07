/* ============================================================
   ARCHON — NEW RUN VIEW  (OWNER: vnew)         look: UI v3 "MONO"
   Routes: #/new   Features: F1 / F1a / F3 / F5

   Launches an orchestrator run from the UI:
     - goal textarea
     - working-directory PICKER (browses via ctx.api('/dirs?path='))
     - execution toggles (dynamic agents, model tiering, effort dial, no testing)
     - agent-count input (1–10)
     - how-to instructions textarea
     - "Preview agents" → ctx.api('/preview-roster?…') → editable
       MODEL / EFFORT / plan cards collected into roster_overrides
     - "Launch" → POST /api/runs → on success ctx.navigate('#/')

   Integration contract (CONTRACT §6 / §11):
     export function mount(container, ctx) { …; return () => cleanup }
     ctx = { sessionId, api(path), ws(path), navigate(hash) }

   Look: MONO — monochrome neutral surfaces, ONE vivid accent reserved
   for the primary "Launch" action and meaningful state. Pill buttons &
   chips (--r-pill); large rounded cards (--r / --r-lg); airy spacing;
   progressive disclosure (advanced options grouped behind an expander).
   Type: Bricolage (--serif) headings, Hanken Grotesk (--sans) body,
   Geist Mono (--mono) for ids / paths / runtime tokens.

   Vanilla ES module, dependency-free. Tokens-only styling
   (var(--…) from tokens.css). Dark + light safe. ANSI stripped,
   all user/server text escaped. Entrance via shared .rise/.rise-stagger
   (motion.css); honors prefers-reduced-motion.
============================================================ */

// ── Model / effort option vocabularies (mirror execution.py enums) ──
const MODEL_TIERS = [
  ["inherit", "inherit"],
  ["cheap", "cheap · haiku"],
  ["standard", "standard · sonnet"],
  ["deep", "deep · opus"],
];
const EFFORTS = [
  ["inherit", "inherit"],
  ["low", "low"],
  ["medium", "medium"],
  ["high", "high"],
  ["xhigh", "xhigh"],
  ["max", "max"],
];

// ── Text safety ─────────────────────────────────────────────
const ANSI_RE = /[][[\]()#;?]*(?:(?:\d{1,4}(?:;\d{0,4})*)?[A-PR-TZcf-nq-uy=><~]|[0-9A-PRZcf-nqry=><])/g;
function stripAnsi(s) {
  return typeof s === "string" ? s.replace(ANSI_RE, "") : "";
}
function esc(s) {
  return stripAnsi(s == null ? "" : String(s)).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[c]);
}

// ── DOM helper ──────────────────────────────────────────────
function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k === "html") node.innerHTML = v;
    else if (k.startsWith("on") && typeof v === "function") {
      node.addEventListener(k.slice(2).toLowerCase(), v);
    } else if (k === "style" && typeof v === "object") {
      Object.assign(node.style, v);
    } else {
      node.setAttribute(k, v);
    }
  }
  for (const child of [].concat(children)) {
    if (child == null) continue;
    node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
  }
  return node;
}

/**
 * Mount the New-Run view.
 * @param {HTMLElement} container
 * @param {{sessionId?:string, api:(p:string,o?:object)=>Promise<Response>, ws?:Function, navigate:(h:string)=>void}} ctx
 * @returns {() => void} cleanup
 */
export function mount(container, ctx) {
  const api = ctx && typeof ctx.api === "function" ? ctx.api : () => Promise.reject(new Error("no api"));
  const navigate = ctx && typeof ctx.navigate === "function" ? ctx.navigate : () => {};

  // ── inject scoped styles once (kept here so the view is self-contained) ──
  injectStyles();

  // ── view state ──
  const state = {
    cwd: "",
    rosterOverrides: {}, // keyed by agent id → {model_tier, effort, permission_mode}
    dirBusy: false,
    previewBusy: false,
    launchBusy: false,
  };
  let aborted = false;
  const controllers = new Set();

  // safe fetch wrapper that tracks abort and parses JSON
  async function call(path, opts) {
    const ac = new AbortController();
    controllers.add(ac);
    try {
      const res = await api(path, { ...(opts || {}), signal: ac.signal });
      const ct = (res.headers && res.headers.get && res.headers.get("content-type")) || "";
      let body = null;
      if (ct.includes("application/json")) body = await res.json().catch(() => null);
      else body = await res.text().catch(() => null);
      if (!res.ok) {
        const msg =
          body && typeof body === "object" && (body.detail || body.error || body.message)
            ? body.detail || body.error || body.message
            : typeof body === "string" && body
            ? body
            : `HTTP ${res.status}`;
        const e = new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
        e.status = res.status;
        throw e;
      }
      return body;
    } finally {
      controllers.delete(ac);
    }
  }

  // ─────────────────────────────────────────────────────────
  //  ROOT SCAFFOLD
  // ─────────────────────────────────────────────────────────
  const root = el("section", { class: "nr-view", "aria-label": "Launch a new run" });

  // header — display heading + calm subtitle, first to rise
  root.appendChild(
    el("header", { class: "nr-header rise" }, [
      el("h1", { class: "nr-title", text: "New Run" }),
      el("p", {
        class: "nr-sub",
        text: "Describe a goal, pick a working directory, shape the roster, then launch an orchestrator.",
      }),
    ]),
  );

  // The form children are staggered on mount via .rise-stagger.
  const form = el("form", { class: "nr-form rise-stagger", autocomplete: "off" });
  form.addEventListener("submit", (e) => e.preventDefault());
  root.appendChild(form);

  // ── ESSENTIALS CARD: goal + working directory (the two things you must set) ──
  const goalInput = el("textarea", {
    class: "nr-textarea",
    id: "nr-goal",
    rows: "3",
    placeholder: "e.g. Build a REST API for a habit-tracking app with auth and a Postgres schema.",
    "aria-label": "Goal",
  });

  const dirPicker = buildDirPicker();

  const essentialsCard = el("div", { class: "nr-card-lg" }, [
    field("Goal", "What should the team build?", goalInput, true),
    field("Working directory", "Where the run executes (browse and pick a folder).", dirPicker.node),
  ]);
  form.appendChild(essentialsCard);

  // ── ROSTER CARD: the agents that will do the work ──
  const previewBtn = el("button", {
    type: "button",
    class: "nr-btn nr-btn-ghost",
    text: "Preview agents",
    onClick: onPreview,
  });
  const rosterPanel = el("div", { class: "nr-roster", "aria-live": "polite" });
  const rosterCard = el("div", { class: "nr-card-lg" }, [
    el("div", { class: "nr-card-hdr" }, [
      el("div", { class: "nr-card-hdr-text" }, [
        el("span", { class: "nr-card-hdr-title", text: "Roster" }),
        el("span", { class: "nr-card-hdr-hint", text: "Preview the proposed agents, then fine-tune each one." }),
      ]),
      previewBtn,
    ]),
    rosterPanel,
  ]);
  form.appendChild(rosterCard);

  // ── ADVANCED (progressive disclosure): execution modes + count + instructions ──
  const toggles = {
    dynamic_agents: makeToggle("dynamic-agents", "Dynamic agents", "Derive a task-shaped roster (w1…wN).", true),
    model_tiering: makeToggle("model-tiering", "Model tiering", "Per-task cheap/standard/deep model.", false),
    effort_dial: makeToggle("effort-dial", "Effort dial", "Per-task reasoning effort.", true),
    no_testing: makeToggle("no-testing", "No testing", "Skip the QA / testing agent.", false),
  };
  const togglesWrap = el("div", { class: "nr-toggles" }, [
    toggles.dynamic_agents.node,
    toggles.model_tiering.node,
    toggles.effort_dial.node,
    toggles.no_testing.node,
  ]);

  const countInput = el("input", {
    class: "nr-number",
    id: "nr-count",
    type: "number",
    min: "1",
    max: "10",
    step: "1",
    value: "5",
    "aria-label": "Agent count",
  });
  const countWrap = el("div", { class: "nr-count-wrap" }, [
    el("button", { type: "button", class: "nr-step", "aria-label": "Decrease", text: "−", onClick: () => stepCount(-1) }),
    countInput,
    el("button", { type: "button", class: "nr-step", "aria-label": "Increase", text: "+", onClick: () => stepCount(1) }),
  ]);
  function stepCount(d) {
    const n = clampCount(parseInt(countInput.value, 10) + d);
    countInput.value = String(n);
  }
  function clampCount(n) {
    if (!Number.isFinite(n)) return 5;
    return Math.max(1, Math.min(10, Math.round(n)));
  }
  countInput.addEventListener("change", () => {
    countInput.value = String(clampCount(parseInt(countInput.value, 10)));
  });

  const instrInput = el("textarea", {
    class: "nr-textarea",
    id: "nr-instructions",
    rows: "3",
    placeholder: "Optional. e.g. Prefer TypeScript strict mode. Keep commits small. Don't touch CI config.",
    "aria-label": "How-to instructions",
  });

  const advancedBody = el("div", { class: "nr-adv-body", id: "nr-advanced-body" }, [
    field("Execution modes", "Toggle the per-run switches.", togglesWrap),
    field("Agent count", "How many agents (1–10).", countWrap),
    field(
      "How-to instructions",
      "Extra guidance appended to every agent's system prompt.",
      instrInput,
    ),
  ]);
  const advCaret = el("span", { class: "nr-adv-caret", "aria-hidden": "true", text: "▸" });
  const advToggle = el(
    "button",
    {
      type: "button",
      class: "nr-adv-toggle",
      "aria-expanded": "false",
      "aria-controls": "nr-advanced-body",
      onClick: toggleAdvanced,
    },
    [
      advCaret,
      el("span", { class: "nr-adv-toggle-text" }, [
        el("span", { class: "nr-adv-toggle-title", text: "Advanced options" }),
        el("span", { class: "nr-adv-toggle-hint", text: "Execution modes, agent count, instructions" }),
      ]),
    ],
  );
  const advancedCard = el("div", { class: "nr-card-lg nr-adv", "data-open": "false" }, [advToggle, advancedBody]);
  function toggleAdvanced() {
    const open = advancedCard.getAttribute("data-open") === "true";
    const next = !open;
    advancedCard.setAttribute("data-open", String(next));
    advToggle.setAttribute("aria-expanded", String(next));
  }
  form.appendChild(advancedCard);

  // ── ACTIONS (sticky-feeling footer bar inside the form) ──
  const errBox = el("div", { class: "nr-error", role: "alert", hidden: true });
  const okBox = el("div", { class: "nr-ok", role: "status", hidden: true });
  const launchBtn = el("button", {
    type: "submit",
    class: "nr-btn nr-btn-primary",
    onClick: onLaunch,
  }, [
    el("span", { class: "nr-btn-label", text: "Launch" }),
    el("span", { class: "nr-btn-arrow", "aria-hidden": "true", text: "→" }),
  ]);
  form.appendChild(
    el("div", { class: "nr-actions" }, [
      el("div", { class: "nr-actions-msgs" }, [errBox, okBox]),
      launchBtn,
    ]),
  );

  container.appendChild(root);

  // init dir picker at session/home root
  browseDir("");

  // ─────────────────────────────────────────────────────────
  //  FIELD / WIDGET BUILDERS
  // ─────────────────────────────────────────────────────────
  function field(label, hint, control, required) {
    return el("div", { class: "nr-field" }, [
      el("div", { class: "nr-label-row" }, [
        el("label", { class: "nr-label" }, [label, required ? el("span", { class: "nr-req", text: " *" }) : null]),
        hint ? el("span", { class: "nr-hint", text: hint }) : null,
      ]),
      control,
    ]);
  }

  function makeToggle(id, label, hint, checked) {
    const input = el("input", { type: "checkbox", id: `nr-tg-${id}`, checked: checked ? "checked" : null });
    if (checked) input.checked = true;
    const node = el("label", { class: "nr-toggle", for: `nr-tg-${id}`, title: hint }, [
      input,
      el("span", { class: "nr-toggle-track" }),
      el("span", { class: "nr-toggle-label", text: label }),
    ]);
    return { node, get: () => input.checked, input };
  }

  // ── DIR PICKER ──
  function buildDirPicker() {
    const pathLabel = el("div", { class: "nr-dir-path mono", text: "—" });
    const list = el("div", { class: "nr-dir-list" });
    const useBtn = el("button", {
      type: "button",
      class: "nr-btn nr-btn-ghost nr-use-dir",
      text: "Use this directory",
      onClick: () => {
        // already current; just acknowledge with a brief accent flash
        pathLabel.classList.add("nr-dir-picked");
        setTimeout(() => pathLabel.classList.remove("nr-dir-picked"), 700);
      },
    });
    const node = el("div", { class: "nr-dir" }, [
      el("div", { class: "nr-dir-bar" }, [
        el("span", { class: "nr-dir-bar-ic", "aria-hidden": "true", text: "◇" }),
        pathLabel,
        useBtn,
      ]),
      list,
    ]);
    return { node, pathLabel, list, useBtn };
  }

  async function browseDir(path) {
    if (state.dirBusy) return;
    state.dirBusy = true;
    dirPicker.list.innerHTML = "";
    dirPicker.list.appendChild(el("div", { class: "nr-dir-loading", text: "Loading…" }));
    try {
      const data = await call(`/dirs?path=${encodeURIComponent(path || "")}`);
      if (aborted) return;
      renderDir(data || {});
    } catch (e) {
      if (aborted) return;
      dirPicker.list.innerHTML = "";
      dirPicker.list.appendChild(
        el("div", { class: "nr-dir-error", text: `Could not browse: ${esc(e.message)}` }),
      );
    } finally {
      state.dirBusy = false;
    }
  }

  function renderDir(data) {
    const cur = data.path || "";
    state.cwd = cur;
    dirPicker.pathLabel.textContent = cur || "(root)";
    dirPicker.pathLabel.title = cur;
    dirPicker.list.innerHTML = "";

    if (data.parent != null && data.parent !== cur) {
      dirPicker.list.appendChild(
        el("button", {
          type: "button",
          class: "nr-dir-row nr-dir-up",
          onClick: () => browseDir(data.parent),
        }, [el("span", { class: "nr-dir-ic", text: "↰" }), el("span", { class: "nr-dir-name", text: ".. (parent)" })]),
      );
    }

    const dirs = Array.isArray(data.dirs) ? data.dirs : [];
    if (!dirs.length) {
      dirPicker.list.appendChild(el("div", { class: "nr-dir-empty", text: "No subdirectories here." }));
    }
    for (const d of dirs) {
      // d may be a string (name) or {name, path}
      const name = typeof d === "string" ? d : d.name || d.path || "";
      const childPath = typeof d === "string" ? joinPath(cur, d) : d.path || joinPath(cur, name);
      dirPicker.list.appendChild(
        el("button", {
          type: "button",
          class: "nr-dir-row",
          onClick: () => browseDir(childPath),
        }, [el("span", { class: "nr-dir-ic", text: "▸" }), el("span", { class: "nr-dir-name", text: name })]),
      );
    }
  }

  function joinPath(base, name) {
    if (!base) return name;
    return base.endsWith("/") ? base + name : `${base}/${name}`;
  }

  // ── PREVIEW ROSTER ──
  async function onPreview() {
    if (state.previewBusy) return;
    clearMessages();
    const goal = goalInput.value.trim();
    if (!goal) {
      showError("Enter a goal before previewing the roster.");
      goalInput.focus();
      return;
    }
    state.previewBusy = true;
    previewBtn.disabled = true;
    previewBtn.textContent = "Previewing…";
    rosterPanel.innerHTML = "";
    rosterPanel.appendChild(el("div", { class: "nr-roster-loading", text: "Deriving roster…" }));

    const count = clampCount(parseInt(countInput.value, 10));
    const dynamic = toggles.dynamic_agents.get() ? "1" : "0";
    const testing = toggles.no_testing.get() ? "0" : "1";
    const qs =
      `/preview-roster?goal=${encodeURIComponent(goal)}` +
      `&agent_count=${count}&dynamic=${dynamic}&testing=${testing}`;
    try {
      const data = await call(qs);
      if (aborted) return;
      renderRoster(Array.isArray(data) ? data : data && Array.isArray(data.roster) ? data.roster : []);
    } catch (e) {
      if (aborted) return;
      rosterPanel.innerHTML = "";
      rosterPanel.appendChild(
        el("div", { class: "nr-roster-error", text: `Preview failed: ${esc(e.message)}` }),
      );
    } finally {
      state.previewBusy = false;
      previewBtn.disabled = false;
      previewBtn.textContent = "Preview agents";
    }
  }

  function renderRoster(agents) {
    rosterPanel.innerHTML = "";
    // drop overrides for agents no longer present
    state.rosterOverrides = {};
    if (!agents.length) {
      rosterPanel.appendChild(
        el("div", { class: "nr-roster-empty" }, [
          el("span", { class: "nr-roster-empty-mark", "aria-hidden": "true", text: "○" }),
          el("span", { text: "No agents proposed for this goal." }),
        ]),
      );
      return;
    }
    const grid = el("div", { class: "nr-roster-grid rise-stagger" });
    for (const a of agents) grid.appendChild(buildAgentCard(a));
    rosterPanel.appendChild(grid);
  }

  function buildAgentCard(agent) {
    const id = String(agent.id || "");
    const profile = agent.profile || {};
    const initialModel = profile.model_tier || "inherit";
    const initialEffort = profile.effort || "inherit";
    const initialPlan = profile.permission_mode === "plan";

    // seed override store from proposed profile so unchanged cards still ship a profile
    state.rosterOverrides[id] = {
      model_tier: initialModel,
      effort: initialEffort,
      permission_mode: initialPlan ? "plan" : profile.permission_mode || "bypassPermissions",
    };

    const modelSel = makeSelect(MODEL_TIERS, initialModel, "MODEL");
    const effortSel = makeSelect(EFFORTS, initialEffort, "EFFORT");
    const planChk = el("input", { type: "checkbox" });
    if (initialPlan) planChk.checked = true;

    const planLabel = el("label", { class: "nr-card-check" }, [
      planChk,
      el("span", { class: "nr-card-check-track" }),
      el("span", { class: "nr-card-check-text", text: "PLAN" }),
    ]);

    function sync() {
      state.rosterOverrides[id] = {
        model_tier: modelSel.value,
        effort: effortSel.value,
        permission_mode: planChk.checked ? "plan" : "bypassPermissions",
      };
      planLabel.classList.toggle("is-on", planChk.checked);
    }
    modelSel.addEventListener("change", sync);
    effortSel.addEventListener("change", sync);
    planChk.addEventListener("change", sync);
    if (initialPlan) planLabel.classList.add("is-on");

    const lane = agent.lane || agent.kind || "";
    const focus = agent.focus || "";
    const subs = Array.isArray(agent.subagents) ? agent.subagents : [];

    return el("div", { class: "nr-card" }, [
      el("div", { class: "nr-card-top" }, [
        el("span", { class: "nr-card-id", text: id || "?" }),
        lane ? el("span", { class: "nr-card-lane", text: String(lane) }) : null,
      ]),
      focus ? el("div", { class: "nr-card-focus", text: focus }) : null,
      subs.length
        ? el(
            "div",
            { class: "nr-card-subs" },
            subs.slice(0, 6).map((s) => el("span", { class: "nr-sub-chip", text: String(s) })),
          )
        : null,
      el("div", { class: "nr-card-ctrls" }, [
        ctrl("MODEL", modelSel),
        ctrl("EFFORT", effortSel),
        planLabel,
      ]),
    ]);
  }

  function ctrl(label, control) {
    return el("div", { class: "nr-ctrl" }, [el("span", { class: "nr-ctrl-label", text: label }), control]);
  }

  function makeSelect(opts, selected, ariaLabel) {
    const wrap = el("div", { class: "nr-select-wrap" });
    const sel = el("select", { class: "nr-select", "aria-label": ariaLabel });
    for (const [val, label] of opts) {
      const o = el("option", { value: val, text: label });
      if (val === selected) o.selected = true;
      sel.appendChild(o);
    }
    wrap.appendChild(sel);
    wrap.appendChild(el("span", { class: "nr-select-caret", "aria-hidden": "true", text: "▾" }));
    // The wrapper is what gets placed in the card DOM (so the caret can overlay the
    // native control), but callers read `.value` and bind `change` against the real
    // <select> — which stays a queryable `select.nr-select` child of the card.
    Object.defineProperty(wrap, "value", { get: () => sel.value });
    wrap.addEventListener = (...a) => sel.addEventListener(...a);
    return wrap;
  }

  // ── LAUNCH ──
  async function onLaunch(e) {
    if (e) e.preventDefault();
    if (state.launchBusy) return;
    clearMessages();

    const goal = goalInput.value.trim();
    if (!goal) {
      showError("Goal is required.");
      goalInput.focus();
      return;
    }
    const count = clampCount(parseInt(countInput.value, 10));
    countInput.value = String(count);

    const overrides = state.rosterOverrides || {};
    const body = {
      goal,
      project_path: state.cwd || null,
      dynamic_agents: toggles.dynamic_agents.get(),
      agent_count: count,
      model_tiering: toggles.model_tiering.get(),
      effort_dial: toggles.effort_dial.get(),
      no_testing: toggles.no_testing.get(),
      instructions: instrInput.value.trim(),
      roster_overrides: Object.keys(overrides).length ? overrides : {},
    };

    state.launchBusy = true;
    launchBtn.disabled = true;
    launchBtn.classList.add("is-busy");
    setLaunchLabel("Launching…");
    try {
      const data = await call("/runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (aborted) return;
      const sid = (data && (data.session_id || data.sessionId)) || "";
      // Persist the new session so the dashboard's syncSessionFromStorage adopts it on mount.
      if (sid) {
        try {
          localStorage.setItem("archon.session", sid);
        } catch (_) {
          /* localStorage unavailable (private mode / disabled) — non-fatal */
        }
      }
      showOk(`Run started${sid ? ` — session ${sid}` : ""}. Switching…`);
      // give the orchestrator a beat to register before the shell switches sessions
      setTimeout(() => {
        if (aborted) return;
        navigate("#/");
      }, 450);
    } catch (err) {
      if (aborted) return;
      showError(`Launch failed: ${esc(err.message)}`);
      launchBtn.disabled = false;
      launchBtn.classList.remove("is-busy");
      setLaunchLabel("Launch");
      state.launchBusy = false;
    }
  }

  function setLaunchLabel(text) {
    const label = launchBtn.querySelector(".nr-btn-label");
    if (label) label.textContent = text;
    else launchBtn.textContent = text;
  }

  // ── messages ──
  function showError(msg) {
    errBox.innerHTML = "";
    errBox.appendChild(document.createTextNode(stripAnsi(msg)));
    errBox.hidden = false;
    okBox.hidden = true;
  }
  function showOk(text) {
    okBox.textContent = stripAnsi(text);
    okBox.hidden = false;
    errBox.hidden = true;
  }
  function clearMessages() {
    errBox.hidden = true;
    okBox.hidden = true;
  }

  // ─────────────────────────────────────────────────────────
  //  CLEANUP
  // ─────────────────────────────────────────────────────────
  return function cleanup() {
    aborted = true;
    for (const ac of controllers) {
      try {
        ac.abort();
      } catch (_) {
        /* noop */
      }
    }
    controllers.clear();
    if (root.parentNode) root.parentNode.removeChild(root);
  };
}

// ── Scoped styles (tokens only; injected once) ──────────────
const STYLE_ID = "nr-view-styles";
function injectStyles() {
  if (typeof document === "undefined" || document.getElementById(STYLE_ID)) return;
  const css = `
/* ── shell — calm, centered, airy ─────────────────────────── */
.nr-view { max-width: 760px; margin: 0 auto; padding: 40px 24px 96px; }

/* ── header ───────────────────────────────────────────────── */
.nr-header { margin-bottom: 28px; }
.nr-title { font-family: var(--serif); font-size: 40px; line-height: 1.04; font-weight: 600;
  letter-spacing: -0.02em; color: var(--text-0); }
.nr-sub { font-family: var(--sans); font-size: 14px; line-height: 1.55; color: var(--text-2);
  margin-top: 12px; max-width: 56ch; }

/* ── form rhythm ──────────────────────────────────────────── */
.nr-form { display: flex; flex-direction: column; gap: 18px; }

/* large rounded surface cards — the MONO building block */
.nr-card-lg { background: var(--bg-1); border: 1px solid var(--border-dim); border-radius: var(--r-lg);
  padding: 22px 24px; display: flex; flex-direction: column; gap: 22px;
  box-shadow: var(--shadow-sm); transition: border-color 200ms ease, box-shadow 200ms ease; }

/* ── field primitive ──────────────────────────────────────── */
.nr-field { display: flex; flex-direction: column; gap: 9px; }
.nr-label-row { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
.nr-label { font-family: var(--sans); font-size: 13px; font-weight: 600; letter-spacing: 0.01em;
  color: var(--text-0); }
.nr-req { color: var(--accent); font-weight: 700; }
.nr-hint { font-family: var(--sans); font-size: 12px; color: var(--text-3); }

/* ── inputs ───────────────────────────────────────────────── */
.nr-textarea {
  font-family: var(--sans); font-size: 14px; line-height: 1.6;
  background: var(--bg); color: var(--text-0);
  border: 1px solid var(--border); border-radius: var(--r-sm);
  padding: 12px 14px; width: 100%; resize: vertical; min-height: 72px;
  transition: border-color 150ms ease, box-shadow 150ms ease, background 150ms ease;
}
.nr-textarea::placeholder { color: var(--text-3); }
.nr-textarea:hover { border-color: var(--border-hi); }
.nr-textarea:focus { outline: none; border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft); }

.nr-number { font-family: var(--mono); font-size: 14px; color: var(--text-0);
  background: var(--bg); border: none; }

/* ── toggles → pill chips (accent ON-state is meaningful signal) ── */
.nr-toggles { display: flex; flex-wrap: wrap; gap: 10px; }
.nr-toggle { display: inline-flex; align-items: center; gap: 9px; cursor: pointer;
  border: 1px solid var(--border); border-radius: var(--r-pill);
  padding: 8px 14px 8px 12px; background: var(--bg);
  transition: border-color 150ms ease, background 150ms ease, color 150ms ease; }
.nr-toggle:hover { border-color: var(--border-hi); background: var(--fill-hover); }
.nr-toggle input { position: absolute; opacity: 0; width: 0; height: 0; }
.nr-toggle-track { width: 30px; height: 17px; border-radius: var(--r-pill); flex-shrink: 0;
  background: var(--track); border: 1px solid var(--border); position: relative;
  transition: background 200ms ease, border-color 200ms ease; }
.nr-toggle-track::after { content: ''; position: absolute; width: 11px; height: 11px; border-radius: 50%;
  background: var(--text-3); top: 2px; left: 2px;
  transition: transform 200ms ease, background 200ms ease; }
.nr-toggle input:checked + .nr-toggle-track { background: var(--accent); border-color: var(--accent); }
.nr-toggle input:checked + .nr-toggle-track::after { transform: translateX(13px); background: var(--accent-fg); }
.nr-toggle-label { font-family: var(--sans); font-size: 13px; font-weight: 500; color: var(--text-2);
  white-space: nowrap; transition: color 150ms ease; }
.nr-toggle input:checked ~ .nr-toggle-label { color: var(--text-0); }
.nr-toggle:focus-within { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }

/* ── agent count → pill stepper ───────────────────────────── */
.nr-count-wrap { display: inline-flex; align-items: stretch; width: max-content;
  border: 1px solid var(--border); border-radius: var(--r-pill); overflow: hidden; background: var(--bg); }
.nr-count-wrap:focus-within { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
.nr-count-wrap .nr-number { width: 56px; text-align: center; border: none; border-radius: 0; padding: 9px 0;
  -moz-appearance: textfield; appearance: textfield; }
.nr-count-wrap .nr-number:focus { outline: none; }
.nr-count-wrap .nr-number::-webkit-outer-spin-button,
.nr-count-wrap .nr-number::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }
.nr-step { font-family: var(--sans); font-size: 18px; line-height: 1; color: var(--text-2);
  background: transparent; border: none; padding: 0 16px; cursor: pointer;
  transition: color 150ms ease, background 150ms ease; }
.nr-step:hover { color: var(--text-0); background: var(--fill-hover); }
.nr-step:active { color: var(--accent); }

/* ── dir picker ───────────────────────────────────────────── */
.nr-dir { border: 1px solid var(--border); border-radius: var(--r); overflow: hidden; background: var(--bg); }
.nr-dir-bar { display: flex; align-items: center; gap: 10px; padding: 10px 12px;
  border-bottom: 1px solid var(--border-dim); background: var(--bg-2); }
.nr-dir-bar-ic { color: var(--text-3); font-size: 12px; flex-shrink: 0; }
.nr-dir-path { flex: 1; min-width: 0; font-family: var(--mono); font-size: 12px; color: var(--text-1);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; transition: color 300ms ease; }
.nr-dir-path.nr-dir-picked { color: var(--ok); }
.nr-use-dir { flex-shrink: 0; }
.nr-dir-list { max-height: 240px; overflow-y: auto; display: flex; flex-direction: column;
  scrollbar-width: thin; scrollbar-color: var(--scrollbar-thumb) transparent; }
.nr-dir-list::-webkit-scrollbar { width: 8px; }
.nr-dir-list::-webkit-scrollbar-thumb { background: var(--scrollbar-thumb); border-radius: var(--r-pill); }
.nr-dir-row { display: flex; align-items: center; gap: 10px; width: 100%; text-align: left;
  font-family: var(--mono); font-size: 12.5px; color: var(--text-1);
  background: transparent; border: none; border-bottom: 1px solid var(--border-dim);
  padding: 9px 14px; cursor: pointer; transition: background 120ms ease, color 120ms ease; }
.nr-dir-row:last-child { border-bottom: none; }
.nr-dir-row:hover { background: var(--fill-hover); color: var(--text-0); }
.nr-dir-up { color: var(--text-2); }
.nr-dir-ic { color: var(--text-3); width: 13px; flex-shrink: 0; }
.nr-dir-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.nr-dir-loading, .nr-dir-empty, .nr-dir-error { font-family: var(--sans); font-size: 12px;
  padding: 16px 14px; color: var(--text-3); }
.nr-dir-error { color: var(--err); }

/* ── roster card header ───────────────────────────────────── */
.nr-card-hdr { display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; }
.nr-card-hdr-text { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.nr-card-hdr-title { font-family: var(--serif); font-size: 19px; font-weight: 600; letter-spacing: -0.01em;
  color: var(--text-0); }
.nr-card-hdr-hint { font-family: var(--sans); font-size: 12.5px; color: var(--text-3); }

.nr-roster { min-height: 4px; }
.nr-roster-loading, .nr-roster-error { font-family: var(--sans); font-size: 13px;
  color: var(--text-3); padding: 6px 0; }
.nr-roster-error { color: var(--err); }
.nr-roster-empty { display: flex; align-items: center; gap: 10px; font-family: var(--sans);
  font-size: 13px; color: var(--text-3); padding: 14px 16px; border: 1px dashed var(--border);
  border-radius: var(--r); }
.nr-roster-empty-mark { font-size: 14px; color: var(--text-3); }
.nr-roster-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 240px), 1fr)); gap: 14px; }

/* ── agent card (rounded, mono surface, accent only on PLAN-on) ── */
.nr-card { background: var(--bg-2); border: 1px solid var(--border-dim); border-radius: var(--r);
  padding: 16px; display: flex; flex-direction: column; gap: 12px;
  transition: border-color 200ms ease, box-shadow 200ms ease; }
.nr-card:hover { border-color: var(--border); box-shadow: var(--shadow-sm); }
.nr-card-top { display: flex; align-items: center; gap: 10px; }
.nr-card-id { font-family: var(--mono); font-size: 14px; font-weight: 600; letter-spacing: 0.02em;
  color: var(--text-0); }
.nr-card-lane { font-family: var(--mono); font-size: 9px; letter-spacing: 0.1em; text-transform: uppercase;
  color: var(--route); background: var(--route-bg); border: 1px solid var(--route-line);
  border-radius: var(--r-pill); padding: 2px 8px; }
.nr-card-focus { font-family: var(--sans); font-size: 13px; color: var(--text-1); line-height: 1.45; }
.nr-card-subs { display: flex; flex-wrap: wrap; gap: 6px; }
.nr-sub-chip { font-family: var(--mono); font-size: 10px; color: var(--text-2);
  background: var(--bg-3); border: 1px solid var(--border-dim); border-radius: var(--r-pill);
  padding: 3px 9px; white-space: nowrap; }
.nr-card-ctrls { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 12px;
  padding-top: 12px; border-top: 1px solid var(--border-dim); }
.nr-ctrl { display: flex; flex-direction: column; gap: 5px; min-width: 0; }
.nr-ctrl-label { font-family: var(--mono); font-size: 9px; letter-spacing: 0.14em;
  text-transform: uppercase; color: var(--text-3); }

/* custom select — rounded, mono, caret affordance */
.nr-select-wrap { position: relative; display: inline-flex; }
.nr-select { font-family: var(--mono); font-size: 11px; color: var(--text-1);
  background: var(--bg); border: 1px solid var(--border); border-radius: var(--r-pill);
  padding: 6px 26px 6px 12px; cursor: pointer;
  -webkit-appearance: none; appearance: none;
  transition: border-color 150ms ease, color 150ms ease; }
.nr-select:hover { border-color: var(--border-hi); color: var(--text-0); }
.nr-select:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
.nr-select-caret { position: absolute; right: 11px; top: 50%; transform: translateY(-50%);
  font-size: 9px; color: var(--text-3); pointer-events: none; }

/* plan = pill chip toggle (accent when ON — meaningful state) */
.nr-card-check { display: inline-flex; align-items: center; gap: 8px; cursor: pointer; align-self: center;
  border: 1px solid var(--border); border-radius: var(--r-pill); padding: 5px 12px 5px 9px;
  background: var(--bg); transition: border-color 150ms ease, background 150ms ease; }
.nr-card-check input { position: absolute; opacity: 0; width: 0; height: 0; }
.nr-card-check-track { width: 26px; height: 15px; border-radius: var(--r-pill); flex-shrink: 0;
  background: var(--track); border: 1px solid var(--border); position: relative;
  transition: background 200ms ease, border-color 200ms ease; }
.nr-card-check-track::after { content: ''; position: absolute; width: 9px; height: 9px; border-radius: 50%;
  background: var(--text-3); top: 2px; left: 2px; transition: transform 200ms ease, background 200ms ease; }
.nr-card-check input:checked + .nr-card-check-track { background: var(--accent); border-color: var(--accent); }
.nr-card-check input:checked + .nr-card-check-track::after { transform: translateX(11px); background: var(--accent-fg); }
.nr-card-check-text { font-family: var(--mono); font-size: 9px; letter-spacing: 0.14em;
  text-transform: uppercase; color: var(--text-3); transition: color 150ms ease; }
.nr-card-check.is-on { border-color: var(--accent-line); }
.nr-card-check.is-on .nr-card-check-text { color: var(--text-0); }
.nr-card-check:focus-within { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }

/* ── advanced (progressive disclosure) ────────────────────── */
.nr-adv { padding: 0; gap: 0; overflow: hidden; }
.nr-adv-toggle { display: flex; align-items: center; gap: 12px; width: 100%; text-align: left;
  background: transparent; border: none; padding: 20px 24px; cursor: pointer;
  font-family: var(--sans); color: var(--text-0);
  border-radius: var(--r-lg); transition: background 150ms ease; }
.nr-adv-toggle:hover { background: var(--fill-hover); }
.nr-adv-toggle:focus-visible { outline: none; box-shadow: inset 0 0 0 2px var(--accent); border-radius: var(--r-lg); }
.nr-adv-caret { font-size: 11px; color: var(--text-3); flex-shrink: 0;
  transition: transform 200ms ease, color 150ms ease; }
.nr-adv[data-open="true"] .nr-adv-caret { transform: rotate(90deg); color: var(--accent); }
.nr-adv-toggle-text { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.nr-adv-toggle-title { font-size: 14px; font-weight: 600; color: var(--text-0); }
.nr-adv-toggle-hint { font-size: 12px; color: var(--text-3); }
.nr-adv-body { display: none; flex-direction: column; gap: 22px; padding: 4px 24px 24px; }
.nr-adv[data-open="true"] .nr-adv-body { display: flex; }

/* ── actions footer ───────────────────────────────────────── */
.nr-actions { display: flex; align-items: center; justify-content: flex-end; gap: 16px; flex-wrap: wrap;
  margin-top: 6px; }
.nr-actions-msgs { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.nr-error, .nr-ok { font-family: var(--sans); font-size: 13px; line-height: 1.4; }
.nr-error { color: var(--err); }
.nr-ok { color: var(--ok); }

/* ── buttons (pills) ──────────────────────────────────────── */
.nr-btn { font-family: var(--sans); font-size: 13px; font-weight: 600; letter-spacing: 0.01em;
  border-radius: var(--r-pill); padding: 10px 20px; cursor: pointer;
  transition: background 150ms ease, color 150ms ease, border-color 150ms ease, box-shadow 150ms ease, transform 120ms ease;
  display: inline-flex; align-items: center; gap: 8px; }
.nr-btn:disabled { opacity: 0.55; cursor: default; }
.nr-btn:focus-visible { outline: none; box-shadow: 0 0 0 3px var(--accent-soft); }

.nr-btn-ghost { color: var(--text-1); background: var(--bg); border: 1px solid var(--border); padding: 9px 16px; }
.nr-btn-ghost:hover:not(:disabled) { color: var(--text-0); border-color: var(--border-hi); background: var(--fill-hover); }
.nr-btn-ghost:active:not(:disabled) { transform: translateY(1px); }

/* PRIMARY — the ONE place vivid accent fills a surface */
.nr-btn-primary { color: var(--accent-fg); background: var(--accent); border: 1px solid var(--accent);
  padding: 11px 24px; box-shadow: var(--shadow-accent); }
.nr-btn-primary:hover:not(:disabled) { background: var(--accent-deep); border-color: var(--accent-deep); }
.nr-btn-primary:active:not(:disabled) { transform: translateY(1px); }
.nr-btn-primary.is-busy { opacity: 0.8; }
.nr-btn-arrow { transition: transform 180ms ease; }
.nr-btn-primary:hover:not(:disabled) .nr-btn-arrow { transform: translateX(3px); }

/* ── responsive ───────────────────────────────────────────── */
@media (max-width: 600px) {
  .nr-view { padding: 28px 16px 72px; }
  .nr-title { font-size: 32px; }
  .nr-card-lg { padding: 18px; border-radius: var(--r); }
  .nr-adv-toggle { padding: 18px; }
  .nr-adv-body { padding: 4px 18px 18px; }
  .nr-actions { justify-content: stretch; }
  .nr-btn-primary { width: 100%; justify-content: center; }
}

/* ── reduced motion: kill the arrow nudge + caret spin transitions ── */
@media (prefers-reduced-motion: reduce) {
  .nr-btn-arrow, .nr-adv-caret, .nr-toggle-track::after, .nr-card-check-track::after { transition: none; }
}
`;
  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = css;
  document.head.appendChild(style);
}

export default { mount };
