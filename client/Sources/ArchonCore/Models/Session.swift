import Foundation

/// Lifecycle state machine (REQ-ARCH-020 / contract §2.3). The transient
/// `reconnecting` is client-only and never emitted by the server. The client
/// MUST NOT infer `completed` from output content.
enum SessionState: String, Codable, Sendable, Equatable {
    case requested
    case spawning
    case running
    case completed
    case failed
    case killed
    case reconnecting   // client-only
    case unknown

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = SessionState(rawValue: raw) ?? .unknown
    }

    var isTerminal: Bool {
        switch self {
        case .completed, .failed, .killed: return true
        default: return false
        }
    }
}

/// Five-state badge vocabulary shared by terminals, kanban badges, and the
/// dashboard (REQ-UX-060 / contract §2.3).
enum SessionStatus: String, Codable, Sendable, Equatable, CaseIterable {
    case idle
    case running
    case blocked
    case error
    case done
    case unknown

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = SessionStatus(rawValue: raw) ?? .unknown
    }
}

enum ExitReason: String, Codable, Sendable, Equatable {
    case normal
    case killed
    case crashRecovery = "crash_recovery"
    case resourceExceeded = "resource_exceeded"
    case spawnFailed = "spawn_failed"
    case unknown

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = ExitReason(rawValue: raw) ?? .unknown
    }
}

/// Canonical session object (contract §2.3), returned by list/detail and
/// embedded in `session_spawned` events.
struct Session: Codable, Sendable, Equatable, Identifiable {
    var sessionId: String
    var state: SessionState
    var status: SessionStatus
    var provider: String
    var cwd: String
    var cardId: String?
    var initiator: Initiator
    var requestId: String?
    var pid: Int32?
    var createdAt: Date
    var startedAt: Date?
    var endedAt: Date?
    var exitCode: Int?
    var exitReason: ExitReason?
    var idleFlagged: Bool
    var lastActivityAt: Date?
    var lastOutputSeq: Int64?
    var elapsedS: Double?

    var id: String { sessionId }
}

/// Who caused a mutation (contract §0). Project-dir writes require `user`.
enum Initiator: String, Codable, Sendable, Equatable {
    case user
    case conductor
    case unknown

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = Initiator(rawValue: raw) ?? .unknown
    }
}

/// `GET /v3/sessions` snapshot (contract §2.3).
struct SessionsListResponse: Codable, Sendable, Equatable {
    var sessions: [Session]
    var count: Int
    var ceiling: Int
    var cap: CapInfo
}

struct CapInfo: Codable, Sendable, Equatable {
    var regime: CapRegime
    var value: Int?
}

enum CapRegime: String, Codable, Sendable, Equatable {
    case auto
    case user
    case unknown

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = CapRegime(rawValue: raw) ?? .unknown
    }
}

// MARK: - Requests / responses

/// `POST /v3/sessions` body (contract §2.3).
struct SpawnSessionRequest: Codable, Sendable, Equatable {
    var requestId: String
    var cwd: String
    var cardId: String?
    var initiator: Initiator
    var prompt: String?
    var cap: Int?

    init(
        requestId: String = ULID.generate(),
        cwd: String,
        cardId: String? = nil,
        initiator: Initiator = .user,
        prompt: String? = nil,
        cap: Int? = nil
    ) {
        self.requestId = requestId
        self.cwd = cwd
        self.cardId = cardId
        self.initiator = initiator
        self.prompt = prompt
        self.cap = cap
    }
}

/// `201` spawn result, or the `202` spawn-deferred admission-control payload.
struct SpawnSessionResponse: Codable, Sendable, Equatable {
    var session: Session?
    var deferred: Bool?
    var reason: String?
    var queuedRequestId: String?
}

struct SessionDetailResponse: Codable, Sendable, Equatable {
    var session: Session
    var recentOutputSeqRange: SeqRange?
}

struct SeqRange: Codable, Sendable, Equatable {
    var first: Int64
    var last: Int64
}

struct KillSessionRequest: Codable, Sendable, Equatable {
    var graceMs: Int?
    var force: Bool?

    init(graceMs: Int? = 5000, force: Bool? = true) {
        self.graceMs = graceMs
        self.force = force
    }
}

struct KillSessionResponse: Codable, Sendable, Equatable {
    var sessionId: String
    var state: SessionState
    var accepted: Bool
}

struct FlagIdleRequest: Codable, Sendable, Equatable {
    var flagged: Bool

    init(flagged: Bool = true) { self.flagged = flagged }
}

struct FlagIdleResponse: Codable, Sendable, Equatable {
    var sessionId: String
    var idleFlagged: Bool
}
