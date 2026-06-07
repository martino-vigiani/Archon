import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const modulePath = "../../orchestrator/static/js/views/sessions.js";

/** Build a ctx whose api() resolves to a Response-like object. */
function makeCtx({ sessions = [], navigate = vi.fn(), stopImpl } = {}) {
  const api = vi.fn((path, opts) => {
    if (path === "/sessions") {
      return Promise.resolve({ json: () => Promise.resolve(sessions) });
    }
    if (/\/sessions\/.+\/stop$/.test(path)) {
      if (stopImpl) return stopImpl(path, opts);
      return Promise.resolve({ json: () => Promise.resolve({ ok: true }) });
    }
    return Promise.resolve({ json: () => Promise.resolve({}) });
  });
  return { sessionId: "", api, navigate, ws: vi.fn() };
}

const SAMPLE = [
  {
    session_id: "20260606-100000-build-rest-api",
    goal: "Build a REST API for habit tracking",
    project_path: "/Users/dev/Apps/Habits",
    status: "running",
    started_at: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
  },
  {
    session_id: "20260605-090000-meditation",
    goal: "Create a meditation app",
    project_path: null,
    status: "completed",
    started_at: new Date(Date.now() - 26 * 60 * 60 * 1000).toISOString(),
  },
];

describe("sessions view (F14)", () => {
  let container;

  beforeEach(() => {
    vi.useRealTimers(); // this view uses setInterval + awaited fetch
    document.body.innerHTML = "";
    container = document.createElement("div");
    document.body.appendChild(container);
    try {
      localStorage.clear();
    } catch {
      /* ignore */
    }
  });

  afterEach(() => {
    vi.restoreAllMocks();
    // Restore fake timers so the shared setup.js afterEach
    // (vi.runOnlyPendingTimers) has a mocked clock to drain.
    vi.useFakeTimers();
  });

  it("renders a card per session with goal, status pill, time and path", async () => {
    const { mount } = await import(modulePath);
    const ctx = makeCtx({ sessions: SAMPLE });

    const cleanup = mount(container, ctx);
    await vi.waitFor(() =>
      expect(container.querySelectorAll(".session-card").length).toBe(2)
    );

    expect(ctx.api).toHaveBeenCalledWith("/sessions");

    const cards = container.querySelectorAll(".session-card");
    expect(cards[0].textContent).toContain("Build a REST API for habit tracking");

    // Status pills carry the semantic tone classes.
    expect(container.querySelector(".session-pill.tone-ok")).toBeTruthy(); // running
    expect(container.querySelectorAll(".session-pill")[1].textContent).toContain(
      "completed"
    );

    // Relative time + project path surfaced.
    expect(cards[0].textContent.toLowerCase()).toContain("ago");
    expect(cards[0].textContent).toContain("/Users/dev/Apps/Habits");

    cleanup();
  });

  it("escapes goal/path content (no XSS injection)", async () => {
    const { mount } = await import(modulePath);
    const ctx = makeCtx({
      sessions: [
        {
          session_id: "x",
          goal: "<img src=x onerror=alert(1)>",
          project_path: "/tmp/<b>evil</b>",
          status: "failed",
          started_at: new Date().toISOString(),
        },
      ],
    });

    const cleanup = mount(container, ctx);
    await vi.waitFor(() =>
      expect(container.querySelector(".session-card")).toBeTruthy()
    );

    // No injected <img>/<b> element should exist in the card body.
    expect(container.querySelector(".session-card img")).toBeNull();
    expect(container.querySelector(".session-goal b")).toBeNull();
    expect(container.querySelector(".session-goal").textContent).toContain(
      "<img src=x onerror=alert(1)>"
    );
    cleanup();
  });

  it("selecting a session persists localStorage and navigates to #/", async () => {
    const { mount } = await import(modulePath);
    const navigate = vi.fn();
    const ctx = makeCtx({ sessions: SAMPLE, navigate });

    const cleanup = mount(container, ctx);
    await vi.waitFor(() =>
      expect(container.querySelectorAll(".session-card").length).toBe(2)
    );

    container.querySelector('[data-select]').click();

    expect(localStorage.getItem("archon.session")).toBe(
      "20260606-100000-build-rest-api"
    );
    expect(navigate).toHaveBeenCalledWith("#/");
    cleanup();
  });

  it("New run button navigates to #/new", async () => {
    const { mount } = await import(modulePath);
    const navigate = vi.fn();
    const ctx = makeCtx({ sessions: SAMPLE, navigate });

    const cleanup = mount(container, ctx);
    container.querySelector(".sessions-new-btn").click();
    expect(navigate).toHaveBeenCalledWith("#/new");
    cleanup();
  });

  it("shows a Stop action only for active runs and POSTs the stop endpoint", async () => {
    const { mount } = await import(modulePath);
    const stopImpl = vi.fn(() =>
      Promise.resolve({ json: () => Promise.resolve({ ok: true }) })
    );
    const ctx = makeCtx({ sessions: SAMPLE, stopImpl });

    const cleanup = mount(container, ctx);
    await vi.waitFor(() =>
      expect(container.querySelectorAll(".session-card").length).toBe(2)
    );

    const stopBtns = container.querySelectorAll(".session-stop-btn");
    expect(stopBtns.length).toBe(1); // only the running session

    stopBtns[0].click();
    expect(stopImpl).toHaveBeenCalledWith(
      "/sessions/20260606-100000-build-rest-api/stop",
      { method: "POST" }
    );
    cleanup();
  });

  it("renders an empty state when there are no sessions", async () => {
    const { mount } = await import(modulePath);
    const ctx = makeCtx({ sessions: [] });

    const cleanup = mount(container, ctx);
    await vi.waitFor(() =>
      expect(container.querySelector(".sessions-empty")).toBeTruthy()
    );
    expect(container.textContent).toContain("No runs yet");
    cleanup();
  });

  it("cleanup stops the auto-refresh timer", async () => {
    const { mount } = await import(modulePath);
    const ctx = makeCtx({ sessions: SAMPLE });

    const cleanup = mount(container, ctx);
    await vi.waitFor(() =>
      expect(container.querySelectorAll(".session-card").length).toBe(2)
    );

    const callsBefore = ctx.api.mock.calls.length;
    cleanup();
    // Wait past one refresh interval; no further /sessions calls.
    await new Promise((r) => setTimeout(r, 60));
    const sessionCalls = ctx.api.mock.calls.filter((c) => c[0] === "/sessions").length;
    expect(ctx.api.mock.calls.length).toBe(callsBefore);
    expect(sessionCalls).toBeGreaterThanOrEqual(1);
    expect(container.innerHTML).toBe("");
  });
});
