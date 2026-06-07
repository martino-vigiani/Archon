/* ============================================================================
   ARCHON — WORKSPACE VIEW (F13, experimental)
   Owner: vfiles. Single owner of this file.

   An illustrative, animated 2D map of the agent workspace. Agent nodes drift /
   orbit gently in a neutral space; file nodes pop in near their authoring agent
   and orbit it; contract nodes float between the agents that provide / depend
   on them. Edges are drawn with distinct styles per kind.

   Data sources (via ctx.api):
     GET /workspace-graph -> { nodes:[{id,type:file|agent|contract,worker,label}],
                               edges:[{from,to,kind:creates|provides|depends}] }
     GET /files           -> [{path,worker,action:created|modified,ts}]

   Integration contract (CONTRACT §6):
     export function mount(container, ctx) { ...; return () => cleanup }
     ctx = { sessionId, api(path), ws(path), navigate(hash) }

   Design language: "MONO". The canvas is a calm neutral field; nodes are
   rounded (agents = rounded squares, files = dots, contracts = diamonds) and
   stay mono by default — accent/semantic color is used ONLY to encode meaning
   (agents pick up the brand accent, edges carry semantic hues per kind). Labels
   are legible Geist Mono; the legend is a clean rounded strip. All colors are
   READ from CSS custom properties (tokens.css) at runtime so the canvas tracks
   dark/light themes. No deps, no npm, hand-rolled requestAnimationFrame. rAF is
   throttled and fully paused on unmount.
============================================================================ */

const POLL_MS = 4000; // graph refresh cadence — gentle on the backend
const TARGET_FPS = 30; // throttle rAF so we never peg the CPU
const FRAME_MS = 1000 / TARGET_FPS;
const POP_MS = 900; // duration of the "pop-in" animation for new nodes

// ── small DOM helpers (vanilla, dependency-free) ────────────────────────────
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = String(text);
  return node;
}

// Strip ANSI escape sequences from any server-provided text (CONTRACT §11).
// eslint-disable-next-line no-control-regex
const ANSI_RE = /[][[()#;?]*(?:[0-9]{1,4}(?:;[0-9]{0,4})*)?[0-9A-ORZcf-nqry=><]/g;
function stripAnsi(value) {
  return String(value == null ? "" : value).replace(ANSI_RE, "");
}

// Resolve a CSS custom property to its concrete value against a probe element so
// the canvas (which can't use var()) tracks the active theme.
function tokenReader(probe) {
  const cache = new Map();
  return (name, fallback) => {
    if (cache.has(name)) return cache.get(name);
    let v = "";
    try {
      v = getComputedStyle(probe).getPropertyValue(name).trim();
    } catch {
      v = "";
    }
    const out = v || fallback || "#888";
    cache.set(name, out);
    return out;
  };
}

// Deterministic 0..1 hash from a string — used to scatter initial positions so
// the layout looks intentional rather than random on every reload.
function hash01(str) {
  let h = 2166136261;
  const s = String(str);
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return ((h >>> 0) % 100000) / 100000;
}

// ── public mount ────────────────────────────────────────────────────────────
export function mount(container, ctx) {
  const api = ctx && typeof ctx.api === "function" ? ctx.api : () => Promise.reject(new Error("no api"));
  const navigate = ctx && typeof ctx.navigate === "function" ? ctx.navigate : null;

  // ---- view scaffold --------------------------------------------------------
  const root = el("div", "ws-view");
  root.setAttribute("data-view", "workspace");
  root.innerHTML = `
    <style>
      .ws-view { display:flex; flex-direction:column; height:100%; min-height:420px;
        background: var(--bg); color: var(--text-1); font-family: var(--sans); }
      /* Header: airy, rounded "experimental" pill, big legible title */
      .ws-hdr { display:flex; align-items:center; gap:12px; padding:20px 28px 16px;
        border-bottom:1px solid var(--border-dim); flex-wrap:wrap; }
      .ws-title { font-family:var(--serif); font-size:20px; font-weight:600;
        letter-spacing:-0.01em; color:var(--text-0); line-height:1; }
      .ws-sub { font-family:var(--mono); font-size:11px; color:var(--text-3); letter-spacing:0.04em; }
      .ws-flag { font-family:var(--mono); font-size:9px; font-weight:600;
        letter-spacing:0.1em; text-transform:uppercase;
        color:var(--warn); border:1px solid var(--warn-line); background:var(--warn-bg);
        border-radius:var(--r-pill,999px); padding:3px 10px; }
      .ws-count { font-family:var(--mono); font-size:11px; color:var(--text-2);
        margin-left:auto; letter-spacing:0.02em; }
      /* Stage: the neutral canvas field, gently inset with large rounded corners */
      .ws-stage { position:relative; flex:1; min-height:340px; overflow:hidden;
        margin:16px 20px; border:1px solid var(--border-dim);
        border-radius:var(--r-lg); background:var(--bg-1); }
      .ws-stage canvas { display:block; width:100%; height:100%;
        border-radius:var(--r-lg); }
      .ws-overlay { position:absolute; inset:0; display:flex; align-items:center; justify-content:center;
        font-family:var(--mono); font-size:12px; color:var(--text-3); letter-spacing:0.04em;
        text-align:center; padding:0 24px; pointer-events:none; }
      .ws-overlay.err { color:var(--err); }
      .ws-spinner { display:inline-block; width:11px; height:11px; margin-right:9px; border-radius:50%;
        border:1.5px solid var(--border-hi); border-top-color:var(--accent);
        animation: ws-spin 0.8s linear infinite; vertical-align:middle; }
      @keyframes ws-spin { to { transform: rotate(360deg); } }
      /* Legend: clean rounded strip, swatches mirror the on-canvas shapes */
      .ws-legend { display:flex; flex-wrap:wrap; align-items:center; gap:14px 22px;
        padding:14px 28px; border-top:1px solid var(--border-dim); background:transparent; }
      .ws-leg-group { display:flex; align-items:center; gap:12px; }
      .ws-leg-title { font-family:var(--mono); font-size:9px; letter-spacing:0.1em;
        text-transform:uppercase; color:var(--text-3); }
      .ws-leg-item { display:flex; align-items:center; gap:6px;
        font-family:var(--mono); font-size:10px; color:var(--text-2); letter-spacing:0.02em; }
      .ws-leg-swatch { width:12px; height:12px; flex-shrink:0; }
      /* agent = rounded square in accent · file = neutral dot · contract = route diamond */
      .ws-leg-swatch.agent { border-radius:4px; border:1.5px solid var(--accent);
        background:var(--accent-soft); }
      .ws-leg-swatch.file { border-radius:50%; border:1px solid var(--text-2);
        background:var(--text-3); }
      .ws-leg-swatch.contract { border:1.5px solid var(--route);
        transform: rotate(45deg); width:9px; height:9px; border-radius:2px; }
      .ws-leg-line { width:20px; height:0; flex-shrink:0; }
      .ws-leg-line.creates { border-top:1.5px solid var(--ok); }
      .ws-leg-line.provides { border-top:1.5px dashed var(--route); }
      .ws-leg-line.depends { border-top:1.5px dotted var(--info); }
      .ws-hint { font-family:var(--sans); font-size:11px; color:var(--text-3);
        margin-left:auto; align-self:center; }
      @media (prefers-reduced-motion: reduce) { .ws-spinner { animation:none; } }
      @media (max-width: 600px) {
        .ws-hdr { padding:16px 18px 12px; }
        .ws-stage { margin:12px 14px; }
        .ws-legend { padding:12px 18px; }
        .ws-hint { display:none; }
      }
    </style>
    <div class="ws-hdr">
      <span class="ws-title">Agent Workspace</span>
      <span class="ws-flag">experimental</span>
      <span class="ws-sub" data-ref="sub">live orbital map</span>
      <span class="ws-count" data-ref="count">—</span>
    </div>
    <div class="ws-stage" data-ref="stage">
      <canvas data-ref="canvas"></canvas>
      <div class="ws-overlay" data-ref="overlay"><span class="ws-spinner"></span>loading workspace…</div>
    </div>
    <div class="ws-legend" data-ref="legend"></div>
  `;
  container.appendChild(root);

  const ref = (name) => root.querySelector(`[data-ref="${name}"]`);
  const stage = ref("stage");
  const canvas = ref("canvas");
  const overlay = ref("overlay");
  const subEl = ref("sub");
  const countEl = ref("count");
  const legendEl = ref("legend");

  buildLegend(legendEl);

  const ctxCanvas = canvas.getContext("2d");
  const readToken = tokenReader(root);

  // ---- simulation state -----------------------------------------------------
  // nodes: Map id -> {id,type,worker,label, x,y, vx,vy, born, r, hot}
  const nodes = new Map();
  let edges = []; // [{from,to,kind}]
  let firstLoaded = false;
  let lastError = null;
  let destroyed = false;

  let dpr = Math.max(1, Math.min(2, window.devicePixelRatio || 1));
  let W = 0;
  let H = 0;

  function resize() {
    const rect = stage.getBoundingClientRect();
    W = Math.max(120, Math.round(rect.width));
    H = Math.max(120, Math.round(rect.height));
    dpr = Math.max(1, Math.min(2, window.devicePixelRatio || 1));
    canvas.width = Math.round(W * dpr);
    canvas.height = Math.round(H * dpr);
    canvas.style.width = `${W}px`;
    canvas.style.height = `${H}px`;
    ctxCanvas.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  resize();

  const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(() => resize()) : null;
  if (ro) ro.observe(stage);
  window.addEventListener("resize", resize);

  // ---- ingest a freshly fetched graph, animating deltas ---------------------
  function ingest(graph) {
    const incoming = Array.isArray(graph && graph.nodes) ? graph.nodes : [];
    edges = Array.isArray(graph && graph.edges) ? graph.edges : [];

    const seen = new Set();
    const now = performance.now();

    for (const raw of incoming) {
      if (!raw || typeof raw.id !== "string") continue;
      const id = raw.id;
      seen.add(id);
      const type = raw.type === "agent" || raw.type === "contract" ? raw.type : "file";
      const label = stripAnsi(raw.label || id);
      const worker = raw.worker != null ? stripAnsi(String(raw.worker)) : null;

      const existing = nodes.get(id);
      if (existing) {
        existing.type = type;
        existing.label = label;
        existing.worker = worker;
        continue;
      }

      // New node: seed a position. Files pop in near their author; agents and
      // contracts scatter deterministically so the layout is stable.
      const r = type === "agent" ? 13 : type === "contract" ? 8 : 6;
      let x;
      let y;
      if (type === "file" && worker && nodes.has(`agent:${worker}`)) {
        const a = nodes.get(`agent:${worker}`);
        const ang = hash01(id) * Math.PI * 2;
        x = a.x + Math.cos(ang) * 24;
        y = a.y + Math.sin(ang) * 24;
      } else {
        x = (0.18 + hash01(id) * 0.64) * (W || 600);
        y = (0.18 + hash01(`${id}#y`) * 0.64) * (H || 400);
      }
      nodes.set(id, {
        id,
        type,
        worker,
        label,
        x,
        y,
        vx: 0,
        vy: 0,
        r,
        born: now,
        hot: firstLoaded, // only flag as "new" once the initial graph is shown
      });
    }

    // Drop nodes that vanished from the graph.
    for (const id of [...nodes.keys()]) {
      if (!seen.has(id)) nodes.delete(id);
    }

    firstLoaded = true;
    lastError = null;
    updateChrome();
  }

  function updateChrome() {
    const total = nodes.size;
    let agents = 0;
    let files = 0;
    let contracts = 0;
    for (const n of nodes.values()) {
      if (n.type === "agent") agents++;
      else if (n.type === "contract") contracts++;
      else files++;
    }
    safe(countEl, `${agents} agents · ${files} files${contracts ? ` · ${contracts} contracts` : ""}`);
    if (!total) {
      safe(subEl, "no activity yet");
      showOverlay("No workspace activity yet — files appear here as agents create them.", false);
    } else {
      safe(subEl, "live orbital map");
      hideOverlay();
    }
  }

  function safe(node, text) {
    const s = String(text == null ? "" : text);
    if (node.textContent !== s) node.textContent = s;
  }
  function showOverlay(msg, isErr) {
    overlay.classList.toggle("err", !!isErr);
    overlay.textContent = msg;
    overlay.style.display = "flex";
  }
  function hideOverlay() {
    overlay.style.display = "none";
  }

  // ---- physics: gentle orbital + soft repulsion -----------------------------
  function step(dt) {
    const cx = W / 2;
    const cy = H / 2;
    const k = Math.min(dt / FRAME_MS, 2); // clamp so a long pause doesn't explode the sim
    const t = performance.now() / 1000;

    // index agent positions for orbit anchoring
    for (const n of nodes.values()) {
      let ax = cx;
      let ay = cy;
      let anchored = false;

      if (n.type === "agent") {
        // agents drift slowly around the center on a wide, slow orbit
        const seed = hash01(n.id);
        const orbitR = 70 + seed * Math.min(W, H) * 0.22;
        const speed = 0.04 + seed * 0.05;
        ax = cx + Math.cos(t * speed + seed * 6.28) * orbitR;
        ay = cy + Math.sin(t * speed * 0.8 + seed * 6.28) * orbitR * 0.7;
        anchored = true;
      } else if (n.type === "file" && n.worker && nodes.has(`agent:${n.worker}`)) {
        // files orbit their authoring agent
        const a = nodes.get(`agent:${n.worker}`);
        const seed = hash01(n.id);
        const orbitR = 26 + seed * 22;
        const speed = 0.5 + seed * 0.7;
        ax = a.x + Math.cos(t * speed + seed * 6.28) * orbitR;
        ay = a.y + Math.sin(t * speed + seed * 6.28) * orbitR;
        anchored = true;
      } else {
        // unowned files / contracts: drift toward a deterministic resting spot
        const seed = hash01(n.id);
        ax = cx + Math.cos(seed * 6.28 + t * 0.06) * Math.min(W, H) * 0.32;
        ay = cy + Math.sin(seed * 6.28 + t * 0.06) * Math.min(W, H) * 0.26;
        anchored = true;
      }

      if (anchored) {
        // critically-damped pull toward the moving anchor (smooth, no spring jitter)
        const pull = n.type === "file" ? 0.12 : 0.06;
        n.vx += (ax - n.x) * pull * k;
        n.vy += (ay - n.y) * pull * k;
      }
    }

    // soft pairwise repulsion (only between same-tier-ish nodes, cheap O(n^2)
    // — fine for the small graphs this view shows; throttled by FPS)
    const list = [...nodes.values()];
    for (let i = 0; i < list.length; i++) {
      for (let j = i + 1; j < list.length; j++) {
        const a = list[i];
        const b = list[j];
        const dx = a.x - b.x;
        const dy = a.y - b.y;
        const d2 = dx * dx + dy * dy || 0.01;
        const min = a.r + b.r + 14;
        if (d2 < min * min) {
          const d = Math.sqrt(d2);
          const force = ((min - d) / min) * 0.6 * k;
          const ux = dx / d;
          const uy = dy / d;
          a.vx += ux * force;
          a.vy += uy * force;
          b.vx -= ux * force;
          b.vy -= uy * force;
        }
      }
    }

    // integrate + damping + keep on stage
    for (const n of nodes.values()) {
      n.vx *= 0.86;
      n.vy *= 0.86;
      n.x += n.vx * k;
      n.y += n.vy * k;
      const pad = n.r + 4;
      if (n.x < pad) { n.x = pad; n.vx *= -0.4; }
      if (n.x > W - pad) { n.x = W - pad; n.vx *= -0.4; }
      if (n.y < pad) { n.y = pad; n.vy *= -0.4; }
      if (n.y > H - pad) { n.y = H - pad; n.vy *= -0.4; }
    }
  }

  // ---- render ---------------------------------------------------------------
  function draw() {
    const c = ctxCanvas;
    c.clearRect(0, 0, W, H);
    if (!nodes.size) return;

    // MONO: agents carry the brand accent (they're the actors); files stay
    // neutral; contracts use the route hue. Edges encode their kind with
    // semantic colors. Everything else is mono. Fallbacks are neutral so the
    // canvas degrades gracefully if a token can't be resolved.
    const colAgent = readToken("--accent", "#5b7cfa");
    const colAgentSoft = readToken("--accent-soft", "rgba(91,124,250,0.14)");
    const colFile = readToken("--text-2", "#8a8a8a");
    const colContract = readToken("--route", "#7c5cfa");
    const colCreates = readToken("--ok", "#5a9e6f");
    const colProvides = readToken("--route", "#7c5cfa");
    const colDepends = readToken("--info", "#4a6e96");
    const colLabel = readToken("--text-3", "#767676");
    const colBg2 = readToken("--bg-2", "#1c1c20");

    const now = performance.now();

    // edges first (under nodes)
    c.lineWidth = 1;
    for (const e of edges) {
      const a = nodes.get(e.from);
      const b = nodes.get(e.to);
      if (!a || !b) continue;
      if (e.kind === "provides") {
        c.strokeStyle = colProvides;
        c.setLineDash([5, 4]);
        c.globalAlpha = 0.55;
      } else if (e.kind === "depends") {
        c.strokeStyle = colDepends;
        c.setLineDash([1, 4]);
        c.globalAlpha = 0.6;
      } else {
        c.strokeStyle = colCreates;
        c.setLineDash([]);
        c.globalAlpha = 0.4;
      }
      c.beginPath();
      c.moveTo(a.x, a.y);
      c.lineTo(b.x, b.y);
      c.stroke();
    }
    c.setLineDash([]);
    c.globalAlpha = 1;

    // nodes
    c.font = `9px ${readToken("--mono", "monospace").split(",")[0] || "monospace"}`;
    c.textAlign = "center";
    c.textBaseline = "middle";
    for (const n of nodes.values()) {
      // pop-in: scale up + fade in over POP_MS
      let scale = 1;
      let alpha = 1;
      if (n.hot) {
        const age = now - n.born;
        if (age < POP_MS) {
          const p = age / POP_MS;
          const e = 1 - Math.pow(1 - p, 3); // ease-out cubic
          scale = 0.2 + e * 0.8;
          alpha = e;
          // soft pulse halo while popping
          c.globalAlpha = (1 - p) * 0.5;
          c.beginPath();
          c.arc(n.x, n.y, n.r * (1 + p * 2.2), 0, Math.PI * 2);
          c.strokeStyle = n.type === "agent" ? colAgent : n.type === "contract" ? colContract : colFile;
          c.stroke();
        } else {
          n.hot = false;
        }
      }
      c.globalAlpha = alpha;
      const r = n.r * scale;

      if (n.type === "agent") {
        // agent: filled rounded square in the brand accent (the actor "icon").
        // Soft accent fill + accent edge → reads as the one colored anchor each
        // file orbits. Generous corner radius keeps it on-brand (rounded).
        c.fillStyle = colAgentSoft;
        c.strokeStyle = colAgent;
        c.lineWidth = 1.5;
        roundRect(c, n.x - r, n.y - r, r * 2, r * 2, Math.max(4, r * 0.42));
        c.fill();
        c.stroke();
        c.fillStyle = colAgent;
        c.fillText(n.label.slice(0, 4), n.x, n.y);
      } else if (n.type === "contract") {
        // contract: rounded diamond, route hue (semantic encoding only)
        c.fillStyle = colBg2;
        c.strokeStyle = colContract;
        c.lineWidth = 1.25;
        c.beginPath();
        c.moveTo(n.x, n.y - r);
        c.lineTo(n.x + r, n.y);
        c.lineTo(n.x, n.y + r);
        c.lineTo(n.x - r, n.y);
        c.closePath();
        c.fill();
        c.stroke();
      } else {
        // file: small neutral dot with a faint ring (stays mono)
        c.beginPath();
        c.arc(n.x, n.y, r, 0, Math.PI * 2);
        c.fillStyle = colFile;
        c.fill();
      }
      c.globalAlpha = 1;
    }

    // labels for files/contracts (drawn dim, only for larger graphs sparingly)
    c.globalAlpha = 1;
    c.fillStyle = colLabel;
    for (const n of nodes.values()) {
      if (n.type === "agent") continue;
      c.fillText(truncate(n.label, 14), n.x, n.y + n.r + 7);
    }
  }

  // ---- animation loop (throttled, pausable) ---------------------------------
  let rafId = null;
  let lastFrame = 0;
  function loop(ts) {
    if (destroyed) return;
    rafId = requestAnimationFrame(loop);
    const dt = ts - lastFrame;
    if (dt < FRAME_MS) return; // throttle to TARGET_FPS
    lastFrame = ts;
    step(dt);
    draw();
  }
  rafId = requestAnimationFrame(loop);

  // pause rAF entirely when the tab is hidden (saves CPU, contract: don't peg)
  function onVisibility() {
    if (document.hidden) {
      if (rafId != null) {
        cancelAnimationFrame(rafId);
        rafId = null;
      }
    } else if (rafId == null && !destroyed) {
      lastFrame = performance.now();
      rafId = requestAnimationFrame(loop);
    }
  }
  document.addEventListener("visibilitychange", onVisibility);

  // ---- polling --------------------------------------------------------------
  async function refresh() {
    if (destroyed) return;
    try {
      const res = await api("/workspace-graph");
      if (destroyed) return;
      if (!res || !res.ok) throw new Error(`workspace-graph ${res ? res.status : "?"}`);
      const graph = await res.json();
      if (destroyed) return;
      ingest(graph);
    } catch (err) {
      if (destroyed) return;
      lastError = err;
      // Only surface the error if we have nothing to show; otherwise keep the
      // last good frame and stay quiet (transient poll failures are common).
      if (!firstLoaded || !nodes.size) {
        showOverlay(`Could not load workspace: ${stripAnsi(err && err.message)}`, true);
      }
    }
  }

  let pollTimer = null;
  function schedule() {
    if (destroyed) return;
    pollTimer = setTimeout(async () => {
      await refresh();
      schedule();
    }, POLL_MS);
  }
  refresh().then(schedule);

  // optional navigation affordance reused by the shell (no-op if absent)
  void navigate;

  // ---- cleanup --------------------------------------------------------------
  return function cleanup() {
    destroyed = true;
    if (rafId != null) cancelAnimationFrame(rafId);
    rafId = null;
    if (pollTimer != null) clearTimeout(pollTimer);
    pollTimer = null;
    document.removeEventListener("visibilitychange", onVisibility);
    window.removeEventListener("resize", resize);
    if (ro) ro.disconnect();
    nodes.clear();
    edges = [];
    if (root.parentNode) root.parentNode.removeChild(root);
  };
}

// ── drawing utilities ───────────────────────────────────────────────────────
function roundRect(c, x, y, w, h, r) {
  const rr = Math.min(r, w / 2, h / 2);
  c.beginPath();
  c.moveTo(x + rr, y);
  c.arcTo(x + w, y, x + w, y + h, rr);
  c.arcTo(x + w, y + h, x, y + h, rr);
  c.arcTo(x, y + h, x, y, rr);
  c.arcTo(x, y, x + w, y, rr);
  c.closePath();
}

function truncate(s, n) {
  const str = String(s == null ? "" : s);
  return str.length > n ? `${str.slice(0, n - 1)}…` : str;
}

function buildLegend(legendEl) {
  const nodeGroup = el("div", "ws-leg-group");
  nodeGroup.appendChild(el("span", "ws-leg-title", "Nodes"));
  for (const [cls, label] of [["agent", "agent"], ["file", "file"], ["contract", "contract"]]) {
    const item = el("div", "ws-leg-item");
    item.appendChild(el("span", `ws-leg-swatch ${cls}`));
    item.appendChild(el("span", null, label));
    nodeGroup.appendChild(item);
  }

  const edgeGroup = el("div", "ws-leg-group");
  edgeGroup.appendChild(el("span", "ws-leg-title", "Edges"));
  for (const [cls, label] of [["creates", "creates"], ["provides", "provides"], ["depends", "depends"]]) {
    const item = el("div", "ws-leg-item");
    item.appendChild(el("span", `ws-leg-line ${cls}`));
    item.appendChild(el("span", null, label));
    edgeGroup.appendChild(item);
  }

  legendEl.appendChild(nodeGroup);
  legendEl.appendChild(edgeGroup);
  legendEl.appendChild(el("span", "ws-hint", "illustrative — positions are schematic"));
}

export default { mount };
