import Testing
import Foundation
@testable import Archon

@Suite("ProjectStore paths & recents")
struct ProjectStoreTests {

    private func makeTempStore() throws -> (ProjectStore, URL) {
        let base = FileManager.default.temporaryDirectory
            .appendingPathComponent("archon-tests-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: base, withIntermediateDirectories: true)
        return (ProjectStore(supportDirectory: base), base)
    }

    @Test("project_id is deterministic, lowercase 64-hex")
    func projectIDShape() {
        let url = URL(fileURLWithPath: "/Users/mara/subralabs-v2")
        let id = ProjectIdentity.projectID(for: url)
        #expect(id.count == 64)
        #expect(id == id.lowercased())
        #expect(id.allSatisfy { $0.isHexDigit })
        // Deterministic
        #expect(id == ProjectIdentity.projectID(for: url))
    }

    @Test("state dir lives under support/projects/<project_id>")
    func stateDirectoryLayout() throws {
        let (store, base) = try makeTempStore()
        let project = URL(fileURLWithPath: "/tmp/some-project")
        let id = ProjectIdentity.projectID(for: project)
        let dir = store.stateDirectory(forProjectAt: project)
        #expect(dir.path.hasPrefix(base.path))
        #expect(dir.lastPathComponent == id)
        #expect(dir.path.contains("/projects/"))
        // Runtime + overlay paths are inside the state dir (never the project).
        #expect(store.runtimeHandshakeFile(forProjectAt: project).lastPathComponent == "runtime.json")
        #expect(!store.memoryOverlayDirectory(forProjectAt: project).path.contains("/tmp/some-project/"))
    }

    @Test("ensureStateDirectory creates dirs outside the project (§A3)")
    func ensureStateDirectoryZeroFootprint() throws {
        let (store, base) = try makeTempStore()
        // A real project dir we must never write into.
        let project = base.appendingPathComponent("myproject", isDirectory: true)
        try FileManager.default.createDirectory(at: project, withIntermediateDirectories: true)

        try store.ensureStateDirectory(forProjectAt: project)
        // Project dir stays empty (byte-identical / no .archon).
        let contents = try FileManager.default.contentsOfDirectory(atPath: project.path)
        #expect(contents.isEmpty)
        // State dir exists under support.
        var isDir: ObjCBool = false
        #expect(FileManager.default.fileExists(atPath: store.stateDirectory(forProjectAt: project).path, isDirectory: &isDir))
        #expect(isDir.boolValue)
    }

    @Test("recent projects roundtrip: dedup + most-recent-first + cap")
    func recentsRoundtrip() throws {
        let (store, _) = try makeTempStore()
        let a = URL(fileURLWithPath: "/tmp/a")
        let b = URL(fileURLWithPath: "/tmp/b")

        _ = store.recordOpenedProject(at: a)
        var list = store.recordOpenedProject(at: b)
        #expect(list.count == 2)
        #expect(list.first?.name == "b")     // most recent first

        // Re-open `a` → moves to front, no duplicate.
        list = store.recordOpenedProject(at: a)
        #expect(list.count == 2)
        #expect(list.first?.name == "a")

        // Persisted across a fresh store instance pointing at the same dir.
        let reloaded = ProjectStore(supportDirectory: store.supportDirectory).loadRecentProjects()
        #expect(reloaded.count == 2)
        #expect(reloaded.first?.name == "a")
    }

    @Test("recents capped at recentLimit")
    func recentsCap() throws {
        let base = FileManager.default.temporaryDirectory
            .appendingPathComponent("archon-tests-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: base, withIntermediateDirectories: true)
        let store = ProjectStore(supportDirectory: base, recentLimit: 3)
        for i in 0..<6 {
            _ = store.recordOpenedProject(at: URL(fileURLWithPath: "/tmp/p\(i)"))
        }
        let list = store.loadRecentProjects()
        #expect(list.count == 3)
        #expect(list.first?.name == "p5")
    }

    @Test("live handshake reads back; dead-pid handshake is ignored")
    func handshakeReadValidatesPid() throws {
        let (store, _) = try makeTempStore()
        let project = URL(fileURLWithPath: "/tmp/handshake-project")
        try store.ensureStateDirectory(forProjectAt: project)

        // Live handshake: use our own pid.
        let livePid = ProcessInfo.processInfo.processIdentifier
        let live = RuntimeHandshake(
            pv: 1, port: 51423, pid: livePid, token: String(repeating: "a", count: 64),
            projectId: ProjectIdentity.projectID(for: project),
            projectPath: ProjectIdentity.canonicalPath(for: project),
            startedAt: Date()
        )
        try ArchonJSON.encode(live).write(to: store.runtimeHandshakeFile(forProjectAt: project))
        let readLive = store.readRuntimeHandshake(forProjectAt: project)
        #expect(readLive?.port == 51423)

        // Dead pid → ignored.
        let dead = RuntimeHandshake(
            pv: 1, port: 51423, pid: 999_999, token: "t",
            projectId: "x", projectPath: "/tmp/handshake-project", startedAt: Date()
        )
        try ArchonJSON.encode(dead).write(to: store.runtimeHandshakeFile(forProjectAt: project))
        #expect(store.readRuntimeHandshake(forProjectAt: project) == nil)
    }
}
