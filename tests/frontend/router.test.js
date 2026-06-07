import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const routerModulePath = "../../orchestrator/static/js/router.js";

/** Fresh import of the router module (it holds module-level state). */
async function loadRouter() {
  vi.resetModules();
  return import(routerModulePath);
}

function resetLocationHash() {
  // jsdom: clearing the hash without reloading.
  history.replaceState(null, "", "/");
}

describe("router", () => {
  beforeEach(() => {
    resetLocationHash();
    document.body.innerHTML = '<div id="app"></div>';
  });

  afterEach(() => {
    resetLocationHash();
  });

  it("mounts the route matching the current hash on start", async () => {
    const { registerRoute, start, stop } = await loadRouter();
    const container = document.getElementById("app");

    registerRoute("#/", (c) => {
      c.textContent = "home";
    });
    registerRoute("#/new", (c) => {
      c.textContent = "new-run";
    });

    location.hash = "#/new";
    start({ container, ctx: {}, fallback: "#/" });

    expect(container.textContent).toBe("new-run");
    stop();
  });

  it("passes ctx and container to the mount fn", async () => {
    const { registerRoute, start, stop } = await loadRouter();
    const container = document.getElementById("app");
    const ctx = { sessionId: "abc", api: () => {} };
    const mount = vi.fn();

    registerRoute("#/", mount);
    start({ container, ctx, fallback: "#/" });

    expect(mount).toHaveBeenCalledTimes(1);
    expect(mount).toHaveBeenCalledWith(container, ctx);
    stop();
  });

  it("falls back to the fallback route for an unknown hash", async () => {
    const { registerRoute, start, stop } = await loadRouter();
    const container = document.getElementById("app");

    registerRoute("#/", (c) => {
      c.textContent = "fallback-home";
    });

    location.hash = "#/does-not-exist";
    start({ container, ctx: {}, fallback: "#/" });

    expect(container.textContent).toBe("fallback-home");
    stop();
  });

  it("runs the previous view's cleanup before mounting the next on navigate", async () => {
    const { registerRoute, start, navigate, stop } = await loadRouter();
    const container = document.getElementById("app");
    const cleanup = vi.fn();

    registerRoute("#/", (c) => {
      c.textContent = "home";
      return cleanup;
    });
    registerRoute("#/new", (c) => {
      c.textContent = "new-run";
    });

    start({ container, ctx: {}, fallback: "#/" });
    expect(container.textContent).toBe("home");
    expect(cleanup).not.toHaveBeenCalled();

    navigate("#/new");

    expect(cleanup).toHaveBeenCalledTimes(1);
    expect(container.textContent).toBe("new-run");
    stop();
  });

  it("navigate updates location.hash and triggers the matching mount", async () => {
    const { registerRoute, start, navigate, stop } = await loadRouter();
    const container = document.getElementById("app");

    registerRoute("#/", (c) => {
      c.textContent = "home";
    });
    registerRoute("#/sessions", (c) => {
      c.textContent = "sessions";
    });

    start({ container, ctx: {}, fallback: "#/" });
    navigate("#/sessions");

    expect(location.hash).toBe("#/sessions");
    expect(container.textContent).toBe("sessions");
    stop();
  });

  it("reacts to a raw hashchange event", async () => {
    const { registerRoute, start, stop } = await loadRouter();
    const container = document.getElementById("app");

    registerRoute("#/", (c) => {
      c.textContent = "home";
    });
    registerRoute("#/chat", (c) => {
      c.textContent = "chat";
    });

    start({ container, ctx: {}, fallback: "#/" });
    expect(container.textContent).toBe("home");

    location.hash = "#/chat";
    window.dispatchEvent(new Event("hashchange"));

    expect(container.textContent).toBe("chat");
    stop();
  });

  it("normalizes hashes (query strings stripped, leading slash added)", async () => {
    const { registerRoute, normalizeHash, start, stop } = await loadRouter();
    const container = document.getElementById("app");

    expect(normalizeHash("#/files?session=x")).toBe("#/files");
    expect(normalizeHash("/files")).toBe("#/files");
    expect(normalizeHash("")).toBe("#/");
    expect(normalizeHash("#")).toBe("#/");

    registerRoute("#/files", (c) => {
      c.textContent = "files";
    });
    registerRoute("#/", () => {});

    location.hash = "#/files?session=x";
    start({ container, ctx: {}, fallback: "#/" });
    expect(container.textContent).toBe("files");
    stop();
  });

  it("stop() removes the listener and runs cleanup", async () => {
    const { registerRoute, start, stop } = await loadRouter();
    const container = document.getElementById("app");
    const cleanup = vi.fn();

    registerRoute("#/", () => cleanup);
    start({ container, ctx: {}, fallback: "#/" });

    stop();
    expect(cleanup).toHaveBeenCalledTimes(1);

    // After stop, a hashchange must not mount anything.
    registerRoute("#/other", (c) => {
      c.textContent = "should-not-mount";
    });
    location.hash = "#/other";
    window.dispatchEvent(new Event("hashchange"));
    expect(container.textContent).not.toBe("should-not-mount");
  });
});
