import { beforeEach, describe, expect, it, vi } from "vitest";

const modulePath = "../../orchestrator/static/js/views/new-run.js";

// Shared setup.js installs fake timers (beforeEach) + tears them down (afterEach).
// Flush awaited fetch/JSON microtasks under fake timers with advanceTimersByTimeAsync(0).
async function flush() {
  await vi.advanceTimersByTimeAsync(0);
  await vi.advanceTimersByTimeAsync(0);
}

function jsonResponse(body, { ok = true, status = 200 } = {}) {
  return {
    ok,
    status,
    headers: { get: (h) => (h.toLowerCase() === "content-type" ? "application/json" : null) },
    json: async () => body,
    text: async () => JSON.stringify(body),
  };
}

function makeCtx({ apiImpl, navigate } = {}) {
  return {
    sessionId: null,
    api: vi.fn(apiImpl || (() => Promise.resolve(jsonResponse({})))),
    ws: vi.fn(),
    navigate: navigate || vi.fn(),
  };
}

describe("views/new-run", () => {
  beforeEach(() => {
    vi.resetModules();
    document.body.innerHTML = "";
    document.head.innerHTML = "";
  });

  it("mounts the expected DOM and browses the working directory on init", async () => {
    const { mount } = await import(modulePath);
    const container = document.createElement("div");
    document.body.appendChild(container);

    const ctx = makeCtx({
      apiImpl: (path) => {
        if (path.startsWith("/dirs")) {
          return Promise.resolve(
            jsonResponse({
              path: "/home/u",
              parent: "/home",
              dirs: ["proj-a", { name: "proj-b", path: "/home/u/proj-b" }],
            }),
          );
        }
        return Promise.resolve(jsonResponse({}));
      },
    });

    const cleanup = mount(container, ctx);
    await flush();

    expect(container.querySelector("#nr-goal")).not.toBeNull();
    expect(container.querySelector("#nr-instructions")).not.toBeNull();
    expect(container.querySelector("#nr-count")).not.toBeNull();
    expect(container.querySelectorAll(".nr-toggle").length).toBe(4);

    const dirRows = container.querySelectorAll(".nr-dir-row");
    expect(dirRows.length).toBe(3); // parent + 2 dirs
    expect(container.querySelector(".nr-dir-path").textContent).toBe("/home/u");
    expect(ctx.api).toHaveBeenCalledWith(
      expect.stringContaining("/dirs?path="),
      expect.objectContaining({ signal: expect.anything() }),
    );

    cleanup();
    expect(container.querySelector(".nr-view")).toBeNull();
  });

  it("previews a roster with editable model/effort/plan cards", async () => {
    const { mount } = await import(modulePath);
    const container = document.createElement("div");
    document.body.appendChild(container);

    const roster = [
      {
        id: "w1",
        lane: "code",
        kind: "code",
        focus: "implementation backbone",
        subagents: ["python-architect"],
        profile: { model_tier: "standard", effort: "high", permission_mode: "bypassPermissions" },
      },
      {
        id: "w2",
        lane: "qa",
        kind: "qa",
        focus: "testing and quality gates",
        subagents: [],
        profile: { model_tier: "deep", effort: "max", permission_mode: "plan" },
      },
    ];

    const ctx = makeCtx({
      apiImpl: (path) => {
        if (path.startsWith("/dirs")) return Promise.resolve(jsonResponse({ path: "/root", parent: null, dirs: [] }));
        if (path.startsWith("/preview-roster")) return Promise.resolve(jsonResponse(roster));
        return Promise.resolve(jsonResponse({}));
      },
    });

    mount(container, ctx);
    await flush();

    container.querySelector("#nr-goal").value = "Build an API";
    const previewBtn = [...container.querySelectorAll("button")].find((b) => b.textContent.includes("Preview"));
    previewBtn.click();
    await flush();

    const cards = container.querySelectorAll(".nr-card");
    expect(cards.length).toBe(2);
    expect(container.querySelector(".nr-card-id").textContent).toBe("w1");
    expect(cards[0].querySelectorAll("select.nr-select").length).toBe(2);
    expect(cards[1].querySelector('input[type="checkbox"]').checked).toBe(true);

    const previewCall = ctx.api.mock.calls.find((c) => c[0].startsWith("/preview-roster"));
    expect(previewCall[0]).toContain("goal=Build");
    expect(previewCall[0]).toContain("agent_count=5");
    expect(previewCall[0]).toContain("dynamic=1");
    expect(previewCall[0]).toContain("testing=1");
  });

  it("validates the goal before launching", async () => {
    const { mount } = await import(modulePath);
    const container = document.createElement("div");
    document.body.appendChild(container);

    const ctx = makeCtx({
      apiImpl: (path) =>
        Promise.resolve(jsonResponse(path.startsWith("/dirs") ? { path: "", parent: null, dirs: [] } : {})),
    });
    mount(container, ctx);
    await flush();

    const launchBtn = [...container.querySelectorAll("button")].find((b) => b.type === "submit");
    launchBtn.click();
    await flush();

    const err = container.querySelector(".nr-error");
    expect(err.hidden).toBe(false);
    expect(err.textContent.toLowerCase()).toContain("goal");
    expect(ctx.api.mock.calls.some((c) => c[0] === "/runs")).toBe(false);
  });

  it("POSTs /runs with the full body and navigates home on success", async () => {
    const { mount } = await import(modulePath);
    const container = document.createElement("div");
    document.body.appendChild(container);

    const navigate = vi.fn();
    const ctx = makeCtx({
      navigate,
      apiImpl: (path) => {
        if (path.startsWith("/dirs"))
          return Promise.resolve(jsonResponse({ path: "/home/u", parent: "/home", dirs: [] }));
        if (path.startsWith("/preview-roster")) return Promise.resolve(jsonResponse([]));
        if (path === "/runs")
          return Promise.resolve(
            jsonResponse({ session_id: "20260606-1200-build-an-api", status: "starting" }, { status: 201 }),
          );
        return Promise.resolve(jsonResponse({}));
      },
    });

    mount(container, ctx);
    await flush();

    container.querySelector("#nr-goal").value = "Build an API";
    container.querySelector("#nr-instructions").value = "Use strict mode";
    container.querySelector("#nr-count").value = "3";

    const launchBtn = [...container.querySelectorAll("button")].find((b) => b.type === "submit");
    launchBtn.click();
    await flush();

    const runCall = ctx.api.mock.calls.find((c) => c[0] === "/runs");
    expect(runCall).toBeDefined();
    expect(runCall[1].method).toBe("POST");
    const body = JSON.parse(runCall[1].body);
    expect(body.goal).toBe("Build an API");
    expect(body.instructions).toBe("Use strict mode");
    expect(body.agent_count).toBe(3);
    expect(body.project_path).toBe("/home/u");
    expect(body).toHaveProperty("dynamic_agents");
    expect(body).toHaveProperty("model_tiering");
    expect(body).toHaveProperty("effort_dial");
    expect(body).toHaveProperty("no_testing");
    expect(body).toHaveProperty("roster_overrides");

    expect(container.querySelector(".nr-ok").hidden).toBe(false);
    expect(container.querySelector(".nr-ok").textContent).toContain("20260606-1200-build-an-api");

    // navigate('#/') fires after the deferred timeout
    await vi.advanceTimersByTimeAsync(500);
    expect(navigate).toHaveBeenCalledWith("#/");
  });

  it("surfaces a server error on launch failure", async () => {
    const { mount } = await import(modulePath);
    const container = document.createElement("div");
    document.body.appendChild(container);

    const ctx = makeCtx({
      apiImpl: (path) => {
        if (path.startsWith("/dirs")) return Promise.resolve(jsonResponse({ path: "/x", parent: null, dirs: [] }));
        if (path === "/runs")
          return Promise.resolve(jsonResponse({ detail: "goal too short" }, { ok: false, status: 400 }));
        return Promise.resolve(jsonResponse({}));
      },
    });
    mount(container, ctx);
    await flush();

    container.querySelector("#nr-goal").value = "x";
    const launchBtn = [...container.querySelectorAll("button")].find((b) => b.type === "submit");
    launchBtn.click();
    await flush();

    const err = container.querySelector(".nr-error");
    expect(err.hidden).toBe(false);
    expect(err.textContent).toContain("goal too short");
  });
});
