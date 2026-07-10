import Foundation
import Observation

/// A lazily-loaded directory-tree node (REQ-UX-070). Reference type so the tree
/// mutates in place (expand/collapse, change indicators) with per-node
/// observation; strictly read-only — the codebase view never edits the project.
@MainActor
@Observable
final class FileNode: Identifiable {
    let id: String            // absolute POSIX path (stable identity)
    let url: URL
    let name: String
    let isDirectory: Bool
    /// Path relative to the tree root (POSIX, no leading slash). "" for the root.
    let relativePath: String

    var isExpanded: Bool = false
    var childrenLoaded: Bool = false
    var children: [FileNode]?
    var isGitignored: Bool = false
    /// File modified during the current run (REQ-UX-071 "• prefix").
    var isChangedThisRun: Bool = false

    init(
        url: URL,
        name: String,
        isDirectory: Bool,
        relativePath: String,
        isGitignored: Bool = false,
        isChangedThisRun: Bool = false
    ) {
        self.id = url.path
        self.url = url
        self.name = name
        self.isDirectory = isDirectory
        self.relativePath = relativePath
        self.isGitignored = isGitignored
        self.isChangedThisRun = isChangedThisRun
        self.children = isDirectory ? nil : []
    }
}

/// A plain value DTO produced by off-main filesystem enumeration, then folded
/// into the `@MainActor` `FileNode` tree. `Sendable` so it can cross actors.
struct FileEntry: Sendable, Equatable {
    let url: URL
    let name: String
    let isDirectory: Bool
    let modifiedAt: Date?
}
