import Foundation

// ============================================================================
// Terminals · Model · ScrollbackBuffer
//
// A memory-bounded ring buffer of committed terminal lines (REQ-PERF-022):
// capped at 10,000 lines/session; the oldest line is evicted in O(1) with no
// allocation churn once warmed. Rendering is virtualized on top of this (the
// render layer only materialises attributed strings for the visible window,
// REQ-PERF-021) — this structure is the raw retained model.
// ============================================================================

/// Fixed-capacity FIFO ring of `TerminalLine`. Value type: cheap to snapshot,
/// safe to hold from a `@MainActor` owner.
struct ScrollbackBuffer: Sendable, Equatable {

    /// Maximum retained lines (default REQ-PERF-022 budget = 10,000).
    let capacity: Int

    private var storage: [TerminalLine] = []
    /// Index of the oldest element within `storage` once the ring is full.
    private var head: Int = 0
    /// Lifetime count of appended lines (including evicted) — never resets.
    private(set) var totalAppended: Int = 0

    init(capacity: Int = 10_000) {
        self.capacity = Swift.max(1, capacity)
        storage.reserveCapacity(Swift.min(self.capacity, 1024))
    }

    /// Number of currently-retained lines (≤ capacity).
    var count: Int { storage.count }

    var isEmpty: Bool { storage.isEmpty }

    /// Appends a line, evicting the oldest in O(1) when at capacity.
    mutating func append(_ line: TerminalLine) {
        totalAppended += 1
        if storage.count < capacity {
            storage.append(line)
        } else {
            // Overwrite the oldest slot and advance the ring head. O(1), no shift.
            storage[head] = line
            head = (head + 1) % capacity
        }
    }

    /// The line at retained index `0..<count` (0 = oldest retained). O(1).
    func line(at index: Int) -> TerminalLine? {
        let n = storage.count
        guard index >= 0, index < n else { return nil }
        // When not full, `head == 0`, so `real == index`. When full, `n ==
        // capacity` and the ring wraps from `head`.
        let real = (head + index) % n
        return storage[real]
    }

    /// The lines in the retained index range, clamped to `0..<count`, oldest→newest.
    func lines(in range: Range<Int>) -> [TerminalLine] {
        let lower = Swift.max(0, range.lowerBound)
        let upper = Swift.min(count, range.upperBound)
        guard lower < upper else { return [] }
        var out: [TerminalLine] = []
        out.reserveCapacity(upper - lower)
        for i in lower..<upper {
            if let l = line(at: i) { out.append(l) }
        }
        return out
    }

    /// A full ordered snapshot (oldest→newest). O(count).
    func snapshot() -> [TerminalLine] {
        lines(in: 0..<count)
    }

    /// Drops all retained lines (keeps capacity / lifetime counter).
    mutating func removeAll() {
        storage.removeAll(keepingCapacity: true)
        head = 0
    }
}
