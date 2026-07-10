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
    /// duplicate. Advances `lastSeq` for in-order and gap observations (so a
    /// single `resume` recovers the missing range), never regresses it.
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
        // seq > last + 1 → a gap. Advance so we resume from `last`.
        let expected = last + 1
        lastSeq = seq
        return .gap(expected: expected)
    }

    mutating func reset(to seq: Int64? = nil) {
        lastSeq = seq
    }
}
