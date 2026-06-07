import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const modulePath = "../../orchestrator/static/js/views/chat.js";
const ESC = String.fromCharCode(27);

/** Build a fetch-style Response stub. */
function jsonResponse(body, { ok = true, status = 200 } = {}) {
  return { ok, status, json: async () => body };
}

/**
 * A controllable `ctx.api` mock. Records calls and lets a test script the
 * replies returned by the polling endpoint.
 */
function makeCtx({ sessionId = "sid-1", replyQueue = [] } = {}) {
  const calls = { chat: [], replies: [] };
  const api = vi.fn(async (path, opts) => {
    if (path.startsWith("/control/chat")) {
      calls.chat.push({ path, opts });
      return jsonResponse({ ok: true, action: "chat" });
    }
    if (path.startsWith("/chat/replies")) {
      calls.replies.push({ path, opts });
      const next = replyQueue.shift();
      return jsonResponse(next || { replies: [], next: 0 });
    }
    return jsonResponse({}, { ok: false, status: 404 });
  });
  return { ctx: { sessionId, api }, calls };
}

describe("views/chat", () => {
  let container;

  // NOTE: the shared tests/frontend/setup.js already calls vi.useFakeTimers()
  // in its global beforeEach and restores them in afterEach — do not manage
  // timers here or the two will fight (real-timers + runOnlyPendingTimers).
  beforeEach(() => {
    try {
      window.localStorage.clear();
    } catch (_) {
      /* ignore */
    }
    container = document.createElement("div");
    document.body.appendChild(container);
  });

  afterEach(() => {
    document.querySelectorAll("style#archon-chat-view-style").forEach((n) => n.remove());
  });

  it("exports stripAnsi and chatSessionIdFor helpers", async () => {
    const { stripAnsi, chatSessionIdFor } = await import(modulePath);
    expect(stripAnsi(ESC + "[31mhi" + ESC + "[0m")).toBe("hi");
    expect(stripAnsi(null)).toBe("");
    expect(chatSessionIdFor("abc")).toBe("dashabc");
    expect(chatSessionIdFor(null)).toBe("dash");
  });

  it("mount builds the expected chat DOM and starts polling", async () => {
    const { mount } = await import(modulePath);
    const { ctx, calls } = makeCtx();

    const cleanup = mount(container, ctx);

    // Core structure exists.
    expect(container.querySelector(".chat-view")).not.toBeNull();
    expect(container.querySelector(".chat-scroll")).not.toBeNull();
    expect(container.querySelector("textarea.chat-input")).not.toBeNull();
    expect(container.querySelector("button.chat-send")).not.toBeNull();
    // Memory note is surfaced to the user.
    expect(container.querySelector(".chat-memory-note").textContent).toMatch(/memory/i);
    // Empty state is shown initially.
    expect(container.querySelector(".chat-empty")).not.toBeNull();

    // An immediate poll fired against the replies endpoint with the right id.
    expect(calls.replies.length).toBeGreaterThanOrEqual(1);
    expect(calls.replies[0].path).toContain("/chat/replies?chat_session_id=dashsid-1");
    expect(calls.replies[0].path).toContain("since=0");

    cleanup();
  });

  it("send posts to /control/chat, shows thinking, then renders the ANSI-stripped reply", async () => {
    const { mount } = await import(modulePath);
    const { ctx, calls } = makeCtx({
      // First poll (boot): nothing. Second poll (post-send): an answer.
      replyQueue: [
        { replies: [], next: 0 },
        { replies: [{ ts: "t", query: "hi", answer: ESC + "[32mall good" + ESC + "[0m" }], next: 1 },
      ],
    });

    const cleanup = mount(container, ctx);
    await vi.advanceTimersByTimeAsync(0); // flush boot poll

    const input = container.querySelector("textarea.chat-input");
    const send = container.querySelector("button.chat-send");
    input.value = "hi there";
    send.click();
    await vi.advanceTimersByTimeAsync(0); // flush send + immediate poll

    // User turn rendered.
    const userMsg = container.querySelector(".chat-msg.from-user .chat-bubble");
    expect(userMsg).not.toBeNull();
    expect(userMsg.textContent).toBe("hi there");

    // POST went out with the correct body shape.
    expect(calls.chat).toHaveLength(1);
    expect(calls.chat[0].opts.method).toBe("POST");
    const body = JSON.parse(calls.chat[0].opts.body);
    expect(body).toEqual({ text: "hi there", chat_session_id: "dashsid-1" });

    // Orchestrator reply rendered, ANSI stripped.
    const orchMsg = container.querySelector(".chat-msg.from-orch .chat-bubble");
    expect(orchMsg).not.toBeNull();
    expect(orchMsg.textContent).toBe("all good");

    // Thinking indicator cleared once the reply arrived.
    expect(container.querySelector(".chat-thinking")).toBeNull();

    cleanup();
  });

  it("escapes user content (no HTML injection)", async () => {
    const { mount } = await import(modulePath);
    const { ctx } = makeCtx();
    const cleanup = mount(container, ctx);
    await vi.advanceTimersByTimeAsync(0);

    const input = container.querySelector("textarea.chat-input");
    input.value = "<img src=x onerror=alert(1)>";
    container.querySelector("button.chat-send").click();
    await vi.advanceTimersByTimeAsync(0);

    const bubble = container.querySelector(".chat-msg.from-user .chat-bubble");
    expect(bubble.querySelector("img")).toBeNull();
    expect(bubble.textContent).toBe("<img src=x onerror=alert(1)>");

    cleanup();
  });

  it("shows a guidance message and disables input when no api is available", async () => {
    const { mount } = await import(modulePath);
    const cleanup = mount(container, { sessionId: "sid-1" }); // no api

    expect(container.querySelector(".chat-inactive")).not.toBeNull();
    expect(container.querySelector(".chat-inactive").textContent).toMatch(/running/i);
    expect(container.querySelector("textarea.chat-input").disabled).toBe(true);
    expect(container.querySelector("button.chat-send").disabled).toBe(true);

    cleanup();
  });

  it("cleanup stops the poll timer", async () => {
    const { mount } = await import(modulePath);
    const { ctx, calls } = makeCtx();
    const cleanup = mount(container, ctx);
    await vi.advanceTimersByTimeAsync(0);

    const afterBoot = calls.replies.length;
    cleanup();
    await vi.advanceTimersByTimeAsync(10000); // would fire several intervals if alive

    expect(calls.replies.length).toBe(afterBoot);
  });
});
