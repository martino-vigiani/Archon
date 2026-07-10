import Foundation
import Observation

// ============================================================================
// Terminals · Store · TerminalSession
//
// The observable per-terminal projection: canonical session metadata (§2.3)
// plus the live PTY buffer (emulator + scrollback) and the stream_seq
// assembler. One instance per `session_id`. Content changes set `needsRender`;
// the store's `FrameCoalescer` bumps `renderTick` ≤ once/frame to drive the
// render view (REQ-PERF-020).
// ============================================================================

@MainActor
@Observable
final class TerminalSession: Identifiable {

    let id: String
    /// 1-based display index (assigned by the store in spawn order, REQ-UX-011).
    let index: Int

    private(set) var meta: Session

    /// PTY rendering engine + 10k-line scrollback. Not observed directly; the
    /// view redraws on `renderTick`.
    @ObservationIgnored let emulator: TerminalEmulator

    /// Bumped (coalesced) when the emulator gains content — the render view's
    /// invalidation trigger.
    var renderTick: Int = 0

    /// Set true on new PTY content; the store's coalescer clears it via `flushRender()`.
    @ObservationIgnored var needsRender: Bool = false

    @ObservationIgnored private var assembler = PTYStreamAssembler()

    init(meta: Session, index: Int, scrollbackCapacity: Int = 10_000) {
        self.id = meta.sessionId
        self.index = index
        self.meta = meta
        self.emulator = TerminalEmulator(scrollbackCapacity: scrollbackCapacity)
    }

    // MARK: - Display

    /// Short human name derived from the working directory (REQ-UX-011a).
    var displayName: String {
        let base = URL(fileURLWithPath: meta.cwd).lastPathComponent
        return base.isEmpty ? shortId : base
    }

    /// A short, stable identifier fragment for dense rows.
    var shortId: String {
        String(id.suffix(6))
    }

    /// The provider / agent type, prettified (REQ-UX-011b). MVP: Claude Code only.
    var agentType: String {
        switch meta.provider {
        case "claude_code": return "Claude Code"
        case "": return "Agent"
        default: return meta.provider.replacingOccurrences(of: "_", with: " ").capitalized
        }
    }

    var status: SessionStatus { meta.status }
    var state: SessionState { meta.state }
    var isTerminal: Bool { meta.state.isTerminal }
    var idleFlagged: Bool { meta.idleFlagged }

    // MARK: - Elapsed (driven by the store's 1 Hz clock)

    /// Wall-clock seconds since the session started (or was created), frozen at
    /// `ended_at`/elapsed for terminated sessions.
    func elapsedSeconds(now: Date) -> Int {
        if let elapsed = meta.elapsedS, meta.state.isTerminal {
            return Int(elapsed.rounded())
        }
        let start = meta.startedAt ?? meta.createdAt
        let end = meta.endedAt ?? now
        return Swift.max(0, Int(end.timeIntervalSince(start).rounded()))
    }

    // MARK: - Signals

    /// True when the last output or status indicates an error (REQ-UX-014):
    /// surfaced as a subtle border in the grid without requiring focus.
    var hasRecentError: Bool {
        if meta.status == .error { return true }
        let tokens = ["error", "failed", "failure", "exception", "traceback", "fatal", "panic"]
        for line in emulator.recentLines(10) {
            let lower = line.plainText.lowercased()
            if tokens.contains(where: { lower.contains($0) }) { return true }
        }
        return false
    }

    /// The most recent non-blank output line, trimmed for the dashboard/pane
    /// header activity cue.
    var activitySummary: String {
        for line in emulator.recentLines(6).reversed() where !line.isEmpty {
            let text = line.plainText.trimmingCharacters(in: .whitespacesAndNewlines)
            if text.isEmpty { continue }
            return text.count > 140 ? String(text.prefix(140)) + "…" : text
        }
        return ""
    }

    // MARK: - Reducers (store-driven)

    func replaceMeta(_ session: Session) {
        meta = session
    }

    func setIdleFlagged(_ flagged: Bool) {
        meta.idleFlagged = flagged
    }

    func applyStatePayload(_ p: SessionStatePayload) {
        meta.state = p.state
        meta.status = p.status
        meta.exitCode = p.exitCode ?? meta.exitCode
        meta.exitReason = p.exitReason ?? meta.exitReason
        meta.idleFlagged = p.idleFlagged ?? meta.idleFlagged
        meta.lastActivityAt = p.lastActivityAt ?? meta.lastActivityAt
        meta.elapsedS = p.elapsedS ?? meta.elapsedS
        if p.state.isTerminal, meta.endedAt == nil {
            meta.endedAt = p.lastActivityAt ?? Date()
        }
    }

    /// Ingests one `pty_output` chunk: classifies ordering (drop/gap markers),
    /// then decodes base64 and feeds the emulator. Sets `needsRender`.
    func ingest(_ payload: PTYOutputPayload) {
        switch assembler.classify(streamSeq: payload.streamSeq, dropped: payload.dropped, droppedBytes: payload.droppedBytes) {
        case .duplicate:
            return
        case .apply:
            break
        case .gapMarker:
            emulator.insertMarker(Self.trimMarker(bytes: 0))
        case .droppedMarker(let bytes):
            emulator.insertMarker(Self.trimMarker(bytes: bytes))
        }
        if let data = payload.data, !data.isEmpty {
            emulator.feed(data)
        }
        needsRender = true
    }

    private static func trimMarker(bytes: Int) -> String {
        bytes > 0 ? "── output trimmed (\(bytes) bytes) ──" : "── output trimmed ──"
    }

    /// The full retained transcript as plain text (for "Copy output", REQ-UX-012).
    func fullTranscript() -> String {
        let total = emulator.lineCount
        var lines: [String] = []
        lines.reserveCapacity(total)
        for i in 0..<total {
            lines.append(emulator.line(at: i).plainText)
        }
        return lines.joined(separator: "\n")
    }

    /// Applies any pending render (called by the store's frame coalescer).
    /// Returns whether a visible change was flushed.
    @discardableResult
    func flushRender() -> Bool {
        guard needsRender else { return false }
        needsRender = false
        renderTick &+= 1
        return true
    }
}
