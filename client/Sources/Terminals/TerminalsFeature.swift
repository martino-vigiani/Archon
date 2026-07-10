import SwiftUI

// ============================================================================
// Terminals · TerminalsFeature
//
// The single public entry point for the Terminals sector. The integrator calls
// `TerminalsFeature.register(into:container:)` once at launch; it creates the
// sector-owned `TerminalsStore`, starts it (event pump + snapshot + 1 Hz clock),
// and plugs the views into their ShellSlots. The store is retained by the
// registered closures — no edits to App/ or the shell are required.
//
// Registered slots:
//   • .main(.terminals) → IndividualTerminalsView (grid + focus + controls)
//   • .main(.summary)   → SummaryDashboardView    (KPIs + status + timeline)
//   • .sidebar          → TerminalsSidebarView     (session list, drives focus)
//
// Seam note: `.sidebar` is a shared slot. If the Board/Codebase sector also
// registers `.sidebar`, later registration wins (ShellRegistry) — the integrator
// decides ordering/composition.
// ============================================================================

enum TerminalsFeature {

    /// Registers the Terminals views into the shell. Call once, on the MainActor.
    /// (Single-module app: `internal` — the integrator lives in the same module.)
    @MainActor
    static func register(into registry: ShellRegistry, container: AppContainer) {
        let store = TerminalsStore(container: container)
        store.start()

        registry.register(.main(.terminals)) {
            IndividualTerminalsView(store: store)
        }
        registry.register(.main(.summary)) {
            SummaryDashboardView(store: store)
        }
        registry.register(.sidebar) {
            TerminalsSidebarView(store: store)
        }
    }
}
