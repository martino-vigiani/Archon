import { beforeEach, describe, expect, it, vi } from "vitest";

const websocketModulePath = "../../orchestrator/static/js/websocket-integration.js";

function createInteractionsMock() {
  return {
    onConnectionChange: vi.fn(),
    onOrchestratorStatusChange: vi.fn(),
    onTerminalStatusChange: vi.fn(),
    onTaskAdded: vi.fn(),
    onTaskTransition: vi.fn(),
    onStatsUpdate: vi.fn(),
    onProgressUpdate: vi.fn(),
    onNewEvent: vi.fn(),
    onSubagentInvoked: vi.fn(),
  };
}

describe("websocket-integration", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  it("calculates progress with completed and in-progress weights", async () => {
    const mod = await import(websocketModulePath);
    vi.spyOn(mod.WebSocketIntegrationLayer.prototype, "waitForDashboardInteractions").mockImplementation(function mockedWait() {
      this.initialized = true;
      this.dashboardInteractions = createInteractionsMock();
    });

    const layer = new mod.WebSocketIntegrationLayer();
    expect(layer.calculateProgress({ pending: 0, in_progress: 0, completed: 0, failed: 0 })).toBe(0);
    expect(layer.calculateProgress({ pending: 1, in_progress: 1, completed: 2, failed: 0 })).toBe(63);
  });

  it("detects queue transitions for existing tasks", async () => {
    const mod = await import(websocketModulePath);
    const interactions = createInteractionsMock();

    vi.spyOn(mod.WebSocketIntegrationLayer.prototype, "waitForDashboardInteractions").mockImplementation(function mockedWait() {
      this.initialized = true;
      this.dashboardInteractions = interactions;
    });

    const layer = new mod.WebSocketIntegrationLayer();
    const oldTasks = {
      pending: [{ id: "task-1" }],
      in_progress: [],
      completed: [],
      failed: [],
    };
    const newTasks = {
      pending: [],
      in_progress: [],
      completed: [{ id: "task-1" }],
      failed: [],
    };

    layer.handleTaskTransitions(newTasks, oldTasks);

    expect(interactions.onTaskTransition).toHaveBeenCalledWith("task-1", "pending", "completed");
  });

  it("notifies only newly detected subagents", async () => {
    const mod = await import(websocketModulePath);
    const interactions = createInteractionsMock();

    vi.spyOn(mod.WebSocketIntegrationLayer.prototype, "waitForDashboardInteractions").mockImplementation(function mockedWait() {
      this.initialized = true;
      this.dashboardInteractions = interactions;
    });

    const layer = new mod.WebSocketIntegrationLayer();
    const existing = { name: "agent-a", timestamp: "2026-02-26T10:00:00Z" };
    const incoming = [existing, { name: "agent-b", timestamp: "2026-02-26T10:01:00Z" }];

    layer.previousState.subagents = [existing];
    layer.handleSubagentInvocations(incoming);

    expect(interactions.onSubagentInvoked).toHaveBeenCalledTimes(1);
    expect(interactions.onSubagentInvoked).toHaveBeenCalledWith(incoming[1]);
  });
});
