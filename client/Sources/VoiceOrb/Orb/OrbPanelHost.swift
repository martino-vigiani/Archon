import SwiftUI

/// The SwiftUI shim registered into `ShellSlot.orbOverlay`. It renders nothing
/// itself (zero footprint in the SwiftUI layer) — instead it attaches a
/// `FloatingOrbPanel` to the host window so the orb lives in its own compositing
/// layer (REQ-DSN-051), floating above the three-pane shell and draggable
/// (REQ-UX-042).
///
/// `content` is the orb + Conductor surface composition supplied by the feature
/// coordinator (kept fresh on every SwiftUI update).
struct OrbPanelHost<Content: View>: NSViewRepresentable {
    let positionStore: any OrbPositionPersisting
    let content: Content

    init(positionStore: any OrbPositionPersisting, @ViewBuilder content: () -> Content) {
        self.positionStore = positionStore
        self.content = content()
    }

    func makeCoordinator() -> Coordinator {
        Coordinator(positionStore: positionStore, content: AnyView(content))
    }

    func makeNSView(context: Context) -> NSView {
        let anchor = NSView(frame: .zero)
        anchor.setContentHuggingPriority(.required, for: .horizontal)
        anchor.setContentHuggingPriority(.required, for: .vertical)
        return anchor
    }

    func updateNSView(_ nsView: NSView, context: Context) {
        context.coordinator.update(content: AnyView(content))
        // The window is available after the view joins the hierarchy; retry via
        // the next runloop tick until it is.
        if let window = nsView.window {
            context.coordinator.attach(to: window)
        } else {
            DispatchQueue.main.async { [weak nsView] in
                guard let window = nsView?.window else { return }
                context.coordinator.attach(to: window)
            }
        }
    }

    static func dismantleNSView(_ nsView: NSView, coordinator: Coordinator) {
        coordinator.detach()
    }

    @MainActor
    final class Coordinator {
        private let controller: OrbPanelController

        init(positionStore: any OrbPositionPersisting, content: AnyView) {
            self.controller = OrbPanelController(positionStore: positionStore, content: content)
        }

        func update(content: AnyView) { controller.update(content: content) }
        func attach(to window: NSWindow) { controller.attach(to: window) }
        func detach() { controller.detach() }
    }
}
