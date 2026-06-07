// views/chat.js — F4: Real-time chat with the orchestrator (per-session memory).
//
// Integration contract (CONTRACT §11):
//   export function mount(container, ctx) { ...; return () => cleanup }
//   ctx = { sessionId, api(path[, opts]) -> Promise<Response>, ws(path), navigate(hash) }
//   - ctx.api(path, opts?) does fetch('/api' + path, opts) with ?session= appended.
//
// Behaviour:
//   - Renders a message list (user + orchestrator turns) and a composer.
//   - Send  -> POST /api/control/chat {text, chat_session_id}.
//   - Poll  -> GET  /api/chat/replies?chat_session_id=&since= on an interval,
//              appending new answers and advancing the `since` cursor.
//   - chat_session_id is stable per dashboard session ("dash" + sessionId) and
//     persisted in localStorage so memory survives reloads / view switches.
//   - Shows a "thinking…" indicator after a send until a reply arrives.
//   - Strips ANSI from all server text; escapes user/server content (textContent).
//   - Cleans up the poll timer on unmount.
//
// Dependency-free vanilla ES module; styling uses ONLY var(--…) tokens.

const POLL_INTERVAL_MS = 1500;
const STYLE_ID = "archon-chat-view-style";
const LS_OFFSET_PREFIX = "archon.chat.offset.";

// ESC () and BEL () referenced via escapes so no literal control
// characters live in this source file.
const ESC = "\\u001b";
// CSI: ESC [ params intermediates final-byte  (covers SGR colour codes).
const CSI_RE = new RegExp(ESC + "\\[[0-9;?]*[ -/]*[@-~]", "g");
// OSC: ESC ] ... terminated by BEL () or ST (ESC \).
const OSC_RE = new RegExp(ESC + "\\][\\s\\S]*?(?:\\u0007|" + ESC + "\\\\)", "g");
// Any other single-character escape: ESC followed by one byte.
const SINGLE_ESC_RE = new RegExp(ESC + "[@-Z\\\\-_]", "g");

/**
 * Strip ANSI escape sequences (CSI / SGR colour codes, OSC strings, single-char
 * escapes) from text. Server-side REPL output embeds ANSI; we render plain text.
 * @param {string} s
 * @returns {string}
 */
export function stripAnsi(s) {
  if (s == null) return "";
  return String(s)
    .replace(OSC_RE, "")
    .replace(CSI_RE, "")
    .replace(SINGLE_ESC_RE, "");
}

/**
 * Compute the stable per-session chat id ("dash" + sessionId).
 * @param {string|null|undefined} sessionId
 * @returns {string}
 */
export function chatSessionIdFor(sessionId) {
  const sid = sessionId == null ? "" : String(sessionId);
  return "dash" + sid;
}

/** Inject the chat-view stylesheet once (token-only; never edits app.css). */
function ensureStyles() {
  if (document.getElementById(STYLE_ID)) return;
  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
/* ── Chat view — MONO. Calm, airy, rounded. The thread is the hero;
   controls stay quiet until needed. Tokens only; no hardcoded values. ── */
.chat-view {
  display: flex; flex-direction: column;
  height: calc(100vh - 52px);
  min-height: 0;
  background: var(--bg);
}

/* Header — a quiet title bar with a live "memory" signal pill. */
.chat-view-hdr {
  padding: 22px 28px 16px;
  display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
}
.chat-view-hdr .section-title {
  font-family: var(--serif); font-weight: 600;
  font-size: 19px; letter-spacing: -0.01em; color: var(--text-0);
}
.chat-memory-note {
  font-family: var(--mono); font-size: 10px; color: var(--text-2);
  letter-spacing: 0.02em; margin-left: auto;
  display: flex; align-items: center; gap: 8px;
  padding: 6px 12px;
  background: var(--info-bg);
  border: 1px solid var(--info-line);
  border-radius: var(--r-pill, 999px);
  max-width: 100%;
}
.chat-memory-note > span:last-child {
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.chat-memory-dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--info); flex-shrink: 0;
  box-shadow: 0 0 0 3px var(--info-bg);
}

/* Message thread — generous gutters, comfortable rhythm. */
.chat-scroll {
  flex: 1; min-height: 0; overflow-y: auto;
  padding: 12px 28px 8px;
  display: flex; flex-direction: column; gap: 18px;
  scroll-behavior: smooth;
  scrollbar-width: thin;
  scrollbar-color: var(--scrollbar-thumb) transparent;
}
.chat-scroll::-webkit-scrollbar { width: 8px; }
.chat-scroll::-webkit-scrollbar-thumb {
  background: var(--scrollbar-thumb); border-radius: var(--r-pill, 999px);
  border: 2px solid transparent; background-clip: padding-box;
}

/* Empty state — invitational, centered, breathes. */
.chat-empty {
  margin: auto; max-width: 420px; text-align: center;
  display: flex; flex-direction: column; align-items: center; gap: 14px;
  padding: 24px;
}
.chat-empty-glyph {
  width: 52px; height: 52px; border-radius: var(--r-lg);
  display: grid; place-items: center;
  background: var(--accent-soft);
  border: 1px solid var(--accent-line);
  color: var(--accent);
}
.chat-empty-glyph svg { width: 24px; height: 24px; display: block; }
.chat-empty strong {
  font-family: var(--serif); color: var(--text-0); font-weight: 600;
  font-size: 17px; letter-spacing: -0.01em;
}
.chat-empty-sub {
  font-family: var(--sans); font-size: 13px; color: var(--text-2);
  line-height: 1.65;
}

/* Bubbles — rounded mono surfaces; user vs orchestrator distinguished by
   side + a subtle accent edge on the user's bubble (quiet, not loud). */
.chat-msg {
  display: flex; flex-direction: column; gap: 6px;
  max-width: 76%;
  animation: chat-bubble-in 260ms cubic-bezier(0.22, 1, 0.36, 1) both;
}
.chat-msg.from-user { align-self: flex-end; align-items: flex-end; }
.chat-msg.from-orch { align-self: flex-start; align-items: flex-start; }
.chat-role {
  font-family: var(--mono); font-size: 9px; letter-spacing: 0.18em;
  text-transform: uppercase; color: var(--text-3);
  padding: 0 4px;
}
.chat-msg.from-orch .chat-role { color: var(--accent); }
.chat-bubble {
  font-family: var(--sans); font-size: 14px; line-height: 1.62;
  color: var(--text-1);
  background: var(--bg-2);
  border: 1px solid var(--border-dim);
  border-radius: var(--r-lg);
  padding: 12px 16px;
  white-space: pre-wrap; word-break: break-word; overflow-wrap: anywhere;
  transition: border-color 200ms ease, box-shadow 200ms ease;
}
/* Orchestrator bubble: anchored corner on the left, faint surface. */
.chat-msg.from-orch .chat-bubble {
  border-bottom-left-radius: var(--r-sm);
  background: var(--bg-1);
}
/* User bubble: anchored corner on the right + a whisper of accent. */
.chat-msg.from-user .chat-bubble {
  border-bottom-right-radius: var(--r-sm);
  background: var(--bg-3);
  border-color: var(--accent-line);
  color: var(--text-0);
  box-shadow: inset 2px 0 0 0 var(--accent);
}

/* Awaiting / typing indicator — on-brand, calm three-dot pulse. */
.chat-thinking {
  align-self: flex-start;
  display: flex; align-items: center; gap: 10px;
  font-family: var(--mono); font-size: 11px; letter-spacing: 0.06em;
  color: var(--text-3);
  background: var(--bg-1);
  border: 1px solid var(--border-dim);
  border-radius: var(--r-pill, 999px);
  padding: 8px 14px;
  animation: chat-bubble-in 240ms cubic-bezier(0.22, 1, 0.36, 1) both;
}
.chat-thinking-dots { display: inline-flex; gap: 4px; }
.chat-thinking-dots span {
  width: 5px; height: 5px; border-radius: 50%;
  background: var(--accent);
  animation: chat-blink 1.2s ease-in-out infinite;
}
.chat-thinking-dots span:nth-child(2) { animation-delay: 0.2s; }
.chat-thinking-dots span:nth-child(3) { animation-delay: 0.4s; }

/* Error state — soft semantic fill, rounded, legible. */
.chat-error {
  align-self: stretch;
  font-family: var(--sans); font-size: 13px; line-height: 1.55;
  color: var(--err); border: 1px solid var(--err-line);
  background: var(--err-bg); border-radius: var(--r);
  padding: 11px 14px;
}

/* No-session state — centered, reassuring. */
.chat-inactive {
  margin: auto; max-width: 440px; text-align: center;
  font-family: var(--sans); font-size: 14px; color: var(--text-2);
  line-height: 1.7;
  padding: 24px;
}
.chat-inactive .chat-inactive-title {
  font-family: var(--mono);
  color: var(--text-0); font-weight: 600; display: block; margin-bottom: 10px;
  letter-spacing: 0.14em; text-transform: uppercase; font-size: 11px;
}

/* Composer — a pill-shaped input field with a rounded send button. */
.chat-composer {
  padding: 12px 28px 10px;
  display: flex; gap: 12px; align-items: flex-end;
}
.chat-input-wrap {
  flex: 1;
  display: flex; align-items: flex-end;
  background: var(--bg-1);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  padding: 4px 6px 4px 16px;
  transition: border-color 160ms ease, box-shadow 160ms ease;
}
.chat-input-wrap:focus-within {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}
.chat-input {
  flex: 1;
  font-family: var(--sans); font-size: 14px; line-height: 1.55;
  background: transparent; color: var(--text-0);
  border: 0; border-radius: 0;
  padding: 10px 4px; resize: none;
  max-height: 140px; min-height: 40px;
}
.chat-input:focus { outline: none; }
.chat-input::placeholder { color: var(--text-3); }
/* Rounded send button — accent pill, icon + label. */
.chat-send {
  display: inline-flex; align-items: center; gap: 7px;
  font-family: var(--sans); font-size: 13px; font-weight: 600;
  letter-spacing: 0.02em;
  color: var(--accent-fg); background: var(--accent);
  border: 1px solid var(--accent);
  border-radius: var(--r-pill, 999px);
  padding: 10px 18px; cursor: pointer; flex-shrink: 0;
  align-self: flex-end; margin-bottom: 1px;
  transition: filter 150ms ease, transform 120ms ease, opacity 150ms ease,
    box-shadow 150ms ease;
}
.chat-send svg { width: 15px; height: 15px; display: block; }
.chat-send:hover:not(:disabled) {
  filter: brightness(1.06);
  box-shadow: var(--shadow-accent);
}
.chat-send:active:not(:disabled) { transform: scale(0.97); }
.chat-send:focus-visible {
  outline: none; box-shadow: 0 0 0 3px var(--accent-soft);
}
.chat-send:disabled { opacity: 0.45; cursor: not-allowed; }

/* Hint line — quiet, mono, beneath the composer. */
.chat-hint {
  font-family: var(--mono); font-size: 10px; color: var(--text-3);
  letter-spacing: 0.04em; padding: 4px 28px 14px;
}

@keyframes chat-bubble-in {
  from { opacity: 0; transform: translateY(8px) scale(0.985); }
  to   { opacity: 1; transform: translateY(0) scale(1); }
}
@keyframes chat-blink {
  0%, 100% { opacity: 0.25; transform: scale(0.85); }
  50%      { opacity: 1; transform: scale(1); }
}

@media (max-width: 600px) {
  .chat-view-hdr { padding: 18px 16px 12px; }
  .chat-scroll { padding: 10px 16px 8px; }
  .chat-composer { padding: 10px 16px; }
  .chat-hint { padding: 4px 16px 12px; }
  .chat-msg { max-width: 90%; }
  .chat-send { padding: 10px 14px; }
}

/* Respect reduced motion — disable entrance/transform/pulse animations. */
@media (prefers-reduced-motion: reduce) {
  .chat-scroll { scroll-behavior: auto; }
  .chat-msg, .chat-thinking { animation: none; }
  .chat-thinking-dots span { animation: none; opacity: 0.7; transform: none; }
  .chat-send:active:not(:disabled) { transform: none; }
}
`;
  document.head.appendChild(style);
}

/** Small DOM helper. */
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

const SVG_NS = "http://www.w3.org/2000/svg";

// Icon path-`d` strings (24×24 viewBox). Kept as data so we build the SVG with
// namespaced DOM nodes — no innerHTML, no untrusted text.
const ICON_SEND =
  "M3.4 20.4 21 12 3.4 3.6 3.4 10l12 2-12 2z"; // paper-plane glyph
const ICON_CHAT =
  "M21 11.5a8.38 8.38 0 0 1-8.5 8.5 8.5 8.5 0 0 1-3.8-.9L3 21l1.9-5.7A8.38 8.38 0 0 1 4 11.5 8.5 8.5 0 0 1 12.5 3 8.38 8.38 0 0 1 21 11.5z"; // speech bubble

/**
 * Build a small inline SVG icon with safe namespaced DOM (no innerHTML).
 * @param {string} d  path data
 * @returns {SVGElement}
 */
function svgIcon(d) {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "1.7");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  const path = document.createElementNS(SVG_NS, "path");
  path.setAttribute("d", d);
  svg.appendChild(path);
  return svg;
}

/**
 * Mount the chat view into `container`.
 *
 * @param {Element} container
 * @param {{sessionId?: string, api?: Function, navigate?: Function}} ctx
 * @returns {() => void} cleanup
 */
export function mount(container, ctx = {}) {
  ensureStyles();
  container.textContent = "";

  const api = typeof ctx.api === "function" ? ctx.api : null;
  const chatSessionId = chatSessionIdFor(ctx.sessionId);
  const offsetKey = LS_OFFSET_PREFIX + chatSessionId;

  // --- Restore the reply cursor so a remount doesn't replay old answers. ---
  let since = 0;
  try {
    const stored = window.localStorage.getItem(offsetKey);
    if (stored != null) since = Math.max(0, parseInt(stored, 10) || 0);
  } catch (_) {
    /* localStorage may be unavailable */
  }

  let destroyed = false;
  let pollTimer = null;
  let thinking = false;
  let pendingReplies = 0; // user turns awaiting an answer

  // --- Layout ---------------------------------------------------------------
  // `.rise` is the shared MONO entrance (motion.css); harmless if absent.
  const root = el("div", "chat-view rise");

  const hdr = el("div", "chat-view-hdr");
  hdr.appendChild(el("span", "section-title", "Manager Chat"));
  const note = el("div", "chat-memory-note");
  note.appendChild(el("span", "chat-memory-dot"));
  note.appendChild(
    el("span", null, "per-session memory — the orchestrator remembers this conversation"),
  );
  hdr.appendChild(note);
  root.appendChild(hdr);

  const scroll = el("div", "chat-scroll");
  root.appendChild(scroll);

  // Empty placeholder lives inside the scroll area until the first turn.
  const empty = el("div", "chat-empty");
  const glyph = el("div", "chat-empty-glyph");
  glyph.appendChild(svgIcon(ICON_CHAT));
  empty.appendChild(glyph);
  empty.appendChild(el("strong", null, "Ask the orchestrator anything"));
  empty.appendChild(
    el(
      "span",
      "chat-empty-sub",
      "status, quality, what each agent is doing, why a task stalled. " +
        "Replies stream back as the run answers. Memory is kept for this session.",
    ),
  );
  scroll.appendChild(empty);

  // Composer — pill-shaped input wrap + a rounded accent send button.
  const composer = el("div", "chat-composer");
  const inputWrap = el("div", "chat-input-wrap");
  const input = document.createElement("textarea");
  input.className = "chat-input";
  input.rows = 1;
  input.placeholder = api
    ? "Message the orchestrator…  (Enter to send, Shift+Enter for newline)"
    : "Chat unavailable in this context";
  input.setAttribute("aria-label", "Message the orchestrator");
  inputWrap.appendChild(input);
  const send = el("button", "chat-send");
  send.type = "button";
  send.setAttribute("aria-label", "Send message");
  send.appendChild(el("span", null, "Send"));
  send.appendChild(svgIcon(ICON_SEND));
  composer.appendChild(inputWrap);
  composer.appendChild(send);
  root.appendChild(composer);

  root.appendChild(
    el(
      "div",
      "chat-hint",
      'Tip: try "status", "what is each agent doing?", or "why is this taking long?"',
    ),
  );

  container.appendChild(root);

  // --- Rendering helpers ----------------------------------------------------
  function removeEmpty() {
    if (empty.parentNode) empty.remove();
  }

  function scrollToBottom() {
    requestAnimationFrame(() => {
      scroll.scrollTop = scroll.scrollHeight;
    });
  }

  function appendMessage(role, text) {
    removeEmpty();
    const msg = el("div", "chat-msg " + (role === "user" ? "from-user" : "from-orch"));
    msg.appendChild(el("span", "chat-role", role === "user" ? "you" : "orchestrator"));
    // textContent escapes; ANSI stripped for server turns.
    msg.appendChild(el("div", "chat-bubble", stripAnsi(text)));
    // Keep the thinking indicator (if any) as the last child.
    const indicator = scroll.querySelector(".chat-thinking");
    if (indicator) scroll.insertBefore(msg, indicator);
    else scroll.appendChild(msg);
    scrollToBottom();
  }

  function showThinking() {
    if (thinking) return;
    thinking = true;
    const t = el("div", "chat-thinking");
    t.appendChild(el("span", null, "orchestrator is thinking"));
    const dots = el("span", "chat-thinking-dots");
    dots.appendChild(el("span"));
    dots.appendChild(el("span"));
    dots.appendChild(el("span"));
    t.appendChild(dots);
    scroll.appendChild(t);
    scrollToBottom();
  }

  function hideThinking() {
    thinking = false;
    const t = scroll.querySelector(".chat-thinking");
    if (t) t.remove();
  }

  function showError(message) {
    const prev = scroll.querySelector(".chat-error");
    if (prev) prev.remove();
    removeEmpty();
    scroll.appendChild(el("div", "chat-error", message));
    scrollToBottom();
  }

  function clearError() {
    const prev = scroll.querySelector(".chat-error");
    if (prev) prev.remove();
  }

  function persistOffset() {
    try {
      window.localStorage.setItem(offsetKey, String(since));
    } catch (_) {
      /* ignore */
    }
  }

  // --- No active run guard --------------------------------------------------
  if (!api) {
    removeEmpty();
    const inactive = el("div", "chat-inactive");
    inactive.appendChild(el("span", "chat-inactive-title", "No session"));
    inactive.appendChild(
      document.createTextNode(
        "Chat needs a running orchestrator session. Start or select a run, then return here.",
      ),
    );
    scroll.appendChild(inactive);
    input.disabled = true;
    send.disabled = true;
    return () => {
      destroyed = true;
    };
  }

  // --- Networking -----------------------------------------------------------
  async function poll() {
    if (destroyed) return;
    try {
      const res = await api(
        "/chat/replies?chat_session_id=" +
          encodeURIComponent(chatSessionId) +
          "&since=" +
          since,
      );
      if (destroyed) return;
      if (!res || !res.ok) {
        // A missing session/run surfaces as a non-OK status; treat softly.
        return;
      }
      const data = await res.json();
      if (destroyed || !data) return;
      const replies = Array.isArray(data.replies) ? data.replies : [];
      if (replies.length) {
        clearError();
        for (const r of replies) {
          const answer = r && (r.answer != null ? r.answer : r.text);
          if (answer != null && String(answer).length) {
            appendMessage("orchestrator", answer);
          }
          if (pendingReplies > 0) pendingReplies -= 1;
        }
        if (pendingReplies <= 0) hideThinking();
      }
      if (typeof data.next === "number" && data.next >= since) {
        since = data.next;
        persistOffset();
      }
    } catch (_) {
      // Transient network error — keep polling; surface only on the send path.
    }
  }

  async function doSend() {
    const text = input.value.trim();
    if (!text || destroyed) return;
    clearError();
    appendMessage("user", text);
    input.value = "";
    autoGrow();
    pendingReplies += 1;
    showThinking();
    send.disabled = true;
    try {
      const res = await api("/control/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, chat_session_id: chatSessionId }),
      });
      if (destroyed) return;
      if (!res || !res.ok) {
        let detail = "";
        try {
          const j = await res.json();
          detail = j && (j.detail || j.error) ? " — " + (j.detail || j.error) : "";
        } catch (_) {
          /* non-JSON body */
        }
        pendingReplies = Math.max(0, pendingReplies - 1);
        if (pendingReplies <= 0) hideThinking();
        if (res && res.status === 404) {
          showError(
            "No active run for this session. Start or select a running session to chat.",
          );
        } else {
          showError("Could not send message" + detail + ". Is a session running?");
        }
        return;
      }
      // Success: kick an immediate poll so the answer arrives promptly.
      poll();
    } catch (_) {
      if (destroyed) return;
      pendingReplies = Math.max(0, pendingReplies - 1);
      if (pendingReplies <= 0) hideThinking();
      showError("Network error sending message. Check that the dashboard is reachable.");
    } finally {
      if (!destroyed) {
        send.disabled = false;
        input.focus();
      }
    }
  }

  // --- Input behaviour ------------------------------------------------------
  function autoGrow() {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 140) + "px";
  }

  function onKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      doSend();
    }
  }

  input.addEventListener("input", autoGrow);
  input.addEventListener("keydown", onKeyDown);
  send.addEventListener("click", doSend);

  // --- Boot -----------------------------------------------------------------
  // Initial poll picks up any replies queued since the last visit; the interval
  // then keeps the conversation live.
  poll();
  pollTimer = window.setInterval(poll, POLL_INTERVAL_MS);

  requestAnimationFrame(() => {
    if (!destroyed) input.focus();
  });

  // --- Cleanup --------------------------------------------------------------
  return function cleanup() {
    destroyed = true;
    if (pollTimer != null) {
      window.clearInterval(pollTimer);
      pollTimer = null;
    }
    input.removeEventListener("input", autoGrow);
    input.removeEventListener("keydown", onKeyDown);
    send.removeEventListener("click", doSend);
    // Persist where we are so a re-mount doesn't replay history.
    persistOffset();
  };
}

export default { mount, stripAnsi, chatSessionIdFor };
