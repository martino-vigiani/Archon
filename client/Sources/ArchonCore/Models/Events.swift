import Foundation

// MARK: - Server → client event envelope (contract §3.1)

/// Every server→client frame. `seq` is a single, connection-independent,
/// monotonic, gap-free counter across ALL events on the orchestrator instance
/// (the replay cursor). Unknown `type` decodes to `.unknown` and is ignored by
/// consumers (never disconnect — REQ-ARCH-006).
struct EventEnvelope: Decodable, Sendable, Equatable {
    var v: Int
    var seq: Int64
    var ts: Date
    var type: String
    var sessionId: String?
    var taskId: String?
    var planId: String?
    var event: ServerEvent

    private enum CodingKeys: String, CodingKey {
        case v, seq, ts, type, sessionId, taskId, planId, payload
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        v = try c.decodeIfPresent(Int.self, forKey: .v) ?? 1
        seq = try c.decode(Int64.self, forKey: .seq)
        ts = try c.decode(Date.self, forKey: .ts)
        type = try c.decode(String.self, forKey: .type)
        sessionId = try c.decodeIfPresent(String.self, forKey: .sessionId)
        taskId = try c.decodeIfPresent(String.self, forKey: .taskId)
        planId = try c.decodeIfPresent(String.self, forKey: .planId)

        switch type {
        case "hello":
            event = .hello(try c.decode(HelloPayload.self, forKey: .payload))
        case "heartbeat":
            event = .heartbeat(try c.decode(HeartbeatPayload.self, forKey: .payload))
        case "session_spawned":
            event = .sessionSpawned(try c.decode(SessionSpawnedPayload.self, forKey: .payload))
        case "session_state":
            event = .sessionState(try c.decode(SessionStatePayload.self, forKey: .payload))
        case "pty_output":
            event = .ptyOutput(try c.decode(PTYOutputPayload.self, forKey: .payload))
        case "kanban_updated":
            event = .kanbanUpdated(try c.decode(KanbanUpdatedPayload.self, forKey: .payload))
        case "conductor_state":
            event = .conductorState(try c.decode(ConductorStatePayload.self, forKey: .payload))
        case "memory_changed":
            event = .memoryChanged(try c.decode(MemoryChangedPayload.self, forKey: .payload))
        case "dry_run_result":
            event = .dryRunResult(try c.decode(DryRun.self, forKey: .payload))
        case "error":
            let envelope = try c.decode(APIErrorEnvelope.self, forKey: .payload)
            event = .error(envelope.error)
        default:
            event = .unknown(type: type)
        }
    }

    /// Convenience initialiser for tests and synthetic events.
    init(
        v: Int = 1,
        seq: Int64,
        ts: Date = Date(),
        type: String,
        sessionId: String? = nil,
        taskId: String? = nil,
        planId: String? = nil,
        event: ServerEvent
    ) {
        self.v = v
        self.seq = seq
        self.ts = ts
        self.type = type
        self.sessionId = sessionId
        self.taskId = taskId
        self.planId = planId
        self.event = event
    }
}

/// The decoded, typed payload of an event (contract §3.4).
enum ServerEvent: Sendable, Equatable {
    case hello(HelloPayload)
    case heartbeat(HeartbeatPayload)
    case sessionSpawned(SessionSpawnedPayload)
    case sessionState(SessionStatePayload)
    case ptyOutput(PTYOutputPayload)
    case kanbanUpdated(KanbanUpdatedPayload)
    case conductorState(ConductorStatePayload)
    case memoryChanged(MemoryChangedPayload)
    case dryRunResult(DryRun)
    case error(APIError)
    case unknown(type: String)
}

// MARK: - Payloads

struct HelloPayload: Decodable, Sendable, Equatable {
    var pv: Int
    var orchestratorVersion: String?
    var currentSeq: Int64
    var replayWindowEvents: Int?
    var replayWindowS: Int?
    var resumeSupported: Bool?
    var conductorState: ConductorState?
    /// Set on a resume-truncation notice (contract §3.3): the client must then
    /// re-fetch full REST snapshots and resume from the newest `seq`.
    var truncated: Bool?
}

struct HeartbeatPayload: Decodable, Sendable, Equatable {
    var currentSeq: Int64
    var pong: String?
}

struct SessionSpawnedPayload: Decodable, Sendable, Equatable {
    var session: Session
}

struct SessionStatePayload: Decodable, Sendable, Equatable {
    var state: SessionState
    var status: SessionStatus
    var exitCode: Int?
    var exitReason: ExitReason?
    var idleFlagged: Bool?
    var lastActivityAt: Date?
    var elapsedS: Double?
    /// Present for `session.resource_exceeded` (e.g. `"rss"`).
    var limit: String?
}

/// Chunked terminal bytes (contract §3.4). `bytes` is base64 of the RAW PTY
/// bytes — the client owns ANSI/UTF-8 terminal parsing. `streamSeq` is
/// per-session, monotonic, gap-free; a gap triggers a `resume`.
struct PTYOutputPayload: Decodable, Sendable, Equatable {
    var streamSeq: Int64
    var encoding: String
    var bytes: String
    var dropped: Bool
    var droppedBytes: Int

    private enum CodingKeys: String, CodingKey {
        case streamSeq, encoding, bytes, dropped, droppedBytes
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        streamSeq = try c.decode(Int64.self, forKey: .streamSeq)
        encoding = try c.decodeIfPresent(String.self, forKey: .encoding) ?? "base64"
        bytes = try c.decodeIfPresent(String.self, forKey: .bytes) ?? ""
        dropped = try c.decodeIfPresent(Bool.self, forKey: .dropped) ?? false
        droppedBytes = try c.decodeIfPresent(Int.self, forKey: .droppedBytes) ?? 0
    }

    init(streamSeq: Int64, encoding: String = "base64", bytes: String, dropped: Bool = false, droppedBytes: Int = 0) {
        self.streamSeq = streamSeq
        self.encoding = encoding
        self.bytes = bytes
        self.dropped = dropped
        self.droppedBytes = droppedBytes
    }

    /// Decoded raw PTY bytes.
    var data: Data? { Data(base64Encoded: bytes) }
}

enum KanbanOp: String, Codable, Sendable, Equatable {
    case snapshot
    case created
    case updated
    case moved
    case deleted
    case unknown

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = KanbanOp(rawValue: raw) ?? .unknown
    }
}

struct ColumnPosition: Decodable, Sendable, Equatable {
    var column: BoardColumn
    var ordinal: Int
}

struct KanbanUpdatedPayload: Decodable, Sendable, Equatable {
    var op: KanbanOp
    var card: Card?
    var cards: [Card]?          // present on `snapshot`
    var cardId: String?         // present on `deleted`
    var from: ColumnPosition?
    var to: ColumnPosition?
    var boardRevision: Int
}

struct ConductorStatePayload: Decodable, Sendable, Equatable {
    var state: ConductorState
    var detail: String?
    var planId: String?
    var intentId: String?
}

enum MemoryOp: String, Codable, Sendable, Equatable {
    case created
    case updated
    case deleted
    case unknown

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = MemoryOp(rawValue: raw) ?? .unknown
    }
}

struct MemoryChangedPayload: Decodable, Sendable, Equatable {
    var scopeDir: String
    var filename: String
    var kind: MemoryKind
    var op: MemoryOp
    var revision: Int
    var checksum: String?
    var initiator: Initiator?
}

// MARK: - Client → server control frames (contract §3.3)

/// Stream topics for subscribe/unsubscribe (REQ-BE-045).
enum StreamTopic: String, Codable, Sendable, Equatable, CaseIterable {
    case session
    case ptyOutput = "pty_output"
    case kanban
    case conductor
    case memory
    case policy
}

/// Small client→server control frames sent over the same socket.
enum ClientControlFrame: Encodable, Sendable, Equatable {
    case resume(afterSeq: Int64)
    case subscribe(topics: [StreamTopic])
    case unsubscribe(topics: [StreamTopic])
    case ping(id: String)

    private enum CodingKeys: String, CodingKey {
        case type
        case afterSeq = "after_seq"
        case topics
        case id
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        switch self {
        case .resume(let afterSeq):
            try c.encode("resume", forKey: .type)
            try c.encode(afterSeq, forKey: .afterSeq)
        case .subscribe(let topics):
            try c.encode("subscribe", forKey: .type)
            try c.encode(topics.map(\.rawValue), forKey: .topics)
        case .unsubscribe(let topics):
            try c.encode("unsubscribe", forKey: .type)
            try c.encode(topics.map(\.rawValue), forKey: .topics)
        case .ping(let id):
            try c.encode("ping", forKey: .type)
            try c.encode(id, forKey: .id)
        }
    }

    /// JSON text ready to send over the socket. Note: encoded with a plain
    /// encoder — `CodingKeys` already carry the exact wire names.
    func jsonText() throws -> String {
        let encoder = JSONEncoder()
        let data = try encoder.encode(self)
        return String(decoding: data, as: UTF8.self)
    }
}

// MARK: - Event replay cursor (contract §2.7)

struct EventReplayResponse: Decodable, Sendable, Equatable {
    var events: [EventEnvelope]
    var fromSeq: Int64?
    var nextSeq: Int64?
    var truncated: Bool
}
