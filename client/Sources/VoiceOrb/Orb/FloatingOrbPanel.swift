import AppKit
import SwiftUI

/// Persists the orb's position as an offset from the host window's origin, per
/// project (Q17 / REQ-UX-042). Implemented in the coordinator over `ProjectStore`
/// (Application Support only — never inside the project tree, Addendum §A3).
@MainActor
protocol OrbPositionPersisting: AnyObject {
    /// Panel origin relative to the parent window origin, or `nil` for default.
    func loadOffset() -> CGPoint?
    func saveOffset(_ offset: CGPoint)
}

/// A borderless, non-activating floating panel (REQ-DSN-051, REQ-UX-036: no
/// accessibility permission, no app activation). Hosts the orb (and, when
/// active, the Conductor surface) in its own compositing layer, independent of
/// the SwiftUI hierarchy.
final class FloatingOrbPanel: NSPanel {
    init() {
        super.init(
            contentRect: NSRect(x: 0, y: 0, width: 132, height: 132),
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )
        isFloatingPanel = true
        level = .normal
        hidesOnDeactivate = false
        isMovableByWindowBackground = true
        backgroundColor = .clear
        isOpaque = false
        hasShadow = false
        titleVisibility = .hidden
        titlebarAppearsTransparent = true
        collectionBehavior = [.fullScreenAuxiliary, .moveToActiveSpace]
        // Never steal keyboard focus unless a control inside genuinely needs it.
        becomesKeyOnlyIfNeeded = true
        animationBehavior = .none
    }

    // A borderless panel must opt in to being able to become key so the
    // Conductor's text field can receive input without activating the app.
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { false }
}

/// Owns the lifecycle of a single `FloatingOrbPanel`: attaches it as a child of
/// the host window, keeps it anchored (bottom-centre by default), auto-sizes it
/// to its SwiftUI content, and persists user drags.
@MainActor
final class OrbPanelController: NSObject, NSWindowDelegate {
    private let panel = FloatingOrbPanel()
    private let hostingView: NSHostingView<AnyView>
    private weak var parentWindow: NSWindow?
    private let positionStore: any OrbPositionPersisting
    private var didAttach = false
    private var defaultBottomMargin: CGFloat = 28

    init(positionStore: any OrbPositionPersisting, content: AnyView) {
        self.positionStore = positionStore
        self.hostingView = NSHostingView(rootView: content)
        super.init()
        hostingView.translatesAutoresizingMaskIntoConstraints = true
        hostingView.autoresizingMask = [.width, .height]
        panel.contentView = hostingView
        panel.delegate = self
    }

    /// Update the hosted SwiftUI content (called on every representable update).
    func update(content: AnyView) {
        hostingView.rootView = content
        resizeToFit(keepingAnchor: true)
    }

    /// Attach to the host window once it exists. Idempotent.
    func attach(to window: NSWindow) {
        guard !didAttach else {
            // Parent may have changed identity across a project reopen.
            if parentWindow !== window { reparent(to: window) }
            return
        }
        parentWindow = window
        resizeToFit(keepingAnchor: false)
        positionForFirstShow(in: window)
        window.addChildWindow(panel, ordered: .above)
        panel.orderFront(nil)
        didAttach = true
    }

    func detach() {
        parentWindow?.removeChildWindow(panel)
        panel.orderOut(nil)
        didAttach = false
    }

    private func reparent(to window: NSWindow) {
        parentWindow?.removeChildWindow(panel)
        parentWindow = window
        positionForFirstShow(in: window)
        window.addChildWindow(panel, ordered: .above)
    }

    // MARK: - Sizing / positioning

    private func resizeToFit(keepingAnchor: Bool) {
        let fitting = hostingView.fittingSize
        let size = CGSize(
            width: fitting.width > 1 ? fitting.width : 132,
            height: fitting.height > 1 ? fitting.height : 132
        )
        let old = panel.frame
        panel.setContentSize(size)
        guard keepingAnchor, didAttach else { return }
        // Keep the bottom-centre anchor fixed so the surface grows upward.
        var frame = panel.frame
        frame.origin.x = old.midX - frame.width / 2
        frame.origin.y = old.minY
        panel.setFrame(frame, display: true)
    }

    private func positionForFirstShow(in window: NSWindow) {
        let parentFrame = window.frame
        let panelSize = panel.frame.size
        let origin: CGPoint
        if let offset = positionStore.loadOffset() {
            origin = CGPoint(x: parentFrame.origin.x + offset.x,
                             y: parentFrame.origin.y + offset.y)
        } else {
            // Default: bottom-centre of the host window (REQ-UX-042).
            origin = CGPoint(
                x: parentFrame.midX - panelSize.width / 2,
                y: parentFrame.origin.y + defaultBottomMargin
            )
        }
        panel.setFrameOrigin(clamp(origin: origin, size: panelSize, within: parentFrame))
    }

    private func clamp(origin: CGPoint, size: CGSize, within frame: NSRect) -> CGPoint {
        let minX = frame.minX - size.width * 0.5
        let maxX = frame.maxX - size.width * 0.5
        let minY = frame.minY
        let maxY = frame.maxY - size.height
        return CGPoint(x: min(max(origin.x, minX), maxX),
                       y: min(max(origin.y, minY), maxY))
    }

    // MARK: - NSWindowDelegate (user drag persistence)

    func windowDidMove(_ notification: Notification) {
        guard didAttach, let parent = parentWindow else { return }
        let offset = CGPoint(
            x: panel.frame.origin.x - parent.frame.origin.x,
            y: panel.frame.origin.y - parent.frame.origin.y
        )
        positionStore.saveOffset(offset)
    }
}
