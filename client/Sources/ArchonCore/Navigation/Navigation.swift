import Foundation

/// The three main-pane destinations (REQ-UX-003). Exactly three: reachable via
/// ⌘1/⌘2/⌘3, a segmented control, and Conductor-driven programmatic navigation.
enum MainPane: String, CaseIterable, Identifiable, Sendable, Hashable {
    case terminals
    case summary
    case codebase

    var id: String { rawValue }

    var title: String {
        switch self {
        case .terminals: return "Terminals"
        case .summary: return "Summary"
        case .codebase: return "Codebase"
        }
    }

    /// SF Symbol name (achromatic per §5.6).
    var systemImageName: String {
        switch self {
        case .terminals: return "square.grid.2x2"
        case .summary: return "chart.bar"
        case .codebase: return "folder"
        }
    }

    /// Keyboard shortcut character (⌘1/⌘2/⌘3).
    var shortcutKey: Character {
        switch self {
        case .terminals: return "1"
        case .summary: return "2"
        case .codebase: return "3"
        }
    }
}

/// The pluggable regions of the three-pane shell. Phase-B feature teams
/// register views into these slots via `ShellRegistry` — no edits to the shell
/// itself (REQ-UX-001 structure; §5.3 material zones).
enum ShellSlot: Hashable, Sendable {
    /// Left sidebar: directory-tree navigator + memory-file access.
    case sidebar
    /// Central main pane content for a given destination.
    case main(MainPane)
    /// Right drawer housing the Kanban board (the "conductor edge").
    case conductorEdge
    /// The always-visible floating orb overlay (REQ-UX-002).
    case orbOverlay
    /// The central Conductor dialogue / transcription surface.
    case conductorSurface
}
