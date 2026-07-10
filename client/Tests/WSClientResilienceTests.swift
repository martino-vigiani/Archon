import Testing
import Foundation
@testable import Archon

/// Transport-resilience behaviour that is pure enough to unit-test without a
/// live orchestrator: the crash-restart cursor reset (finding: crash-restart
/// recovery broken end-to-end).
@Suite("WSClient resilience")
struct WSClientResilienceTests {

    /// A closed loopback port: `start`/`reconfigure` spin up the connect loop but
    /// it never succeeds, so we only observe the synchronous cursor state.
    private func closedURL(_ port: Int) -> URL { URL(string: "ws://127.0.0.1:\(port)")! }

    @Test("reconfigure drops the stale resume cursor for a restarted orchestrator")
    func reconfigureResetsCursor() async {
        let ws = WSClient()
        // Wired against instance A with a live cursor.
        await ws.start(baseURL: closedURL(9), token: "token-a", resumeFrom: 4820)
        #expect(await ws.lastSeq == 4820)

        // Instance A dies; the supervisor relaunches on a new port with a new
        // token and a FRESH event bus (seq resets to 0). Reusing the old cursor
        // would mark every new event as a duplicate — the bug that left the app
        // stuck reconnecting. reconfigure must clear it.
        await ws.reconfigure(baseURL: closedURL(10), token: "token-b")
        #expect(await ws.lastSeq == nil)

        await ws.stop()
    }

    @Test("start ignores the resume cursor when re-pointed while already active")
    func startKeepsCursorAcrossRepoint() async {
        let ws = WSClient()
        await ws.start(baseURL: closedURL(11), token: "t", resumeFrom: 100)
        #expect(await ws.lastSeq == 100)
        // A plain re-point (same instance) keeps the cursor so a resume recovers.
        await ws.start(baseURL: closedURL(12), token: "t", resumeFrom: nil)
        #expect(await ws.lastSeq == 100)
        await ws.stop()
    }
}
