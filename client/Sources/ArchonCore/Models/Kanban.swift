import Foundation

/// The five fixed, ordered, non-renameable board columns (REQ-UX-050 /
/// contract §2.5).
enum BoardColumn: String, Codable, Sendable, Equatable, CaseIterable, Identifiable {
    case queued
    case inProgress = "in_progress"
    case blocked
    case review
    case done

    var id: String { rawValue }

    /// User-facing display title.
    var title: String {
        switch self {
        case .queued: return "Queued"
        case .inProgress: return "In Progress"
        case .blocked: return "Blocked"
        case .review: return "Review"
        case .done: return "Done"
        }
    }
}

enum CardPriority: String, Codable, Sendable, Equatable {
    case low
    case normal
    case high
    case unknown

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = CardPriority(rawValue: raw) ?? .unknown
    }
}

/// Kanban card object (contract §2.5).
struct Card: Codable, Sendable, Equatable, Identifiable {
    var cardId: String
    var title: String
    var body: String?
    var column: BoardColumn
    var ordinal: Int
    var priority: CardPriority
    var provenance: Initiator
    var sessionId: String?
    var status: SessionStatus
    var revision: Int
    var createdAt: Date
    var updatedAt: Date

    var id: String { cardId }
}

struct KanbanSnapshotResponse: Codable, Sendable, Equatable {
    var columns: [BoardColumn]
    var cards: [Card]
    var boardRevision: Int
}

// MARK: - Requests / responses

struct CreateCardRequest: Codable, Sendable, Equatable {
    var requestId: String
    var title: String
    var body: String?
    var column: BoardColumn
    var priority: CardPriority
    var provenance: Initiator

    init(
        requestId: String = ULID.generate(),
        title: String,
        body: String? = nil,
        column: BoardColumn = .queued,
        priority: CardPriority = .normal,
        provenance: Initiator = .user
    ) {
        self.requestId = requestId
        self.title = title
        self.body = body
        self.column = column
        self.priority = priority
        self.provenance = provenance
    }
}

struct CardResponse: Codable, Sendable, Equatable {
    var card: Card
}

/// `PATCH /v3/kanban/cards/{id}` — any subset of mutable fields with an
/// optimistic-concurrency `base_revision` (contract §2.5).
struct PatchCardRequest: Codable, Sendable, Equatable {
    var baseRevision: Int
    var title: String?
    var body: String?
    var priority: CardPriority?
    var provenance: Initiator

    init(
        baseRevision: Int,
        title: String? = nil,
        body: String? = nil,
        priority: CardPriority? = nil,
        provenance: Initiator = .user
    ) {
        self.baseRevision = baseRevision
        self.title = title
        self.body = body
        self.priority = priority
        self.provenance = provenance
    }
}

struct MoveCardRequest: Codable, Sendable, Equatable {
    var baseRevision: Int
    var toColumn: BoardColumn
    var toOrdinal: Int
    var provenance: Initiator

    init(
        baseRevision: Int,
        toColumn: BoardColumn,
        toOrdinal: Int,
        provenance: Initiator = .user
    ) {
        self.baseRevision = baseRevision
        self.toColumn = toColumn
        self.toOrdinal = toOrdinal
        self.provenance = provenance
    }
}

struct MoveCardResponse: Codable, Sendable, Equatable {
    var card: Card
    var boardRevision: Int
}

struct DeleteCardRequest: Codable, Sendable, Equatable {
    var baseRevision: Int
    var provenance: Initiator

    init(baseRevision: Int, provenance: Initiator = .user) {
        self.baseRevision = baseRevision
        self.provenance = provenance
    }
}

struct DeleteCardResponse: Codable, Sendable, Equatable {
    var cardId: String
    var deleted: Bool
}
