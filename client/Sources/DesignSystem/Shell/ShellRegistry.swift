import SwiftUI

/// The small navigation/plug-in registry phase-B feature teams register into
/// (task item 5). Terminals, Board, and VoiceOrb each register a view builder
/// for their `ShellSlot` at launch — no edits to the shell itself.
///
/// Unregistered slots render a neutral placeholder, so the foundation app runs
/// standalone before any feature module exists.
@MainActor
@Observable
final class ShellRegistry {

    private var builders: [ShellSlot: () -> AnyView] = [:]

    init() {}

    /// Registers a view builder for a slot. Later registrations replace earlier.
    func register(_ slot: ShellSlot, @ViewBuilder content: @escaping () -> some View) {
        builders[slot] = { AnyView(content()) }
    }

    func hasContent(for slot: ShellSlot) -> Bool {
        builders[slot] != nil
    }

    /// The registered view for a slot, or a neutral placeholder.
    @ViewBuilder
    func view(for slot: ShellSlot) -> some View {
        if let builder = builders[slot] {
            builder()
        } else {
            PlaceholderSlotView(slot: slot)
        }
    }
}

/// Neutral, strictly-achromatic placeholder for an unregistered slot.
struct PlaceholderSlotView: View {
    let slot: ShellSlot

    var body: some View {
        switch slot {
        case .orbOverlay:
            PlaceholderOrb()
        case .sidebar:
            EmptyStateView(
                systemImage: "sidebar.left",
                title: "Sidebar",
                message: "Directory tree & memory appear here."
            )
            .archonMaterial(.glassSidebar)
        case .conductorEdge:
            EmptyStateView(
                systemImage: "rectangle.trailinghalf.inset.filled",
                title: "Kanban",
                message: "The board appears here."
            )
            .archonMaterial(.flatSurface)
        case .conductorSurface:
            EmptyStateView(
                systemImage: "waveform",
                title: "Conductor",
                message: "Speak or type to start."
            )
        case .main(let pane):
            EmptyStateView(
                systemImage: pane.systemImageName,
                title: pane.title,
                message: "\(pane.title) view is provided by a feature module."
            )
            .archonMaterial(.flatSurface)
        }
    }
}

/// A neutral placeholder orb (the real, chromatic Metal orb is the phase-B
/// VoiceOrb module — color lives ONLY there). Kept achromatic here so the
/// DesignSystem module contains zero chroma.
struct PlaceholderOrb: View {
    @Environment(\.archonTheme) private var theme

    var body: some View {
        Circle()
            .fill(
                RadialGradient(
                    colors: [theme.surfaceRaised, theme.background],
                    center: .center,
                    startRadius: 2,
                    endRadius: 28
                )
            )
            .overlay { Circle().strokeBorder(theme.borderSubtle, lineWidth: Space.hairline) }
            .frame(width: 56, height: 56)
            .shadow(color: Ink.ink0.opacity(0.25), radius: 8, y: 2)
            .accessibilityLabel("Conductor orb")
    }
}
