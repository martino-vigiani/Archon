import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const modulePath = "../../orchestrator/static/js/views/workspace.js";

// jsdom has no real 2D canvas — provide a no-op stub so draw() doesn't throw.
function stubCanvas() {
  const noop = () => {};
  const ctx = {
    setTransform: noop,
    clearRect: noop,
    beginPath: noop,
    moveTo: noop,
    lineTo: noop,
    arc: noop,
    arcTo: noop,
    closePath: noop,
    fill: noop,
    stroke: noop,
    fillText: noop,
    setLineDash: noop,
    fillStyle: "",
    strokeStyle: "",
    lineWidth: 1,
    globalAlpha: 1,
    font: "",
    textAlign: "",
    textBaseline: "",
  };
  HTMLCanvasElement.prototype.getContext = () => ctx;
}

function graphResponse(graph) {
  return {
    ok: true,
    status: 200,
    json: () => Promise.resolve(graph),
  };
}

function makeCtx(graph) {
  const api = vi.fn((path) => {
    if (path === "/workspace-graph") return Promise.resolve(graphResponse(graph));
    return Promise.resolve(graphResponse({ nodes: [], edges: [] }));
  });
  return { ctx: { sessionId: "s1", api, ws: vi.fn(), navigate: vi.fn() }, api };
}

describe("workspace view", () => {
  beforeEach(() => {
    stubCanvas();
  });
  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("mount builds the canvas, header flag and legend scaffold", async () => {
    const mod = await import(modulePath);
    const container = document.createElement("div");
    document.body.appendChild(container);

    const { ctx } = makeCtx({ nodes: [], edges: [] });
    const cleanup = mod.mount(container, ctx);

    expect(container.querySelector('[data-view="workspace"]')).toBeTruthy();
    expect(container.querySelector("canvas")).toBeTruthy();
    // experimental flag present
    expect(container.querySelector(".ws-flag").textContent).toBe("experimental");
    // legend lists all node + edge kinds
    const legendText = container.querySelector(".ws-legend").textContent;
    for (const word of ["agent", "file", "contract", "creates", "provides", "depends"]) {
      expect(legendText).toContain(word);
    }

    cleanup();
  });

  it("fetches /workspace-graph and reflects node counts; cleanup removes the view", async () => {
    const mod = await import(modulePath);
    const container = document.createElement("div");
    document.body.appendChild(container);

    const graph = {
      nodes: [
        { id: "agent:w1", type: "agent", worker: "w1", label: "w1" },
        { id: "file:/a.py", type: "file", worker: "w1", label: "a.py" },
        { id: "contract:API", type: "contract", worker: null, label: "API" },
      ],
      edges: [{ from: "agent:w1", to: "file:/a.py", kind: "creates" }],
    };
    const { ctx, api } = makeCtx(graph);
    const cleanup = mod.mount(container, ctx);

    // let the initial refresh() promise + ingest resolve
    await vi.waitFor(() => {
      expect(api).toHaveBeenCalledWith("/workspace-graph");
      const count = container.querySelector('[data-ref="count"]').textContent;
      expect(count).toContain("1 agents");
      expect(count).toContain("1 files");
      expect(count).toContain("1 contracts");
    });

    cleanup();
    expect(container.querySelector('[data-view="workspace"]')).toBeNull();
  });

  it("shows an error overlay when the graph fetch fails and nothing is loaded", async () => {
    const mod = await import(modulePath);
    const container = document.createElement("div");
    document.body.appendChild(container);

    const api = vi.fn(() => Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) }));
    const cleanup = mod.mount(container, { sessionId: "s1", api, ws: vi.fn(), navigate: vi.fn() });

    await vi.waitFor(() => {
      const overlay = container.querySelector('[data-ref="overlay"]');
      expect(overlay.classList.contains("err")).toBe(true);
      expect(overlay.textContent).toContain("Could not load workspace");
    });

    cleanup();
  });
});
