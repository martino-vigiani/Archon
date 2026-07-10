import Foundation

/// Memory file kind (contract §2.6). `CLAUDE.md`/`AGENTS.md` are agent-native
/// files discovered per-directory in the project tree; `overlay` holds
/// Archon-specific metadata stored OUTSIDE the project (§A3 zero-footprint).
enum MemoryKind: String, Codable, Sendable, Equatable {
    case claude = "CLAUDE.md"
    case agents = "AGENTS.md"
    case overlay
    case unknown

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = MemoryKind(rawValue: raw) ?? .unknown
    }
}

enum MemoryLocation: String, Codable, Sendable, Equatable {
    case project
    case overlay
    case unknown

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = MemoryLocation(rawValue: raw) ?? .unknown
    }
}

struct MemoryFile: Codable, Sendable, Equatable, Identifiable {
    var scopeDir: String
    var filename: String
    var kind: MemoryKind
    var location: MemoryLocation
    var size: Int
    var mtime: Date
    var owner: Initiator
    var revision: Int
    var checksum: String
    var editable: Bool

    /// Stable identity across list refreshes.
    var id: String { "\(scopeDir)::\(filename)" }
}

struct MemoryScope: Codable, Sendable, Equatable, Identifiable {
    var scopeDir: String
    var files: [MemoryFile]

    var id: String { scopeDir }
}

struct MemoryListResponse: Codable, Sendable, Equatable {
    var scopes: [MemoryScope]
}

struct MemoryReadResponse: Codable, Sendable, Equatable {
    var file: MemoryFile
    var content: String
}

/// `PUT /v3/memory/file` — user-initiated writes only (§A3). `initiator != user`
/// → `403 conductor_write_forbidden`.
struct MemoryWriteRequest: Codable, Sendable, Equatable {
    var scopeDir: String
    var filename: String
    var content: String
    var baseRevision: Int
    var baseChecksum: String
    var initiator: Initiator

    init(
        scopeDir: String,
        filename: String,
        content: String,
        baseRevision: Int,
        baseChecksum: String,
        initiator: Initiator = .user
    ) {
        self.scopeDir = scopeDir
        self.filename = filename
        self.content = content
        self.baseRevision = baseRevision
        self.baseChecksum = baseChecksum
        self.initiator = initiator
    }
}

struct MemoryWriteResponse: Codable, Sendable, Equatable {
    var file: MemoryFile
}

struct MemoryDeleteRequest: Codable, Sendable, Equatable {
    var baseRevision: Int
    var initiator: Initiator

    init(baseRevision: Int, initiator: Initiator = .user) {
        self.baseRevision = baseRevision
        self.initiator = initiator
    }
}

struct MemoryDeleteResponse: Codable, Sendable, Equatable {
    var deleted: Bool
}
