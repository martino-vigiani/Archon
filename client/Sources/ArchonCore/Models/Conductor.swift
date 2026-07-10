import Foundation

/// The six canonical orb / Conductor behavioural states (REQ-UX-040, Q18 /
/// contract §3.4). `listening` is client-local (WhisperKit push-to-talk); the
/// server owns the other five.
enum ConductorState: String, Codable, Sendable, Equatable, CaseIterable {
    case idle
    case listening   // client-local
    case thinking
    case spawning
    case streaming
    case error
    case unknown

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = ConductorState(rawValue: raw) ?? .unknown
    }
}

/// `POST /v3/conductor/message` body (contract §2.4). Only finalized text ever
/// leaves the client (REQ-ARCH-032).
struct ConductorMessageRequest: Codable, Sendable, Equatable {
    var requestId: String
    var text: String
    var source: IntentSource
    var context: ConductorContext?

    init(
        requestId: String = ULID.generate(),
        text: String,
        source: IntentSource,
        context: ConductorContext? = nil
    ) {
        self.requestId = requestId
        self.text = text
        self.source = source
        self.context = context
    }
}

enum IntentSource: String, Codable, Sendable, Equatable {
    case text
    case voiceTranscript = "voice_transcript"
}

struct ConductorContext: Codable, Sendable, Equatable {
    var activeDir: String?
    var selectedCardId: String?
    var cap: Int?

    init(activeDir: String? = nil, selectedCardId: String? = nil, cap: Int? = nil) {
        self.activeDir = activeDir
        self.selectedCardId = selectedCardId
        self.cap = cap
    }
}

/// `200` response from `POST /v3/conductor/message` (contract §2.4).
struct ConductorMessageResponse: Codable, Sendable, Equatable {
    var intentId: String
    var plan: Plan
    var dryRun: DryRun
    var expiresAt: Date
}

struct Plan: Codable, Sendable, Equatable, Identifiable {
    var planId: String
    var summary: String
    var proposedSessionCount: Int
    var appliedCap: Int?
    var ceiling: Int
    var finalCount: Int
    var reductionReason: String?
    var actions: [PlanAction]

    var id: String { planId }
}

struct PlanAction: Codable, Sendable, Equatable, Identifiable {
    var actionId: String
    var kind: PlanActionKind
    var cwd: String?
    var prompt: String?
    var cardRef: String?
    var column: BoardColumn?
    var title: String?
    var rationale: String?
    var destructive: Bool

    var id: String { actionId }
}

enum PlanActionKind: String, Codable, Sendable, Equatable {
    case spawnSession = "spawn_session"
    case createCard = "create_card"
    case updateCard = "update_card"
    case moveCard = "move_card"
    case deleteCard = "delete_card"
    case killSession = "kill_session"
    case proposeMemoryEdit = "propose_memory_edit"
    case unknown

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = PlanActionKind(rawValue: raw) ?? .unknown
    }
}

/// Dry-run pre-flight estimate (Q14). When it cannot be produced within
/// `dry_run_max_s`, `estimateReady == false` and figures are null; a later
/// `dry_run_result` WS event MAY deliver it.
struct DryRun: Codable, Sendable, Equatable {
    var estimateReady: Bool
    var estimatedSessionCount: Int?
    var estimatedTokens: Int?
    var estimatedDurationS: Double?
    var warnings: [String]?
}

// MARK: - Confirm / cancel

struct ConfirmPlanRequest: Codable, Sendable, Equatable {
    var requestId: String
    var cap: Int?
    var autoApply: Bool?

    init(requestId: String = ULID.generate(), cap: Int? = nil, autoApply: Bool? = nil) {
        self.requestId = requestId
        self.cap = cap
        self.autoApply = autoApply
    }
}

struct ConfirmPlanResponse: Codable, Sendable, Equatable {
    var planId: String
    var status: PlanExecutionStatus
    var createdSessionIds: [String]?
    var createdCardIds: [String]?
    var appliedCap: Int?
    var finalCount: Int?
    var actionResults: [PlanActionResult]?
}

enum PlanExecutionStatus: String, Codable, Sendable, Equatable {
    case executing
    case partial
    case cancelled
    case unknown

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = PlanExecutionStatus(rawValue: raw) ?? .unknown
    }
}

struct PlanActionResult: Codable, Sendable, Equatable {
    var actionId: String
    var ok: Bool
    var error: APIError?
}

struct CancelPlanResponse: Codable, Sendable, Equatable {
    var planId: String
    var status: PlanExecutionStatus
}
