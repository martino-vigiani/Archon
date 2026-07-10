import Testing
import Foundation
@testable import Archon

@Suite("Terminals store state reduction")
@MainActor
struct TerminalsStoreTests {

    // Retained for the test's lifetime so the store's `unowned container` stays
    // valid (in production the container owns the registry that retains the store).
    private let container = AppContainer()

    private func makeStore() -> TerminalsStore {
        TerminalsStore(container: container)
    }

    private func session(
        _ id: String,
        state: SessionState = .running,
        status: SessionStatus = .running,
        cwd: String = "/proj/api"
    ) -> Session {
        Session(
            sessionId: id, state: state, status: status, provider: "claude_code",
            cwd: cwd, cardId: nil, initiator: .user, requestId: nil, pid: 10,
            createdAt: Date(), startedAt: Date(), endedAt: nil, exitCode: nil,
            exitReason: nil, idleFlagged: false, lastActivityAt: nil,
            lastOutputSeq: nil, elapsedS: nil
        )
    }

    private func spawn(_ seq: Int64, _ s: Session) -> EventEnvelope {
        EventEnvelope(seq: seq, type: "session_spawned", sessionId: s.sessionId,
                      event: .sessionSpawned(SessionSpawnedPayload(session: s)))
    }

    private func stateEvent(_ seq: Int64, _ id: String, _ state: SessionState, _ status: SessionStatus) -> EventEnvelope {
        EventEnvelope(seq: seq, type: "session_state", sessionId: id,
                      event: .sessionState(SessionStatePayload(
                        state: state, status: status, exitCode: state == .completed ? 0 : nil,
                        exitReason: state == .completed ? .normal : nil, idleFlagged: false,
                        lastActivityAt: Date(), elapsedS: 5, limit: nil)))
    }

    private func pty(_ seq: Int64, _ id: String, _ text: String, streamSeq: Int64, dropped: Bool = false, droppedBytes: Int = 0) -> EventEnvelope {
        let bytes = Data(text.utf8).base64EncodedString()
        return EventEnvelope(seq: seq, type: "pty_output", sessionId: id,
                             event: .ptyOutput(PTYOutputPayload(streamSeq: streamSeq, bytes: bytes, dropped: dropped, droppedBytes: droppedBytes)))
    }

    // MARK: - Session lifecycle

    @Test("session_spawned registers a session with a 1-based index and selects it")
    func spawnRegisters() {
        let store = makeStore()
        store.apply(spawn(1, session("s1")))
        #expect(store.orderedSessions.count == 1)
        #expect(store.sessionsById["s1"]?.index == 1)
        #expect(store.selectedSessionId == "s1")
        #expect(store.liveSessions.count == 1)
        #expect(store.kpi.activeCount == 1)
    }

    @Test("duplicate session_spawned does not create a second pane")
    func spawnIdempotent() {
        let store = makeStore()
        store.apply(spawn(1, session("s1")))
        store.apply(spawn(2, session("s1")))
        #expect(store.orderedSessions.count == 1)
        #expect(store.kpi.totalSpawned == 1)
    }

    @Test("session_state to a terminal state ends the session and logs the timeline")
    func terminalState() {
        let store = makeStore()
        store.apply(spawn(1, session("s1")))
        store.apply(stateEvent(2, "s1", .completed, .done))
        #expect(store.sessionsById["s1"]?.isTerminal == true)
        #expect(store.liveSessions.isEmpty)
        #expect(store.kpi.count(.done) == 1)
        #expect(store.timeline.contains { $0.kind == .ended && $0.sessionId == "s1" })
    }

    @Test("multiple spawns increment indices and total-spawned count")
    func multipleSpawns() {
        let store = makeStore()
        store.apply(spawn(1, session("s1")))
        store.apply(spawn(2, session("s2")))
        store.apply(spawn(3, session("s3")))
        #expect(store.kpi.totalSpawned == 3)
        #expect(store.sessionsById["s3"]?.index == 3)
        #expect(store.orderedSessions.map(\.id) == ["s1", "s2", "s3"])
    }

    // MARK: - PTY routing

    @Test("pty_output is decoded and fed to the target session's emulator")
    func ptyRouting() {
        let store = makeStore()
        store.apply(spawn(1, session("s1")))
        store.apply(pty(2, "s1", "hello\n", streamSeq: 1))
        let emulator = store.sessionsById["s1"]!.emulator
        #expect(emulator.scrollbackCount == 1)
        #expect(emulator.line(at: 0).plainText == "hello")
    }

    @Test("a dropped pty_output chunk inserts an output-trimmed marker")
    func ptyDropMarker() {
        let store = makeStore()
        store.apply(spawn(1, session("s1")))
        store.apply(pty(2, "s1", "resumed\n", streamSeq: 9, dropped: true, droppedBytes: 512))
        let emulator = store.sessionsById["s1"]!.emulator
        #expect(emulator.line(at: 0).isMarker == true)
        #expect(emulator.line(at: 1).plainText == "resumed")
    }

    @Test("pty_output for an unknown session is ignored (no crash)")
    func ptyUnknownSession() {
        let store = makeStore()
        store.apply(pty(1, "ghost", "x", streamSeq: 1))
        #expect(store.orderedSessions.isEmpty)
    }

    // MARK: - Snapshot reconciliation

    @Test("snapshot updates existing metadata and adds new sessions, preserving order")
    func snapshotReconcile() {
        let store = makeStore()
        store.apply(spawn(1, session("s1", status: .running)))
        store.applySessionsSnapshot([
            session("s1", state: .completed, status: .done),
            session("s2", status: .running),
        ])
        #expect(store.sessionsById["s1"]?.status == .done)
        #expect(store.sessionsById["s2"] != nil)
        #expect(store.kpi.totalSpawned == 2)
    }

    // MARK: - Retention pruning (unbounded-growth finding)

    @Test("terminated sessions are capped; live sessions and lifetime count are preserved")
    func prunesDeadSessions() {
        let store = makeStore()
        let cap = TerminalsStore.maxRetainedDeadSessions
        let deadCount = cap + 10
        for i in 0..<deadCount {
            store.apply(spawn(Int64(i + 1), session("dead-\(i)", state: .completed, status: .done)))
        }
        // One live session must never be evicted.
        store.apply(spawn(Int64(deadCount + 1), session("live-1", status: .running)))

        let retainedDead = store.orderedSessions.filter { $0.isTerminal }
        #expect(retainedDead.count == cap)
        #expect(store.sessionsById["live-1"] != nil)
        // The oldest dead sessions are the ones dropped; the most recent are kept.
        #expect(store.sessionsById["dead-0"] == nil)
        #expect(store.sessionsById["dead-\(deadCount - 1)"] != nil)
        // Lifetime spawn count is not pruned.
        #expect(store.kpi.totalSpawned == deadCount + 1)
    }

    // MARK: - Conductor log + navigation

    @Test("conductor_state detail updates the last-decision log")
    func conductorLog() {
        let store = makeStore()
        store.apply(EventEnvelope(seq: 1, type: "conductor_state",
            event: .conductorState(ConductorStatePayload(state: .thinking, detail: "Planning 2 terminals", planId: nil, intentId: nil))))
        #expect(store.lastConductorDecision == "Planning 2 terminals")
    }

    @Test("showTerminals sets the status filter and navigates to the Terminals pane")
    func filterNavigation() {
        let store = makeStore()
        store.apply(spawn(1, session("s1", status: .running)))
        store.apply(spawn(2, session("s2", state: .completed, status: .done)))
        store.showTerminals(filteredBy: .running)
        #expect(store.statusFilter == .running)
        #expect(store.filteredSessions().map(\.id) == ["s1"])
        store.clearFilter()
        #expect(store.filteredSessions().count == 2)
    }
}
