import Testing
import Foundation
@testable import Archon

@Suite("PTY stream_seq assembler")
struct PTYStreamAssemblerTests {

    @Test("the first chunk applies and seeds last stream_seq")
    func firstApplies() {
        var a = PTYStreamAssembler()
        #expect(a.classify(streamSeq: 1, dropped: false, droppedBytes: 0) == .apply)
        #expect(a.lastStreamSeq == 1)
    }

    @Test("consecutive stream_seq applies in order")
    func consecutiveApplies() {
        var a = PTYStreamAssembler(lastStreamSeq: 1)
        #expect(a.classify(streamSeq: 2, dropped: false, droppedBytes: 0) == .apply)
        #expect(a.classify(streamSeq: 3, dropped: false, droppedBytes: 0) == .apply)
        #expect(a.lastStreamSeq == 3)
    }

    @Test("a replayed/duplicate stream_seq is dropped and does not regress")
    func duplicateDropped() {
        var a = PTYStreamAssembler(lastStreamSeq: 5)
        #expect(a.classify(streamSeq: 5, dropped: false, droppedBytes: 0) == .duplicate)
        #expect(a.classify(streamSeq: 3, dropped: false, droppedBytes: 0) == .duplicate)
        #expect(a.lastStreamSeq == 5)
    }

    @Test("a stream_seq skip yields a gap marker reporting the missing seq")
    func gapMarker() {
        var a = PTYStreamAssembler(lastStreamSeq: 2)
        #expect(a.classify(streamSeq: 5, dropped: false, droppedBytes: 0) == .gapMarker(missing: 3))
        #expect(a.lastStreamSeq == 5)
    }

    @Test("server drop-with-marker yields a dropped marker carrying the byte count")
    func droppedMarker() {
        var a = PTYStreamAssembler(lastStreamSeq: 4)
        #expect(a.classify(streamSeq: 9, dropped: true, droppedBytes: 4096) == .droppedMarker(bytes: 4096))
        #expect(a.lastStreamSeq == 9)
    }

    @Test("an explicit drop takes precedence over gap detection")
    func dropBeatsGap() {
        var a = PTYStreamAssembler(lastStreamSeq: 2)
        // Jump AND dropped → the drop marker wins (continuity already reset).
        #expect(a.classify(streamSeq: 100, dropped: true, droppedBytes: 10) == .droppedMarker(bytes: 10))
        #expect(a.lastStreamSeq == 100)
    }

    @Test("reset clears continuity so the next chunk applies as first")
    func reset() {
        var a = PTYStreamAssembler(lastStreamSeq: 42)
        a.reset()
        #expect(a.lastStreamSeq == nil)
        #expect(a.classify(streamSeq: 7, dropped: false, droppedBytes: 0) == .apply)
    }
}
