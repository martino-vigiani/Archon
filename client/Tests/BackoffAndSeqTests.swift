import Testing
import Foundation
@testable import Archon

@Suite("Backoff policy")
struct BackoffTests {

    @Test("attempt 0 is the initial delay (capped)")
    func initialDelay() {
        let policy = BackoffPolicy(initialSeconds: 0.5, maxSeconds: 15, multiplier: 2, jitterFraction: 0)
        #expect(policy.baseDelaySeconds(forAttempt: 0) == 0.5)
    }

    @Test("exponential growth")
    func growth() {
        let policy = BackoffPolicy(initialSeconds: 0.5, maxSeconds: 100, multiplier: 2, jitterFraction: 0)
        #expect(policy.baseDelaySeconds(forAttempt: 1) == 1.0)
        #expect(policy.baseDelaySeconds(forAttempt: 2) == 2.0)
        #expect(policy.baseDelaySeconds(forAttempt: 3) == 4.0)
    }

    @Test("caps at maxSeconds (REQ-ARCH-007 ≤ 15 s)")
    func capped() {
        let policy = BackoffPolicy.reconnect
        #expect(policy.baseDelaySeconds(forAttempt: 20) <= 15)
        #expect(policy.baseDelaySeconds(forAttempt: 0) <= 0.5)
    }

    @Test("jitter: random 0.5 yields the base delay")
    func jitterMidpoint() {
        let policy = BackoffPolicy(initialSeconds: 1, maxSeconds: 100, multiplier: 2, jitterFraction: 0.5)
        #expect(policy.delaySeconds(forAttempt: 2, random: 0.5) == 4.0)
    }

    @Test("jitter bounds: random 0 → base*(1-j), random 1 → base*(1+j)")
    func jitterBounds() {
        let policy = BackoffPolicy(initialSeconds: 1, maxSeconds: 100, multiplier: 2, jitterFraction: 0.4)
        let base = policy.baseDelaySeconds(forAttempt: 3)   // 8
        #expect(abs(policy.delaySeconds(forAttempt: 3, random: 0) - base * 0.6) < 1e-9)
        #expect(abs(policy.delaySeconds(forAttempt: 3, random: 1) - base * 1.4) < 1e-9)
    }

    @Test("reconnect policy starts ≤ 500 ms")
    func reconnectStart() {
        #expect(BackoffPolicy.reconnect.initialSeconds <= 0.5)
        #expect(BackoffPolicy.reconnect.maxSeconds <= 15)
    }
}

@Suite("Seq tracker gap detection")
struct SeqTrackerTests {

    @Test("first observation is in order and seeds lastSeq")
    func firstInOrder() {
        var tracker = SeqTracker()
        #expect(tracker.observe(10) == .inOrder)
        #expect(tracker.lastSeq == 10)
    }

    @Test("consecutive seqs are in order")
    func consecutive() {
        var tracker = SeqTracker(lastSeq: 10)
        #expect(tracker.observe(11) == .inOrder)
        #expect(tracker.observe(12) == .inOrder)
        #expect(tracker.lastSeq == 12)
    }

    @Test("a skip is a gap reporting the missing seq WITHOUT advancing the cursor")
    func gap() {
        var tracker = SeqTracker(lastSeq: 10)
        #expect(tracker.observe(13) == .gap(expected: 11))
        // Must NOT advance: resume(after_seq: lastSeq) has to re-request the whole
        // [11, 13] range. Advancing to 13 would make the replay look duplicate.
        #expect(tracker.lastSeq == 10)
    }

    @Test("resume after a gap redelivers the missing range in order")
    func gapThenResumeRecovers() {
        var tracker = SeqTracker(lastSeq: 10)
        // Live frame 13 skips ahead → gap; cursor stays at 10, resume from 10.
        #expect(tracker.observe(13) == .gap(expected: 11))
        #expect(tracker.lastSeq == 10)
        // Server replays 11, 12, 13 in order — each is now in-order and delivered
        // exactly once, advancing the cursor one step at a time.
        #expect(tracker.observe(11) == .inOrder)
        #expect(tracker.observe(12) == .inOrder)
        #expect(tracker.observe(13) == .inOrder)
        #expect(tracker.lastSeq == 13)
        // Live resumes cleanly.
        #expect(tracker.observe(14) == .inOrder)
    }

    @Test("a replayed/duplicate seq is dropped, lastSeq unchanged")
    func duplicate() {
        var tracker = SeqTracker(lastSeq: 10)
        #expect(tracker.observe(9) == .duplicate)
        #expect(tracker.observe(10) == .duplicate)
        #expect(tracker.lastSeq == 10)
    }
}
