import Testing
import Foundation
@testable import Archon

@Suite("AppState event reducer")
@MainActor
struct AppStateReducerTests {

    private func makeSessionSpawned(seq: Int64, id: String, status: SessionStatus = .running) -> EventEnvelope {
        let session = Session(
            sessionId: id, state: .running, status: status, provider: "claude_code",
            cwd: "/p", cardId: nil, initiator: .user, requestId: nil, pid: 1,
            createdAt: Date(), startedAt: nil, endedAt: nil, exitCode: nil,
            exitReason: nil, idleFlagged: false, lastActivityAt: nil,
            lastOutputSeq: nil, elapsedS: nil
        )
        return EventEnvelope(seq: seq, type: "session_spawned", sessionId: id,
                             event: .sessionSpawned(SessionSpawnedPayload(session: session)))
    }

    @Test("session_spawned then session_state updates the session")
    func sessionLifecycle() {
        let state = AppState()
        state.apply(makeSessionSpawned(seq: 1, id: "s1"))
        #expect(state.sessionsById["s1"]?.state == .running)
        #expect(state.liveSessionCount == 1)

        let done = EventEnvelope(
            seq: 2, type: "session_state", sessionId: "s1",
            event: .sessionState(SessionStatePayload(
                state: .completed, status: .done, exitCode: 0, exitReason: .normal,
                idleFlagged: false, lastActivityAt: nil, elapsedS: 5, limit: nil))
        )
        state.apply(done)
        #expect(state.sessionsById["s1"]?.state == .completed)
        #expect(state.sessionsById["s1"]?.status == .done)
        #expect(state.liveSessionCount == 0)
    }

    @Test("kanban created / moved / deleted")
    func kanbanReducer() {
        let state = AppState()
        let card = Card(
            cardId: "c1", title: "t", body: nil, column: .queued, ordinal: 0,
            priority: .normal, provenance: .user, sessionId: nil, status: .idle,
            revision: 1, createdAt: Date(), updatedAt: Date()
        )
        let created = EventEnvelope(seq: 1, type: "kanban_updated", taskId: "c1",
            event: .kanbanUpdated(KanbanUpdatedPayload(op: .created, card: card, cards: nil, cardId: nil, from: nil, to: nil, boardRevision: 1)))
        state.apply(created)
        #expect(state.cards.count == 1)
        #expect(state.boardRevision == 1)

        var moved = card
        moved.column = .inProgress
        moved.revision = 2
        let moveEvent = EventEnvelope(seq: 2, type: "kanban_updated", taskId: "c1",
            event: .kanbanUpdated(KanbanUpdatedPayload(op: .moved, card: moved, cards: nil, cardId: nil, from: nil, to: nil, boardRevision: 2)))
        state.apply(moveEvent)
        #expect(state.cards.count == 1)
        #expect(state.cards(in: .inProgress).count == 1)
        #expect(state.cards(in: .queued).isEmpty)

        let deleted = EventEnvelope(seq: 3, type: "kanban_updated", taskId: "c1",
            event: .kanbanUpdated(KanbanUpdatedPayload(op: .deleted, card: nil, cards: nil, cardId: "c1", from: nil, to: nil, boardRevision: 3)))
        state.apply(deleted)
        #expect(state.cards.isEmpty)
        #expect(state.boardRevision == 3)
    }

    @Test("conductor_state drives the orb; server listening is ignored")
    func conductorStateReducer() {
        let state = AppState()
        state.apply(EventEnvelope(seq: 1, type: "conductor_state",
            event: .conductorState(ConductorStatePayload(state: .thinking, detail: nil, planId: nil, intentId: nil))))
        #expect(state.conductorState == .thinking)

        // A stray server `listening` must be ignored (client-local only).
        state.apply(EventEnvelope(seq: 2, type: "conductor_state",
            event: .conductorState(ConductorStatePayload(state: .listening, detail: nil, planId: nil, intentId: nil))))
        #expect(state.conductorState == .thinking)
    }

    @Test("setListening toggles the client-local orb state")
    func setListening() {
        let state = AppState()
        state.setListening(true)
        #expect(state.conductorState == .listening)
        state.setListening(false)
        #expect(state.conductorState == .idle)
    }

    @Test("snapshot application replaces runtime state (REQ-ARCH-026)")
    func snapshotApplication() {
        let state = AppState()
        state.apply(makeSessionSpawned(seq: 1, id: "old"))
        let snapshot = SessionsListResponse(sessions: [], count: 0, ceiling: 8, cap: CapInfo(regime: .auto, value: nil))
        state.applySessionsSnapshot(snapshot)
        #expect(state.sessionsById.isEmpty)
        #expect(state.hardCeiling == 8)
    }
}
