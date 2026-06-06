import { describe, expect, it, vi } from "vitest";

const dashboardModulePath = "../../orchestrator/static/js/dashboard-interactions.js";

describe("dashboard-interactions", () => {
  it("shows and auto-removes toasts", async () => {
    vi.resetModules();
    const { Toast } = await import(dashboardModulePath);
    Toast.container = null;

    Toast.show("Build completed", { type: "success", duration: 100 });

    const container = document.getElementById("toast-container");
    expect(container).not.toBeNull();
    expect(container.children).toHaveLength(1);
    expect(container.textContent).toContain("Build completed");

    vi.advanceTimersByTime(400);
    expect(container.children).toHaveLength(0);
  });

  it("notifies only when connection state changes", async () => {
    vi.resetModules();
    const { DashboardInteractions, Toast } = await import(dashboardModulePath);
    const toastSpy = vi.spyOn(Toast, "show").mockImplementation(() => {});

    const interactions = new DashboardInteractions();
    interactions.onConnectionChange(true);
    interactions.onConnectionChange(true);
    interactions.onConnectionChange(false);

    expect(toastSpy).toHaveBeenCalledTimes(2);
    expect(toastSpy).toHaveBeenNthCalledWith(
      1,
      "Connected to Archon",
      expect.objectContaining({ type: "success" }),
    );
    expect(toastSpy).toHaveBeenNthCalledWith(
      2,
      "Connection lost. Reconnecting...",
      expect.objectContaining({ type: "warning" }),
    );
  });

  it("notifies when a task reaches completed queue", async () => {
    vi.resetModules();
    const { DashboardInteractions, Toast } = await import(dashboardModulePath);
    const toastSpy = vi.spyOn(Toast, "show").mockImplementation(() => {});

    const interactions = new DashboardInteractions();
    interactions.onTaskTransition("task-1", "in_progress", "completed");

    expect(toastSpy).toHaveBeenCalledWith(
      "Task completed",
      expect.objectContaining({ type: "success" }),
    );
  });
});
