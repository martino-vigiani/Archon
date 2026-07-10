import Foundation

// ============================================================================
// Terminals · Model · PTYStreamAssembler
//
// Per-session `stream_seq` ordering + coalesce/drop-with-marker classification
// (contract §3.4). `pty_output` chunks carry a per-session, monotonic, gap-free
// `stream_seq`; the server may coalesce and then DROP-with-marker under
// backpressure (`dropped:true`, `dropped_bytes:N`) resetting continuity. This
// pure, testable classifier turns each incoming chunk into a render decision.
// ============================================================================

/// What to do with an incoming `pty_output` chunk after ordering analysis.
enum PTYChunkDecision: Sendable, Equatable {
    /// In-order (or first) chunk: decode base64 + feed the emulator.
    case apply
    /// `stream_seq` ≤ last seen (a replayed/duplicate frame): drop silently.
    case duplicate
    /// `stream_seq` skipped ahead: insert an "output trimmed" marker, then apply
    /// the chunk (`missing` = the first absent stream_seq, for diagnostics).
    case gapMarker(missing: Int64)
    /// Server dropped-with-marker (`dropped:true`): insert an "output trimmed"
    /// marker, then apply whatever bytes accompanied the marker chunk.
    case droppedMarker(bytes: Int)
}

/// Tracks a single session's `stream_seq` and classifies each chunk. Pure value
/// type — the store keeps one per session.
struct PTYStreamAssembler: Sendable, Equatable {

    private(set) var lastStreamSeq: Int64?

    init(lastStreamSeq: Int64? = nil) {
        self.lastStreamSeq = lastStreamSeq
    }

    /// Classifies a chunk and advances internal state. The server's explicit
    /// `dropped` marker takes precedence over gap detection (it already resets
    /// continuity), so we honour it first.
    mutating func classify(streamSeq: Int64, dropped: Bool, droppedBytes: Int) -> PTYChunkDecision {
        if dropped {
            lastStreamSeq = streamSeq
            return .droppedMarker(bytes: Swift.max(0, droppedBytes))
        }
        guard let last = lastStreamSeq else {
            lastStreamSeq = streamSeq
            return .apply
        }
        if streamSeq <= last {
            return .duplicate
        }
        if streamSeq == last + 1 {
            lastStreamSeq = streamSeq
            return .apply
        }
        // streamSeq > last + 1 → a gap: the missing bytes are unrecoverable here
        // (the global-seq resume path recovers ordering); mark the break.
        let missing = last + 1
        lastStreamSeq = streamSeq
        return .gapMarker(missing: missing)
    }

    mutating func reset() {
        lastStreamSeq = nil
    }
}
