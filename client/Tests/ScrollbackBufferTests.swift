import Testing
import Foundation
@testable import Archon

@Suite("Scrollback ring buffer")
struct ScrollbackBufferTests {

    private func line(_ id: Int) -> TerminalLine {
        TerminalLine(id: id, runs: [TerminalRun(text: "line\(id)", style: .default)])
    }

    @Test("appends below capacity retain all lines in order")
    func retainsBelowCapacity() {
        var buffer = ScrollbackBuffer(capacity: 10)
        for i in 0..<5 { buffer.append(line(i)) }
        #expect(buffer.count == 5)
        #expect(buffer.line(at: 0)?.id == 0)
        #expect(buffer.line(at: 4)?.id == 4)
        #expect(buffer.totalAppended == 5)
    }

    @Test("evicts the oldest line once at capacity (FIFO)")
    func evictsOldest() {
        var buffer = ScrollbackBuffer(capacity: 3)
        for i in 0..<5 { buffer.append(line(i)) }   // 0,1 evicted
        #expect(buffer.count == 3)
        #expect(buffer.line(at: 0)?.id == 2)
        #expect(buffer.line(at: 1)?.id == 3)
        #expect(buffer.line(at: 2)?.id == 4)
        #expect(buffer.totalAppended == 5)
    }

    @Test("snapshot returns retained lines oldest→newest after wrap")
    func snapshotAfterWrap() {
        var buffer = ScrollbackBuffer(capacity: 3)
        for i in 0..<7 { buffer.append(line(i)) }   // retains 4,5,6
        let ids = buffer.snapshot().map(\.id)
        #expect(ids == [4, 5, 6])
    }

    @Test("out-of-range access returns nil, not a crash")
    func outOfRange() {
        var buffer = ScrollbackBuffer(capacity: 3)
        buffer.append(line(0))
        #expect(buffer.line(at: -1) == nil)
        #expect(buffer.line(at: 5) == nil)
    }

    @Test("lines(in:) clamps the range")
    func rangeClamped() {
        var buffer = ScrollbackBuffer(capacity: 5)
        for i in 0..<5 { buffer.append(line(i)) }
        #expect(buffer.lines(in: 2..<10).map(\.id) == [2, 3, 4])
        #expect(buffer.lines(in: -3..<2).map(\.id) == [0, 1])
    }

    @Test("respects the 10,000-line budget (REQ-PERF-022)")
    func tenThousandLineBudget() {
        var buffer = ScrollbackBuffer(capacity: 10_000)
        for i in 0..<12_000 { buffer.append(line(i)) }
        #expect(buffer.count == 10_000)
        #expect(buffer.line(at: 0)?.id == 2_000)          // first 2,000 evicted
        #expect(buffer.line(at: 9_999)?.id == 11_999)
        #expect(buffer.totalAppended == 12_000)
    }
}
