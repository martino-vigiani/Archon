import Foundation

/// Shared, deterministic formatting for board card metadata.
enum BoardFormat {

    private static let timestamp: DateFormatter = {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "MMM d, HH:mm"
        return formatter
    }()

    static func shortTime(_ date: Date) -> String {
        timestamp.string(from: date)
    }

    /// A compact, opaque session reference (contract §0: ids are opaque; show a
    /// short suffix so distinct sessions read differently without implying order).
    static func sessionLabel(_ sessionId: String?) -> String {
        guard let sessionId, !sessionId.isEmpty else { return "Unassigned" }
        let suffix = sessionId.count > 6 ? String(sessionId.suffix(6)) : sessionId
        return "Session ·\(suffix)"
    }

    /// Title clamped to the contract's 80-char display bound (REQ-UX-051).
    static func clampTitle(_ title: String, max: Int = 80) -> String {
        guard title.count > max else { return title }
        return String(title.prefix(max - 1)) + "…"
    }
}
