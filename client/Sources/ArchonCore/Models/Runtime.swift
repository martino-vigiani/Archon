import Foundation

/// The `0600` handshake file the orchestrator atomically writes at startup
/// (contract §1.2):
///
/// ```
/// ~/Library/Application Support/Archon/projects/<project_id>/runtime.json
/// ```
///
/// The client polls for it, reads `port` + `token`, and connects. The client
/// NEVER holds the provider API key — only this per-session bearer token.
struct RuntimeHandshake: Codable, Sendable, Equatable {
    var pv: Int
    var port: Int
    var pid: Int32
    var token: String
    var projectId: String
    var projectPath: String
    var startedAt: Date

    /// Whether the process referenced by `pid` is still alive. A stale file
    /// (dead pid) MUST be ignored by the client (contract §1.2).
    var isProcessAlive: Bool {
        // signal 0 performs error-checking without sending a signal.
        kill(pid, 0) == 0 || errno == EPERM
    }
}
