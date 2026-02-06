/**
 * WebSocket Integration Layer for Dashboard Interactions
 *
 * Bridges WebSocket state updates with T1's micro-interaction system.
 * Every WebSocket message becomes a moment of delight.
 *
 * Author: T2 - The Architect
 * Built for: T1 - The Craftsman
 * Date: 2026-02-03
 */

/**
 * WebSocket Integration Manager
 *
 * Listens to WebSocket state changes and translates them into
 * interaction events that T1's dashboard-interactions.js can handle.
 */
class WebSocketIntegrationLayer {
  constructor() {
    this.previousState = {
      connected: false,
      orchestratorStatus: null,
      terminals: {},
      tasks: {
        pending: [],
        in_progress: [],
        completed: [],
        failed: []
      },
      stats: {
        pending: 0,
        in_progress: 0,
        completed: 0,
        failed: 0
      },
      progress: 0
    };

    this.dashboardInteractions = null;
    this.initialized = false;

    // Wait for dashboard interactions to be ready
    this.waitForDashboardInteractions();
  }

  /**
   * Wait for T1's dashboard interactions to be available
   */
  waitForDashboardInteractions() {
    const checkInterval = setInterval(() => {
      if (window.dashboardInteractions) {
        this.dashboardInteractions = window.dashboardInteractions;
        this.initialized = true;
        clearInterval(checkInterval);
        console.log('[T2 Architect] WebSocket integration layer connected to T1\'s interaction system');
      }
    }, 100);

    // Timeout after 10 seconds
    setTimeout(() => {
      clearInterval(checkInterval);
      if (!this.initialized) {
        console.warn('[T2 Architect] Dashboard interactions not found - animations disabled');
      }
    }, 10000);
  }

  /**
   * Process WebSocket update message
   *
   * @param {Object} data - Consolidated update from WebSocket
   * @param {Object} currentState - Current dashboard state
   */
  processUpdate(data, currentState) {
    if (!this.initialized || !this.dashboardInteractions) {
      return; // T1's system not ready yet
    }

    // 1. Connection state changes
    this.handleConnectionChange(currentState.connected);

    // 2. Orchestrator status changes
    if (data.status) {
      this.handleOrchestratorStatusChange(
        data.status.state,
        currentState.orchestratorStatus
      );
    }

    // 3. Terminal status changes
    if (data.status && data.status.terminals) {
      this.handleTerminalStatusChanges(data.status.terminals);
    }

    // 4. Task transitions
    if (data.tasks) {
      this.handleTaskTransitions(data.tasks, currentState.tasks);
    }

    // 5. Stats updates
    if (data.status && data.status.tasks) {
      const newStats = {
        pending: data.status.tasks.pending_count || 0,
        in_progress: data.status.tasks.in_progress_count || 0,
        completed: data.status.tasks.completed_count || 0,
        failed: data.status.tasks.failed_count || 0
      };
      this.handleStatsUpdate(newStats);
    }

    // 6. Progress updates
    const newProgress = this.calculateProgress(currentState.stats);
    if (newProgress !== this.previousState.progress) {
      this.dashboardInteractions.onProgressUpdate(newProgress);
      this.previousState.progress = newProgress;
    }

    // 7. New events
    if (data.events && Array.isArray(data.events)) {
      data.events.forEach(event => {
        this.handleNewEvent(event);
      });
    }

    // 8. Subagent invocations
    if (data.subagents && Array.isArray(data.subagents)) {
      this.handleSubagentInvocations(data.subagents);
    }
  }

  /**
   * Handle connection state change
   */
  handleConnectionChange(connected) {
    if (connected !== this.previousState.connected) {
      this.dashboardInteractions.onConnectionChange(connected);
      this.previousState.connected = connected;
    }
  }

  /**
   * Handle orchestrator status change
   */
  handleOrchestratorStatusChange(newStatus, oldStatus) {
    if (newStatus !== oldStatus && oldStatus !== null) {
      this.dashboardInteractions.onOrchestratorStatusChange(newStatus, oldStatus);
    }
  }

  /**
   * Handle terminal status changes
   */
  handleTerminalStatusChanges(terminals) {
    Object.keys(terminals).forEach(tid => {
      const terminal = terminals[tid];
      const oldStatus = this.previousState.terminals[tid]?.state;
      const newStatus = terminal.state;

      if (oldStatus !== newStatus) {
        this.dashboardInteractions.onTerminalStatusChange(tid, newStatus, oldStatus);

        // Update previous state
        if (!this.previousState.terminals[tid]) {
          this.previousState.terminals[tid] = {};
        }
        this.previousState.terminals[tid].state = newStatus;
      }
    });
  }

  /**
   * Handle task transitions between queues
   */
  handleTaskTransitions(newTasks, oldTasksState) {
    // Build task ID maps for comparison
    const oldTaskIds = {
      pending: new Set((oldTasksState.pending || []).map(t => t.id)),
      in_progress: new Set((oldTasksState.in_progress || []).map(t => t.id)),
      completed: new Set((oldTasksState.completed || []).map(t => t.id)),
      failed: new Set((oldTasksState.failed || []).map(t => t.id))
    };

    const newTaskIds = {
      pending: new Set((newTasks.pending || []).map(t => t.id)),
      in_progress: new Set((newTasks.in_progress || []).map(t => t.id)),
      completed: new Set((newTasks.completed || []).map(t => t.id)),
      failed: new Set((newTasks.failed || []).map(t => t.id))
    };

    // Detect transitions
    const queues = ['pending', 'in_progress', 'completed', 'failed'];

    queues.forEach(toQueue => {
      newTaskIds[toQueue].forEach(taskId => {
        // Was this task in a different queue before?
        const fromQueue = queues.find(q =>
          q !== toQueue && oldTaskIds[q].has(taskId)
        );

        if (fromQueue) {
          // Task transitioned from one queue to another
          this.dashboardInteractions.onTaskTransition(taskId, fromQueue, toQueue);
        } else if (!oldTaskIds[toQueue].has(taskId)) {
          // New task added to this queue
          const task = (newTasks[toQueue] || []).find(t => t.id === taskId);
          if (task) {
            this.dashboardInteractions.onTaskAdded(task, toQueue);
          }
        }
      });
    });

    // Update previous state
    this.previousState.tasks = {
      pending: [...(newTasks.pending || [])],
      in_progress: [...(newTasks.in_progress || [])],
      completed: [...(newTasks.completed || [])],
      failed: [...(newTasks.failed || [])]
    };
  }

  /**
   * Handle stats update
   */
  handleStatsUpdate(newStats) {
    const oldStats = this.previousState.stats;

    // Check if any stat changed
    const changed = Object.keys(newStats).some(key =>
      oldStats[key] !== newStats[key]
    );

    if (changed) {
      this.dashboardInteractions.onStatsUpdate(newStats);
      this.previousState.stats = { ...newStats };
    }
  }

  /**
   * Calculate progress percentage
   */
  calculateProgress(stats) {
    const total = stats.pending + stats.in_progress +
                  stats.completed + stats.failed;

    if (total === 0) return 0;

    // Quality-based progress:
    // - Completed: 100%
    // - In progress: 50%
    // - Pending: 0%
    const qualityScore = stats.completed + (stats.in_progress * 0.5);
    return Math.round((qualityScore / total) * 100);
  }

  /**
   * Handle new event
   */
  handleNewEvent(event) {
    this.dashboardInteractions.onNewEvent(event);
  }

  /**
   * Handle subagent invocations
   */
  handleSubagentInvocations(subagents) {
    // Only notify for new subagents
    const newSubagents = subagents.filter(sa => {
      return !this.previousState.subagents?.some(old =>
        old.name === sa.name && old.timestamp === sa.timestamp
      );
    });

    newSubagents.forEach(subagent => {
      this.dashboardInteractions.onSubagentInvoked(subagent);
    });

    // Update previous state (keep last 20)
    this.previousState.subagents = subagents.slice(0, 20);
  }
}

/**
 * Export singleton instance
 */
const wsIntegration = new WebSocketIntegrationLayer();

// Export to global scope for use in index.html
window.wsIntegration = wsIntegration;

export default wsIntegration;
