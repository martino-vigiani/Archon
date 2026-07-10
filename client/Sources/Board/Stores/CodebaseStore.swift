import Foundation
import Observation

/// A calm project summary for the "personal intelligence" surface when no file
/// is selected (REQ-UX-073 / §4.8). Derived from the shared `AppState`.
struct ProjectOverview: Sendable, Equatable {
    var name: String
    var path: String
    var branch: String?
    var liveSessionCount: Int
    var totalSessions: Int
    var lastActivityAt: Date?
}

/// The Codebase sector store (@Observable @MainActor): a lazily-loaded,
/// read-only directory tree (REQ-UX-070), `.gitignore`-aware dimming, current-
/// run change indicators (REQ-UX-071), and the singular preview/overview surface
/// (REQ-UX-073). Folder-expand state persists in the app-support state dir,
/// NEVER in the project (addendum §A3). Direct FS reads only — no writes.
@MainActor
@Observable
final class CodebaseStore {

    // MARK: - Observable state

    private(set) var root: FileNode?
    private(set) var selection: FileNode?
    private(set) var preview: FilePreview?
    private(set) var isLoading: Bool = false

    // MARK: - Config

    private(set) var projectURL: URL?
    private var stateDirectory: URL?
    private weak var appState: AppState?
    private var runStartDate: Date = Date()
    private var gitignore: GitignoreMatcher?
    private(set) var expandedPaths: Set<String> = []

    init(projectURL: URL? = nil, stateDirectory: URL? = nil, appState: AppState? = nil) {
        self.projectURL = projectURL
        self.stateDirectory = stateDirectory
        self.appState = appState
    }

    /// (Re)binds the store to a project. Called on connect once the project path
    /// is known. Loads persisted expand state and the gitignore matcher.
    func configure(projectURL: URL?, stateDirectory: URL?) {
        self.projectURL = projectURL
        self.stateDirectory = stateDirectory
        self.runStartDate = Date()
        self.selection = nil
        self.preview = nil
        self.root = nil
        if let projectURL {
            self.gitignore = GitignoreMatcher(directory: projectURL)
        } else {
            self.gitignore = nil
        }
        self.expandedPaths = loadExpandedPaths()
    }

    // MARK: - Overview

    var overview: ProjectOverview {
        let sessions = appState?.sessions ?? []
        return ProjectOverview(
            name: projectURL?.lastPathComponent ?? appState?.projectInfo?.name ?? "Project",
            path: projectURL?.path ?? appState?.projectInfo?.path ?? "",
            branch: appState?.projectInfo?.git?.branch,
            liveSessionCount: appState?.liveSessionCount ?? 0,
            totalSessions: sessions.count,
            lastActivityAt: sessions.compactMap(\.lastActivityAt).max()
        )
    }

    // MARK: - Loading

    func loadRoot() async {
        guard let projectURL else { root = nil; return }
        isLoading = true
        defer { isLoading = false }
        let rootNode = FileNode(
            url: projectURL,
            name: projectURL.lastPathComponent,
            isDirectory: true,
            relativePath: ""
        )
        rootNode.isExpanded = true
        await loadChildren(rootNode)
        await restoreExpansion(rootNode)
        root = rootNode
    }

    func toggleExpand(_ node: FileNode) async {
        guard node.isDirectory else { return }
        node.isExpanded.toggle()
        if node.isExpanded {
            expandedPaths.insert(node.id)
            if !node.childrenLoaded { await loadChildren(node) }
        } else {
            expandedPaths.remove(node.id)
        }
        persistExpandedPaths()
    }

    /// Selecting a directory toggles it; selecting a file loads the read-only
    /// preview into the singular central surface (REQ-UX-072/073).
    func select(_ node: FileNode) async {
        if node.isDirectory {
            await toggleExpand(node)
            return
        }
        selection = node
        preview = nil
        preview = await FileTreeLoader.readPreview(node.url)
    }

    func clearSelection() {
        selection = nil
        preview = nil
    }

    /// Re-scans already-loaded directories and refreshes change indicators
    /// (REQ-UX-071, via poll). Bounded to loaded/expanded nodes.
    func refresh() async {
        guard let root else { return }
        await reloadLoaded(root)
    }

    // MARK: - Internals

    private func loadChildren(_ node: FileNode) async {
        node.children = await makeChildren(of: node)
        node.childrenLoaded = true
    }

    private func makeChildren(of parent: FileNode) async -> [FileNode] {
        let entries = await FileTreeLoader.loadChildren(of: parent.url)
        return entries.map { entry in
            let relative = parent.relativePath.isEmpty ? entry.name : parent.relativePath + "/" + entry.name
            // Dimming inherits: anything under an ignored directory is also dimmed
            // (git ignores whole subtrees), even if no pattern names the child.
            let ignored = parent.isGitignored
                || (gitignore?.isIgnored(relativePath: relative, isDirectory: entry.isDirectory) ?? false)
            let node = FileNode(
                url: entry.url,
                name: entry.name,
                isDirectory: entry.isDirectory,
                relativePath: relative,
                isGitignored: ignored,
                isChangedThisRun: !entry.isDirectory && (entry.modifiedAt.map { $0 >= runStartDate } ?? false)
            )
            if node.isDirectory && expandedPaths.contains(node.id) {
                node.isExpanded = true
            }
            return node
        }
    }

    private func restoreExpansion(_ node: FileNode) async {
        guard let children = node.children else { return }
        for child in children where child.isDirectory && child.isExpanded {
            if !child.childrenLoaded { await loadChildren(child) }
            await restoreExpansion(child)
        }
    }

    private func reloadLoaded(_ node: FileNode) async {
        guard node.isDirectory, node.childrenLoaded else { return }
        node.children = await makeChildren(of: node)
        guard let children = node.children else { return }
        for child in children where child.isDirectory && child.isExpanded {
            await loadChildren(child)
            await reloadLoaded(child)
        }
    }

    // MARK: - Expand-state persistence (app-support only — §A3)

    private var expandStateFile: URL? {
        stateDirectory?.appendingPathComponent("codebase-expanded.json", isDirectory: false)
    }

    private func loadExpandedPaths() -> Set<String> {
        guard let file = expandStateFile,
              let data = try? Data(contentsOf: file),
              let list = try? JSONDecoder().decode([String].self, from: data)
        else { return [] }
        return Set(list)
    }

    private func persistExpandedPaths() {
        guard let file = expandStateFile else { return }
        let list = Array(expandedPaths)
        guard let data = try? JSONEncoder().encode(list) else { return }
        try? FileManager.default.createDirectory(
            at: file.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        try? data.write(to: file, options: .atomic)
    }
}
