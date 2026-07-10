import Foundation

/// The result of observing an incoming `seq`.
enum SeqObservation: Sendable, Equatable {
    /// The first observation, or exactly `lastSeq + 1`.
    case inOrder
    /// `seq` skipped ahead; the client must issue a `resume` from the last
    /// good seq (REQ-ARCH-005). `expected` is the seq that was missing.
    case gap(expected: Int64)
    /// `seq` is ≤ the last observed value (a replayed/duplicate frame).
    case duplicate
}

/// Pure, testable monotonic-sequence tracker for the globally-ordered event
/// stream (contract §3.1). The client tracks the highest `seq` seen and resumes
/// from it; a gap requests replay.
struct SeqTracker: Sendable, Equatable {
    private(set) var lastSeq: Int64?

    init(lastSeq: Int64? = nil) {
        self.lastSeq = lastSeq
    }

    /// Observes an incoming `seq`, returning whether it is in order, a gap, or a
    /// duplicate. Advances `lastSeq` only for in-order observations; on a gap the
    /// cursor is left at the last good seq so that a single
    /// `resume(after_seq: lastSeq)` redelivers the WHOLE missing range in order
    /// (each replayed frame then arrives in-order and advances the cursor one
    /// step at a time). Advancing past the gap here would make the replayed
    /// events look like duplicates and drop them (REQ-ARCH-005).
    mutating func observe(_ seq: Int64) -> SeqObservation {
        guard let last = lastSeq else {
            lastSeq = seq
            return .inOrder
        }
        if seq == last + 1 {
            lastSeq = seq
            return .inOrder
        }
        if seq <= last {
            return .duplicate
        }
        // seq > last + 1 → a gap. Do NOT advance; resume from `last` recovers
        // [last + 1, seq] in order.
        return .gap(expected: last + 1)
    }

    mutating func reset(to seq: Int64? = nil) {
        lastSeq = seq
    }
}
