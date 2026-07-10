import Foundation

/// The five main-pane destinations (REQ-UX-003). Reachable via ⌘1–⌘5, a
/// segmented control, and Conductor-driven programmatic navigation.
enum MainPane: String, CaseIterable, Identifiable, Sendable, Hashable {
    case terminals
    case summary
    case codebase
    case kanban
    case memory

    var id: String { rawValue }

    var title: String {
        switch self {
        case .terminals: return "Terminals"
        case .summary: return "Summary"
        case .codebase: return "Codebase"
        case .kanban: return "Board"
        case .memory: return "Memory"
        }
    }

    /// SF Symbol name (achromatic per §5.6).
    var systemImageName: String {
        switch self {
        case .terminals: return "square.grid.2x2"
        case .summary: return "chart.bar"
        case .codebase: return "folder"
        case .kanban: return "rectangle.split.3x1"
        case .memory: return "doc.text"
        }
    }

    /// Keyboard shortcut character (⌘1…⌘5).
    var shortcutKey: Character {
        switch self {
        case .terminals: return "1"
        case .summary: return "2"
        case .codebase: return "3"
        case .kanban: return "4"
        case .memory: return "5"
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
