import Testing
import Foundation
@testable import Archon

@MainActor
@Suite("BoardStore — optimistic concurrency & event folding")
struct BoardStoreTests {

    private func makeStore(_ service: MockKanbanService) -> BoardStore {
        BoardStore(service: { service })
    }

    private func snapshot(_ cards: [Card], revision: Int = 1) -> KanbanSnapshotResponse {
        KanbanSnapshotResponse(columns: BoardColumn.allCases, cards: cards, boardRevision: revision)
    }

    // MARK: - Optimistic move → 409 reconcile

    @Test("A 409 revision_conflict refetches and reconciles calmly")
    func moveConflictReconciles() async {
        // Authoritative state the server returns on the reconcile refetch.
        let authoritative = snapshot(
            [BoardFixtures.card(id: "A", column: .queued, ordinal: 0, revision: 9)],
            revision: 99
        )
        let service = MockKanbanService(snapshot: authoritative)
        service.moveError = BoardFixtures.revisionConflict()

        let store = makeStore(service)
        store.applySnapshot(snapshot([
            BoardFixtures.card(id: "A", column: .queued, ordinal: 0, revision: 1),
            BoardFixtures.card(id: "B", column: .queued, ordinal: 1, revision: 1),
        ]))

        await store.move(cardId: "A", toColumn: .inProgress, toOrdinal: 0)

        // Reconciled to the authoritative snapshot, no thrown error, calm note.
        #expect(store.cards.count == 1)
        let a = store.cards.first { $0.cardId == "A" }
        #expect(a?.column == .queued)
        #expect(a?.revision == 9)
        #expect(store.boardRevision == 99)
        #expect(store.lastError == .conflictReconciled)
        #expect(service.snapshotCalls == 1)
        #expect(service.lastMoveRequest?.baseRevision == 1)
        #expect(service.lastMoveRequest?.provenance == .user)
    }

    @Test("A successful move applies the authoritative card + repacks ordinals")
    func moveSuccess() async {
        let service = MockKanbanService(snapshot: snapshot([]))
        service.moveResponse = MoveCardResponse(
            card: BoardFixtures.card(id: "A", column: .inProgress, ordinal: 0, revision: 2),
            boardRevision: 60
        )
        let store = makeStore(service)
        store.applySnapshot(snapshot([
            BoardFixtures.card(id: "A", column: .queued, ordinal: 0, revision: 1),
            BoardFixtures.card(id: "B", column: .queued, ordinal: 1, revision: 1),
        ]))

        await store.move(cardId: "A", toColumn: .inProgress, toOrdinal: 0)

        #expect(store.cards(in: .inProgress).map(\.cardId) == ["A"])
        #expect(store.cards(in: .inProgress).first?.revision == 2)
        #expect(store.cards(in: .queued).map(\.cardId) == ["B"])
        #expect(store.cards(in: .queued).first?.ordinal == 0)   // repacked contiguous
        #expect(store.boardRevision == 60)
        #expect(store.lastError == nil)
        #expect(service.lastMoveRequest?.toColumn == .inProgress)
        #expect(service.lastMoveRequest?.toOrdinal == 0)
    }

    @Test("An illegal_transition restores the board and notes the rejection")
    func moveIllegalTransition() async {
        let service = MockKanbanService(snapshot: snapshot([]))
        service.moveError = BoardFixtures.illegalTransition()
        let store = makeStore(service)
        let initial = [
            BoardFixtures.card(id: "A", column: .queued, ordinal: 0, revision: 1),
            BoardFixtures.card(id: "B", column: .queued, ordinal: 1, revision: 1),
        ]
        store.applySnapshot(snapshot(initial))

        await store.move(cardId: "A", toColumn: .done, toOrdinal: 0)

        // Rolled back to the pre-move state; no refetch needed.
        #expect(store.cards(in: .queued).map(\.cardId) == ["A", "B"])
        #expect(store.cards(in: .done).isEmpty)
        #expect(store.lastError == .illegalMove)
        #expect(service.snapshotCalls == 0)
    }

    // MARK: - Pure ordinal re-pack

    @Test("applyLocalMove reorders within a column with contiguous ordinals")
    func localReorder() {
        let store = makeStore(MockKanbanService(snapshot: snapshot([])))
        store.applySnapshot(snapshot([
            BoardFixtures.card(id: "A", column: .queued, ordinal: 0),
            BoardFixtures.card(id: "B", column: .queued, ordinal: 1),
            BoardFixtures.card(id: "C", column: .queued, ordinal: 2),
        ]))

        store.applyLocalMove(cardId: "C", toColumn: .queued, toOrdinal: 0)

        #expect(store.cards(in: .queued).map(\.cardId) == ["C", "A", "B"])
        #expect(store.cards(in: .queued).map(\.ordinal) == [0, 1, 2])
    }

    @Test("applyLocalMove across columns repacks both source and destination")
    func localCrossColumn() {
        let store = makeStore(MockKanbanService(snapshot: snapshot([])))
        store.applySnapshot(snapshot([
            BoardFixtures.card(id: "A", column: .queued, ordinal: 0),
            BoardFixtures.card(id: "B", column: .queued, ordinal: 1),
        ]))

        store.applyLocalMove(cardId: "A", toColumn: .inProgress, toOrdinal: 0)

        #expect(store.cards(in: .inProgress).map(\.cardId) == ["A"])
        #expect(store.cards(in: .inProgress).first?.ordinal == 0)
        #expect(store.cards(in: .queued).map(\.cardId) == ["B"])
        #expect(store.cards(in: .queued).first?.ordinal == 0)
    }

    // MARK: - Event folding

    @Test("Folding a created event inserts the card and animates it (remote change)")
    func foldCreated() {
        let store = makeStore(MockKanbanService(snapshot: snapshot([])))
        let card = BoardFixtures.card(id: "X", column: .inProgress, ordinal: 0, provenance: .conductor)

        store.apply(BoardFixtures.kanbanEvent(op: .created, card: card, boardRevision: 5))

        #expect(store.cards.map(\.cardId) == ["X"])
        #expect(store.boardRevision == 5)
        #expect(store.animatingCardIds.contains("X"))   // conductor working the board (§5.7)
    }

    @Test("Folding a moved event updates the card in place")
    func foldMoved() {
        let store = makeStore(MockKanbanService(snapshot: snapshot([])))
        store.applySnapshot(snapshot([BoardFixtures.card(id: "X", column: .queued, ordinal: 0, revision: 1)]))

        let moved = BoardFixtures.card(id: "X", column: .review, ordinal: 0, revision: 4)
        store.apply(BoardFixtures.kanbanEvent(op: .moved, card: moved, boardRevision: 12))

        #expect(store.cards(in: .review).map(\.cardId) == ["X"])
        #expect(store.cards.first { $0.cardId == "X" }?.revision == 4)
        #expect(store.boardRevision == 12)
    }

    @Test("Folding a deleted event removes the card")
    func foldDeleted() {
        let store = makeStore(MockKanbanService(snapshot: snapshot([])))
        store.applySnapshot(snapshot([BoardFixtures.card(id: "X", column: .queued, ordinal: 0)]))

        store.apply(BoardFixtures.kanbanEvent(op: .deleted, card: nil, boardRevision: 13, cardId: "X"))

        #expect(store.cards.isEmpty)
        #expect(store.boardRevision == 13)
        #expect(!store.animatingCardIds.contains("X"))
    }

    @Test("Folding a snapshot event replaces the board")
    func foldSnapshot() {
        let store = makeStore(MockKanbanService(snapshot: snapshot([])))
        let payload = KanbanUpdatedPayload(
            op: .snapshot,
            card: nil,
            cards: [BoardFixtures.card(id: "A"), BoardFixtures.card(id: "B")],
            cardId: nil, from: nil, to: nil, boardRevision: 40
        )
        store.apply(EventEnvelope(seq: 1, type: "kanban_updated", event: .kanbanUpdated(payload)))

        #expect(Set(store.cards.map(\.cardId)) == ["A", "B"])
        #expect(store.boardRevision == 40)
        #expect(store.isLoaded)
    }

    @Test("Non-kanban events are ignored by the board store")
    func ignoresOtherEvents() {
        let store = makeStore(MockKanbanService(snapshot: snapshot([])))
        store.applySnapshot(snapshot([BoardFixtures.card(id: "A")]))
        let heartbeat = EventEnvelope(seq: 1, type: "heartbeat", event: .heartbeat(HeartbeatPayload(currentSeq: 1, pong: nil)))
        store.apply(heartbeat)
        #expect(store.cards.map(\.cardId) == ["A"])
    }

    // MARK: - Offline

    @Test("A mutation with no service is a no-op that flags offline")
    func offlineMutation() async {
        let store = BoardStore(service: { nil })
        store.applySnapshot(snapshot([BoardFixtures.card(id: "A", column: .queued, ordinal: 0)]))
        await store.move(cardId: "A", toColumn: .review, toOrdinal: 0)
        #expect(store.isOffline)
        #expect(store.lastError == .offline)
        #expect(store.cards(in: .queued).map(\.cardId) == ["A"])   // unchanged, stale-visible
    }
}
