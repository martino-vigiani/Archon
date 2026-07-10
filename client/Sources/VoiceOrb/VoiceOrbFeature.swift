import SwiftUI

/// The single public entry point for the VoiceOrb sector (task item 5). The app
/// integrator calls `register(into:container:)` once at launch; this module
/// plugs its views into the shell slots it owns and never touches `App/`,
/// `ArchonCore/`, or other feature directories.
///
/// Slots registered:
/// - `.orbOverlay` — the floating, draggable, chromatic orb in its own panel
///   (REQ-DSN-051 / REQ-UX-042), composed with the Conductor surface above it.
/// - `.conductorSurface` — the Conductor exchange pane (REQ-ARCH-043), for when
///   the integrator wires a dedicated region for it.
///
/// Seam note: `ShellSlot.conductorEdge` is intentionally NOT registered here —
/// that slot houses the Kanban board (Board sector). The Conductor's own
/// edge/summon affordance is composed into the orb overlay instead.
enum VoiceOrbFeature {

    /// Retains the coordinator for the app lifetime by capturing it in the
    /// registered view builders (the registry is owned by `AppContainer`).
    @MainActor
    static func register(into registry: ShellRegistry, container: AppContainer) {
        let coordinator = VoiceOrbCoordinator(container: container)

        registry.register(.orbOverlay) {
            OrbPanelHost(positionStore: coordinator.positionStore) {
                OrbOverlayContent(coordinator: coordinator)
            }
        }

        registry.register(.conductorSurface) {
            ConductorSurfaceView(
                conductor: coordinator.conductor,
                voice: coordinator.voice
            )
        }
    }
}
