import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { mount } from "../../orchestrator/static/js/views/files.js";

/* Helper: build a ctx whose api() resolves to the given file-event payload. */
function makeCtx(events) {
  const api = vi.fn(async () => ({
    ok: true,
    status: 200,
    json: async () => events,
  }));
  return { ctx: { sessionId: "s1", api, navigate: vi.fn() }, api };
}

/* Flush the microtask queue so the awaited fetch in load() resolves while
   fake timers are active. */
async function flush() {
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
}

describe("files view", () => {
  let container;
  let cleanup;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.appendChild(container);
  });

  afterEach(() => {
    if (cleanup) cleanup();
    cleanup = null;
  });

  it("renders worker groups, file rows, action tags and counts", async () => {
    const events = [
      { path: "src/app/main.py", worker: "w1", action: "created", ts: "2026-06-06T10:00:00Z" },
      { path: "src/app/util.py", worker: "w1", action: "modified", ts: "2026-06-06T10:01:00Z" },
      { path: "README.md", worker: "w2", action: "created", ts: "2026-06-06T10:02:00Z" },
    ];
    const { ctx, api } = makeCtx(events);

    cleanup = mount(container, ctx);
    await flush();

    // api was called against the /files endpoint.
    expect(api).toHaveBeenCalledWith("/files");

    // Header totals reflect counts.
    const totals = container.querySelector('[data-fv="totals"]');
    expect(totals.textContent).toContain("3 files");
    expect(totals.textContent).toContain("2 workers");

    // Two worker groups, w1 (2 files) ordered before w2 (1 file).
    const groups = container.querySelectorAll(".fv-group");
    expect(groups).toHaveLength(2);
    expect(groups[0].getAttribute("data-worker")).toBe("w1");
    expect(groups[1].getAttribute("data-worker")).toBe("w2");

    // Worker badges are present and escaped via textContent.
    const badges = container.querySelectorAll(".fv-badge");
    expect([...badges].map((b) => b.textContent)).toEqual(["w1", "w2"]);

    // Three file rows total; action tags present.
    const files = container.querySelectorAll(".fv-file");
    expect(files).toHaveLength(3);
    expect(container.querySelector(".fv-action-created")).not.toBeNull();
    expect(container.querySelector(".fv-action-modified")).not.toBeNull();

    // w1 group count chip says "2 files".
    expect(groups[0].querySelector(".fv-group-count").textContent).toBe("2 files");
  });

  it("shows an empty state when there are no files", async () => {
    const { ctx } = makeCtx([]);
    cleanup = mount(container, ctx);
    await flush();

    expect(container.querySelector(".fv-empty")).not.toBeNull();
    expect(container.querySelector(".fv-group")).toBeNull();
  });

  it("shows an error state when the request fails", async () => {
    const api = vi.fn(async () => ({ ok: false, status: 500, json: async () => ({}) }));
    cleanup = mount(container, { sessionId: "s1", api });
    await flush();

    expect(container.querySelector(".fv-error")).not.toBeNull();
  });

  it("filters file rows by path", async () => {
    const events = [
      { path: "src/app/main.py", worker: "w1", action: "created", ts: "2026-06-06T10:00:00Z" },
      { path: "docs/guide.md", worker: "w2", action: "created", ts: "2026-06-06T10:01:00Z" },
    ];
    const { ctx } = makeCtx(events);
    cleanup = mount(container, ctx);
    await flush();

    expect(container.querySelectorAll(".fv-file")).toHaveLength(2);

    const search = container.querySelector('[data-fv="search"]');
    search.value = "docs";
    search.dispatchEvent(new Event("input"));

    const files = container.querySelectorAll(".fv-file");
    expect(files).toHaveLength(1);
    expect(files[0].querySelector(".fv-file-name").textContent).toBe("guide.md");
  });

  it("strips ANSI escapes from server text and writes via textContent", async () => {
    const events = [
      {
        path: "\x1b[31msecret.txt\x1b[0m",
        worker: "\x1b[1mw1\x1b[0m",
        action: "created",
        ts: "2026-06-06T10:00:00Z",
      },
    ];
    const { ctx } = makeCtx(events);
    cleanup = mount(container, ctx);
    await flush();

    const name = container.querySelector(".fv-file-name");
    expect(name.textContent).toBe("secret.txt");
    // No ESC control byte leaked into the DOM.
    expect(name.textContent).not.toContain("\x1b");
    // Worker badge cleaned too.
    expect(container.querySelector(".fv-badge").textContent).toBe("w1");
  });

  it("returns a cleanup function that removes the view and stops polling", async () => {
    const { ctx, api } = makeCtx([]);
    cleanup = mount(container, ctx);
    await flush();
    const callsAfterMount = api.mock.calls.length;

    cleanup();
    cleanup = null;

    // View removed from the container.
    expect(container.querySelector(".files-view")).toBeNull();

    // Advancing past the poll interval triggers no further fetches.
    vi.advanceTimersByTime(20000);
    await flush();
    expect(api.mock.calls.length).toBe(callsAfterMount);
  });
});
