import Foundation

/// One turn in the Conductor exchange log (REQ-UX-031). A `user` turn may be a
/// live transcript preview (`isPartial`), a finalized voice intent, or typed
/// text; a `conductor` turn is planning "thinking" text or a reply.
struct ConductorExchange: Identifiable, Sendable, Equatable {
    enum Role: Sendable, Equatable {
        case user
        case conductor
    }

    let id: String
    var role: Role
    var text: String
    var timestamp: Date
    /// True while this is a live, not-yet-finalized transcript preview.
    var isPartial: Bool

    init(id: String = UUID().uuidString, role: Role, text: String, timestamp: Date = Date(), isPartial: Bool = false) {
        self.id = id
        self.role = role
        self.text = text
        self.timestamp = timestamp
        self.isPartial = isPartial
    }
}

/// A typed, recoverable Conductor/provider error surfaced in the surface with a
/// retry affordance (Addendum §A4). Never a raw stack trace (REQ-UX-093).
struct ConductorError: Sendable, Equatable {
    var title: String
    var message: String
    var retriable: Bool

    /// Builds a plain-language error from a wire `APIError`.
    init(apiError: APIError) {
        self.retriable = apiError.retriable
        switch apiError.code {
        case .rateLimited:
            title = "Rate limited"
            message = "Claude is rate-limiting requests. Retrying shortly."
        case .providerError:
            title = "Claude unavailable"
            message = "The Claude API returned an error. You can retry."
        case .planExpired:
            title = "Plan expired"
            message = "This plan timed out before confirmation. Ask again."
        case .orchestratorError:
            title = "Orchestrator error"
            message = "The local orchestrator hit an internal error."
        default:
            title = "Conductor error"
            message = apiError.message.isEmpty ? "Something went wrong." : apiError.message
        }
    }

    init(title: String, message: String, retriable: Bool) {
        self.title = title
        self.message = message
        self.retriable = retriable
    }
}

// MARK: - Plan action presentation (REQ-ARCH-042 destructive distinction)

extension PlanActionKind {
    var symbolName: String {
        switch self {
        case .spawnSession: return "terminal.fill"
        case .createCard: return "plus.rectangle"
        case .updateCard: return "pencil"
        case .moveCard: return "arrow.left.arrow.right"
        case .deleteCard: return "trash"
        case .killSession: return "xmark.circle"
        case .proposeMemoryEdit: return "doc.badge.ellipsis"
        case .unknown: return "questionmark.circle"
        }
    }

    var label: String {
        switch self {
        case .spawnSession: return "Spawn terminal"
        case .createCard: return "Create card"
        case .updateCard: return "Update card"
        case .moveCard: return "Move card"
        case .deleteCard: return "Delete card"
        case .killSession: return "Stop terminal"
        case .proposeMemoryEdit: return "Propose memory edit"
        case .unknown: return "Action"
        }
    }
}

extension PlanAction {
    /// Kill/delete are destructive; the contract also flags them via `destructive`.
    var isDestructive: Bool {
        destructive || kind == .deleteCard || kind == .killSession
    }

    /// Memory proposals are handed off for explicit user review — the Conductor
    /// never writes them itself (Addendum §A3).
    var isMemoryProposal: Bool { kind == .proposeMemoryEdit }

    /// A one-line secondary description for the action row.
    var detailLine: String? {
        switch kind {
        case .spawnSession:
            if let prompt, !prompt.isEmpty { return prompt }
            return cwd
        case .createCard, .updateCard, .moveCard, .deleteCard:
            if let title, !title.isEmpty {
                if let column { return "\(title) → \(column.title)" }
                return title
            }
            return rationale
        default:
            return rationale
        }
    }
}

/// Formatting helpers for the dry-run pre-flight estimate line (Q14). Produces
/// a compact single line, or "No estimate" when the estimate wasn't ready in
/// time (never blocks past 1.5 s).
enum DryRunFormat {
    static func summaryLine(_ dryRun: DryRun?) -> String {
        guard let dryRun, dryRun.estimateReady else { return "No estimate" }
        var parts: [String] = []
        if let count = dryRun.estimatedSessionCount {
            parts.append("~\(count) terminal\(count == 1 ? "" : "s")")
        }
        if let tokens = dryRun.estimatedTokens {
            parts.append("~\(formatTokens(tokens)) tokens")
        }
        if let seconds = dryRun.estimatedDurationS {
            parts.append("~\(formatDuration(seconds))")
        }
        return parts.isEmpty ? "Estimate ready" : parts.joined(separator: " · ")
    }

    static func formatTokens(_ tokens: Int) -> String {
        if tokens >= 1000 {
            let k = Double(tokens) / 1000
            return String(format: k >= 10 ? "%.0fk" : "%.1fk", k)
        }
        return "\(tokens)"
    }

    static func formatDuration(_ seconds: Double) -> String {
        if seconds < 60 { return "\(Int(seconds.rounded()))s" }
        let minutes = Int((seconds / 60).rounded())
        return "\(minutes)m"
    }
}
