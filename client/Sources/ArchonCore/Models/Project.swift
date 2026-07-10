import Foundation

/// `GET /v3/project` response (contract §2.2). Single-project per instance
/// (Q3) — the project is fixed for the orchestrator instance lifetime.
struct ProjectInfo: Codable, Sendable, Equatable {
    var projectId: String
    var path: String
    var name: String
    var provider: String
    var openedAt: Date
    var git: GitInfo?
    var stateDir: String
}

struct GitInfo: Codable, Sendable, Equatable {
    var isRepo: Bool
    var branch: String?
    var head: String?
    var dirty: Bool?
}
