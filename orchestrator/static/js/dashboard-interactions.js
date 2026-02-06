/**
 * ARCHON Dashboard Interaction Layer
 *
 * Self-contained micro-interaction system for the dashboard.
 * No external dependencies - everything is inline.
 *
 * Author: T1 - The Craftsman
 * Date: 2026-02-06
 */

/**
 * Toast notification system
 */
class Toast {
  static container = null;

  static ensureContainer() {
    if (!Toast.container) {
      Toast.container = document.createElement('div');
      Toast.container.id = 'toast-container';
      Toast.container.style.cssText = `
        position: fixed;
        top: 80px;
        right: 24px;
        z-index: 9999;
        display: flex;
        flex-direction: column;
        gap: 8px;
        pointer-events: none;
      `;
      document.body.appendChild(Toast.container);
    }
  }

  static show(message, options = {}) {
    Toast.ensureContainer();
    const { type = 'info', duration = 3000 } = options;

    const colors = {
      info: { bg: 'rgba(59,130,246,0.15)', border: 'rgba(59,130,246,0.3)', text: '#93bbfd' },
      success: { bg: 'rgba(34,197,94,0.15)', border: 'rgba(34,197,94,0.3)', text: '#6ee7a0' },
      warning: { bg: 'rgba(234,179,8,0.15)', border: 'rgba(234,179,8,0.3)', text: '#fcd34d' },
      error: { bg: 'rgba(239,68,68,0.15)', border: 'rgba(239,68,68,0.3)', text: '#fca5a5' }
    };

    const c = colors[type] || colors.info;

    const el = document.createElement('div');
    el.style.cssText = `
      padding: 10px 16px;
      border-radius: 10px;
      background: ${c.bg};
      border: 1px solid ${c.border};
      color: ${c.text};
      font-size: 13px;
      font-weight: 500;
      backdrop-filter: blur(12px);
      pointer-events: auto;
      opacity: 0;
      transform: translateX(20px);
      transition: all 0.25s ease;
      max-width: 320px;
    `;
    el.textContent = message;

    Toast.container.appendChild(el);

    // Animate in
    requestAnimationFrame(() => {
      el.style.opacity = '1';
      el.style.transform = 'translateX(0)';
    });

    // Animate out
    setTimeout(() => {
      el.style.opacity = '0';
      el.style.transform = 'translateX(20px)';
      setTimeout(() => el.remove(), 250);
    }, duration);
  }
}

/**
 * Dashboard Interaction Manager
 */
class DashboardInteractions {
  constructor() {
    this.previousState = {
      terminals: {},
      tasks: {},
      stats: {},
      connected: false
    };

    this.init();
  }

  init() {
    this.initTerminalCards();
    window.dashboardInteractions = this;
  }

  initTerminalCards() {
    const terminals = document.querySelectorAll('.terminal-card');
    terminals.forEach((card, index) => {
      card.style.opacity = '0';
      card.style.transform = 'translateY(12px)';
      setTimeout(() => {
        card.style.transition = 'opacity 0.35s ease, transform 0.35s ease';
        card.style.opacity = '1';
        card.style.transform = 'translateY(0)';
      }, index * 80);
    });
  }

  onConnectionChange(connected) {
    if (connected === this.previousState.connected) return;

    if (connected) {
      Toast.show('Connected to Archon', { type: 'success', duration: 2000 });
    } else {
      Toast.show('Connection lost. Reconnecting...', { type: 'warning', duration: 3000 });
    }

    this.previousState.connected = connected;
  }

  onOrchestratorStatusChange(newStatus, oldStatus) {
    const badge = document.getElementById('orchestrator-status');
    if (!badge) return;

    if (newStatus === 'running' && oldStatus !== 'running') {
      badge.style.transition = 'transform 300ms ease';
      badge.style.transform = 'scale(1.05)';
      setTimeout(() => {
        badge.style.transform = 'scale(1)';
      }, 300);
      Toast.show('Orchestrator running', { type: 'info', duration: 2000 });
    }
  }

  onTerminalStatusChange(terminalId, newStatus, oldStatus) {
    const card = document.getElementById(`terminal-${terminalId}`);
    if (!card) return;

    // Pulse animation on state change
    card.style.transition = 'box-shadow 0.3s ease';
    if (newStatus === 'busy') {
      const color = getComputedStyle(card).getPropertyValue(`--${terminalId}-color`) || '#3b82f6';
      card.style.boxShadow = `0 0 20px ${color}22`;
      setTimeout(() => {
        card.style.boxShadow = '';
      }, 600);
    } else if (newStatus === 'error') {
      Toast.show(`${terminalId.toUpperCase()} encountered an error`, {
        type: 'error',
        duration: 4000
      });
    }

    this.previousState.terminals[terminalId] = newStatus;
  }

  onTaskAdded(task, queueType) {
    // Subtle notification
  }

  onTaskTransition(taskId, fromQueue, toQueue) {
    if (toQueue === 'completed') {
      Toast.show('Task completed', { type: 'success', duration: 1500 });
    } else if (toQueue === 'failed') {
      Toast.show('Task failed', { type: 'error', duration: 2000 });
    }
  }

  onStatsUpdate(newStats) {
    ['pending', 'in_progress', 'completed', 'failed'].forEach(key => {
      const oldValue = this.previousState.stats[key] || 0;
      const newValue = newStats[key] || 0;

      if (oldValue !== newValue) {
        const element = document.getElementById(`stat-${key.replace('_', '-')}`);
        if (element) {
          element.style.transition = 'transform 0.2s ease';
          element.style.transform = 'scale(1.15)';
          setTimeout(() => {
            element.style.transform = 'scale(1)';
          }, 200);
        }
      }
    });

    this.previousState.stats = { ...newStats };
  }

  onProgressUpdate(percentage) {
    if (percentage === 100) {
      Toast.show('All tasks completed!', { type: 'success', duration: 3000 });
    }
  }

  onNewEvent(event) {
    // No-op, events render via main loop
  }

  onSubagentInvoked(subagent) {
    Toast.show(`Subagent: ${subagent.name}`, { type: 'info', duration: 2000 });
  }

  notify(message, type = 'info', duration = 3000) {
    Toast.show(message, { type, duration });
  }
}

let dashboardInteractions = null;

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    dashboardInteractions = new DashboardInteractions();
  });
} else {
  dashboardInteractions = new DashboardInteractions();
}

export default dashboardInteractions;
export { DashboardInteractions, Toast };
