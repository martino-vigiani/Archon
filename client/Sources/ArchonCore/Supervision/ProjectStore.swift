import Foundation

/// A recently-opened project, persisted app-side (Addendum §A2). Stored OUTSIDE
/// any project directory (§A3 zero-footprint).
struct RecentProject: Codable, Sendable, Equatable, Identifiable {
    var projectId: String
    var path: String
    var name: String
    var lastOpenedAt: Date

    var id: String { projectId }

    var url: URL { URL(fileURLWithPath: path) }
}

/// Owns all on-disk app state paths and the recent-projects list.
///
/// HARD RULE (Addendum §A3): the app NEVER writes inside a project directory.
/// Everything lives under `~/Library/Application Support/Archon/…`. The
/// per-project state dir is keyed by `sha256(canonical-path)` so two projects
/// never collide and opening one leaves its working tree byte-identical.
struct ProjectStore: Sendable {

    let supportDirectory: URL
    private let recentLimit: Int

    init(supportDirectory: URL? = nil, recentLimit: Int = 12) {
        self.supportDirectory = supportDirectory ?? Self.defaultSupportDirectory()
        self.recentLimit = recentLimit
    }

    static func defaultSupportDirectory() -> URL {
        let base = (try? FileManager.default.url(
            for: .applicationSupportDirectory,
            in: .userDomainMask,
            appropriateFor: nil,
            create: false
        )) ?? URL(fileURLWithPath: NSHomeDirectory()).appendingPathComponent("Library/Application Support")
        return base.appendingPathComponent("Archon", isDirectory: true)
    }

    // MARK: - Path layout

    var projectsDirectory: URL {
        supportDirectory.appendingPathComponent("projects", isDirectory: true)
    }

    var metricsDirectory: URL {
        supportDirectory.appendingPathComponent("metrics", isDirectory: true)
    }

    private var recentProjectsFile: URL {
        supportDirectory.appendingPathComponent("recent-projects.json", isDirectory: false)
    }

    /// `~/Library/Application Support/Archon/projects/<project_id>/`
    func stateDirectory(forProjectAt url: URL) -> URL {
        let projectId = ProjectIdentity.projectID(for: url)
        return projectsDirectory.appendingPathComponent(projectId, isDirectory: true)
    }

    func stateDirectory(forProjectID projectId: String) -> URL {
        projectsDirectory.appendingPathComponent(projectId, isDirectory: true)
    }

    /// The `0600` handshake file written by the orchestrator (contract §1.2).
    func runtimeHandshakeFile(forProjectAt url: URL) -> URL {
        stateDirectory(forProjectAt: url).appendingPathComponent("runtime.json", isDirectory: false)
    }

    /// Overlay memory root, OUTSIDE the project (never `.archon/` in the tree).
    func memoryOverlayDirectory(forProjectAt url: URL) -> URL {
        stateDirectory(forProjectAt: url).appendingPathComponent("memory-overlay", isDirectory: true)
    }

    // MARK: - Directory management

    /// Ensures the support + per-project state directories exist. Only ever
    /// touches Application Support — never the project directory.
    @discardableResult
    func ensureStateDirectory(forProjectAt url: URL) throws -> URL {
        let dir = stateDirectory(forProjectAt: url)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: metricsDirectory, withIntermediateDirectories: true)
        return dir
    }

    // MARK: - Runtime handshake

    /// Reads and validates the handshake file, ignoring a stale one (dead pid,
    /// contract §1.2).
    func readRuntimeHandshake(forProjectAt url: URL) -> RuntimeHandshake? {
        let file = runtimeHandshakeFile(forProjectAt: url)
        guard let data = try? Data(contentsOf: file),
              let handshake = try? ArchonJSON.decode(RuntimeHandshake.self, from: data)
        else {
            return nil
        }
        guard handshake.isProcessAlive else { return nil }
        return handshake
    }

    /// Removes a stale handshake file if its process is dead.
    func clearStaleHandshake(forProjectAt url: URL) {
        let file = runtimeHandshakeFile(forProjectAt: url)
        guard let data = try? Data(contentsOf: file),
              let handshake = try? ArchonJSON.decode(RuntimeHandshake.self, from: data)
        else {
            return
        }
        if !handshake.isProcessAlive {
            try? FileManager.default.removeItem(at: file)
        }
    }

    // MARK: - Recent projects

    func loadRecentProjects() -> [RecentProject] {
        guard let data = try? Data(contentsOf: recentProjectsFile),
              let list = try? ArchonJSON.decode([RecentProject].self, from: data)
        else {
            return []
        }
        return list
    }

    /// Records a freshly-opened project at the top of the recents list
    /// (dedup by `project_id`, capped). Returns the updated list.
    @discardableResult
    func recordOpenedProject(at url: URL, now: Date = Date()) -> [RecentProject] {
        let projectId = ProjectIdentity.projectID(for: url)
        let canonical = ProjectIdentity.canonicalPath(for: url)
        let entry = RecentProject(
            projectId: projectId,
            path: canonical,
            name: url.lastPathComponent,
            lastOpenedAt: now
        )
        var list = loadRecentProjects().filter { $0.projectId != projectId }
        list.insert(entry, at: 0)
        if list.count > recentLimit {
            list = Array(list.prefix(recentLimit))
        }
        saveRecentProjects(list)
        return list
    }

    @discardableResult
    func removeRecentProject(projectId: String) -> [RecentProject] {
        let list = loadRecentProjects().filter { $0.projectId != projectId }
        saveRecentProjects(list)
        return list
    }

    private func saveRecentProjects(_ list: [RecentProject]) {
        try? FileManager.default.createDirectory(at: supportDirectory, withIntermediateDirectories: true)
        if let data = try? ArchonJSON.encode(list) {
            try? data.write(to: recentProjectsFile, options: .atomic)
        }
    }
}
