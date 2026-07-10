import Foundation

/// A Conductor-authored memory-edit *proposal* (contract §2.4 plan action
/// `propose_memory_edit`). The Conductor NEVER writes project files (addendum
/// §A3, the hard rule) — it can only propose. The Memory view renders this as a
/// diff-style review card; the user's Accept becomes an `initiator: .user`
/// write, Reject discards it.
///
/// The integrator (Conductor sector) constructs these from confirmed plan
/// actions and hands them to `MemoryStore.addProposal(_:)`.
struct MemoryProposal: Identifiable, Sendable, Equatable {
    let id: String
    let scopeDir: String
    let filename: String
    let baseRevision: Int
    let baseChecksum: String
    let originalContent: String
    let proposedContent: String
    let rationale: String?

    init(
        id: String = ULID.generate(),
        scopeDir: String,
        filename: String,
        baseRevision: Int,
        baseChecksum: String,
        originalContent: String,
        proposedContent: String,
        rationale: String? = nil
    ) {
        self.id = id
        self.scopeDir = scopeDir
        self.filename = filename
        self.baseRevision = baseRevision
        self.baseChecksum = baseChecksum
        self.originalContent = originalContent
        self.proposedContent = proposedContent
        self.rationale = rationale
    }

    /// Stable identity of the file this proposal targets.
    var fileKey: String { "\(scopeDir)::\(filename)" }
}
