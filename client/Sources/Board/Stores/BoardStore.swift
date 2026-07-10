import Foundation
import Observation

/// A subtle, non-modal board error surfaced inline (§4.10 / addendum §A4). Never
/// an alert — the board keeps its last-good state visible and reconciles calmly.
enum BoardError: Sendable, Equatable {
    case conflictReconciled     // 409 revision_conflict → refetched authoritative state
    case illegalMove            // 409 illegal_transition → move rejected, board unchanged
    case offline                // no live orchestrator; action is read-only
    case message(String)        // any other recoverable failure, plain language
}

/// The Board sector's kanban projection (@Observable @MainActor). Fed from
/// `WSClient.events()` (folding `kanban_updated`) plus authoritative REST
/// snapshots, with optimistic mutations reconciled against revision-checked
/// concurrency (contract §2.5 / REQ-BE-015).
///
/// This store is the *feature's own* projection: `AppState` keeps a separate
/// lightweight kanban cache for the shell — this one adds the optimistic layer,
/// conductor-change animation hints, and offline handling the board UI needs.
@MainActor
@Observable
final class BoardStore {

    // MARK: - Observable state

    private(set) var cards: [Card] = []
    private(set) var boardRevision: Int = 0
    private(set) var isLoaded: Bool = false
    private(set) var isOffline: Bool = false
    private(set) var lastError: BoardError?

    /// Cards whose most-recent change arrived from the stream *not* caused by a
    /// local optimistic op (i.e. the Conductor working the board). The UI plays
    /// a subtle spring on these so the user SEES the assistant act (§5.7).
    private(set) var animatingCardIds: Set<String> = []

    /// Cards with an in-flight local optimistic mutation — their echoed events
    /// must not re-animate.
    private(set) var pendingCardIds: Set<String> = []

    // MARK: - Dependencies

    private let service: @MainActor () -> (any KanbanService)?
    private let animationHold: Duration
    private let errorHold: Duration

    init(
        service: @escaping @MainActor () -> (any KanbanService)?,
        animationHold: Duration = .milliseconds(700),
        errorHold: Duration = .seconds(4)
    ) {
        self.service = service
        self.animationHold = animationHold
        self.errorHold = errorHold
    }

    // MARK: - Derived

    /// Cards in a column, ordered by ordinal (contract §2.5 `ordinal` = 0-based
    /// position within its column).
    func cards(in column: BoardColumn) -> [Card] {
        cards.filter { $0.column == column }.sorted { $0.ordinal < $1.ordinal }
    }

    var totalCount: Int { cards.count }

    // MARK: - Snapshots / connectivity

    func applySnapshot(_ snapshot: KanbanSnapshotResponse) {
        cards = snapshot.cards
        boardRevision = snapshot.boardRevision
        isLoaded = true
    }

    /// Fetches the authoritative snapshot (REQ-ARCH-026). Used on connect and to
    /// reconcile after a 409.
    func refresh() async {
        guard let service = service() else {
            isOffline = true
            return
        }
        do {
            let snapshot = try await service.kanbanSnapshot()
            applySnapshot(snapshot)
        } catch {
            // Keep last-good state visible (addendum §A4). Only note offline if
            // the orchestrator is unreachable.
            if isUnavailable(error) { isOffline = true }
        }
    }

    func setOffline(_ offline: Bool) {
        isOffline = offline
    }

    func clearError() { lastError = nil }

    // MARK: - Event folding (pure; unit-tested)

    /// Folds a decoded stream envelope. Only `kanban_updated` is relevant; every
    /// other type is ignored (kept total so the coordinator can pass all events).
    func apply(_ envelope: EventEnvelope) {
        guard case .kanbanUpdated(let payload) = envelope.event else { return }
        applyKanban(payload)
    }

    /// Folds one `kanban_updated` delta into the board, reconstructable from the
    /// event stream alone (REQ-BE-016). Marks remote (non-local) card changes for
    /// a subtle entrance animation.
    func applyKanban(_ payload: KanbanUpdatedPayload) {
        boardRevision = payload.boardRevision
        switch payload.op {
        case .snapshot:
            if let snapshotCards = payload.cards {
                cards = snapshotCards
                isLoaded = true
            }
        case .created, .updated, .moved:
            guard let card = payload.card else { return }
            upsert(card)
            markRemoteChangeIfNeeded(card.cardId)
        case .deleted:
            if let cardId = payload.cardId ?? payload.card?.cardId {
                cards.removeAll { $0.cardId == cardId }
                animatingCardIds.remove(cardId)
                pendingCardIds.remove(cardId)
            }
        case .unknown:
            break
        }
    }

    private func upsert(_ card: Card) {
        if let index = cards.firstIndex(where: { $0.cardId == card.cardId }) {
            cards[index] = card
        } else {
            cards.append(card)
        }
    }

    private func markRemoteChangeIfNeeded(_ cardId: String) {
        guard !pendingCardIds.contains(cardId) else { return }
        animatingCardIds.insert(cardId)
        Task { [weak self] in
            try? await Task.sleep(for: self?.animationHold ?? .milliseconds(700))
            self?.animatingCardIds.remove(cardId)
        }
    }

    func clearAnimation(for cardId: String) {
        animatingCardIds.remove(cardId)
    }

    // MARK: - Intents (optimistic + revision-checked reconcile)

    func createCard(
        title: String,
        body: String? = nil,
        column: BoardColumn = .queued,
        priority: CardPriority = .normal
    ) async {
        guard let service = service() else { noteOffline(); return }
        let request = CreateCardRequest(
            title: title, body: body, column: column, priority: priority, provenance: .user
        )
        do {
            let response = try await service.createCard(request)
            upsert(response.card)           // dedups with the echoed created event
        } catch {
            surface(error)
        }
    }

    func editCard(
        _ cardId: String,
        title: String? = nil,
        body: String? = nil,
        priority: CardPriority? = nil
    ) async {
        guard let index = cards.firstIndex(where: { $0.cardId == cardId }) else { return }
        guard let service = service() else { noteOffline(); return }

        let snapshot = cards
        var optimistic = cards[index]
        let baseRevision = optimistic.revision
        if let title { optimistic.title = title }
        if let body { optimistic.body = body }
        if let priority { optimistic.priority = priority }
        cards[index] = optimistic

        pendingCardIds.insert(cardId)
        defer { pendingCardIds.remove(cardId) }

        do {
            let response = try await service.patchCard(
                cardId,
                request: PatchCardRequest(
                    baseRevision: baseRevision,
                    title: title, body: body, priority: priority, provenance: .user
                )
            )
            upsert(response.card)
        } catch {
            await reconcileOrRollback(error, rollback: snapshot)
        }
    }

    /// Move across columns and/or reorder within a column (contract §2.5 move).
    /// Optimistically re-packs ordinals to match server semantics, then confirms
    /// with `base_revision`; a 409 refetches and reconciles calmly.
    func move(cardId: String, toColumn: BoardColumn, toOrdinal: Int) async {
        guard let card = cards.first(where: { $0.cardId == cardId }) else { return }
        guard let service = service() else { noteOffline(); return }

        let snapshot = cards
        let baseRevision = card.revision
        applyLocalMove(cardId: cardId, toColumn: toColumn, toOrdinal: toOrdinal)

        pendingCardIds.insert(cardId)
        defer { pendingCardIds.remove(cardId) }

        do {
            let response = try await service.moveCard(
                cardId,
                request: MoveCardRequest(
                    baseRevision: baseRevision,
                    toColumn: toColumn,
                    toOrdinal: toOrdinal,
                    provenance: .user
                )
            )
            boardRevision = response.boardRevision
            upsert(response.card)          // authoritative revision/ordinal
        } catch {
            await reconcileOrRollback(error, rollback: snapshot)
        }
    }

    func delete(cardId: String) async {
        guard let card = cards.first(where: { $0.cardId == cardId }) else { return }
        guard let service = service() else { noteOffline(); return }

        let snapshot = cards
        let baseRevision = card.revision
        cards.removeAll { $0.cardId == cardId }   // optimistic

        pendingCardIds.insert(cardId)
        defer { pendingCardIds.remove(cardId) }

        do {
            _ = try await service.deleteCard(
                cardId,
                request: DeleteCardRequest(baseRevision: baseRevision, provenance: .user)
            )
        } catch {
            await reconcileOrRollback(error, rollback: snapshot)
        }
    }

    // MARK: - Optimistic move mechanics

    /// Re-packs every column to contiguous 0-based ordinals with the moved card
    /// inserted at `toOrdinal` in `toColumn` (mirrors the server's contiguous
    /// re-pack, contract §2.5).
    func applyLocalMove(cardId: String, toColumn: BoardColumn, toOrdinal: Int) {
        guard var moving = cards.first(where: { $0.cardId == cardId }) else { return }
        let fromColumn = moving.column
        moving.column = toColumn

        var destination = cards
            .filter { $0.column == toColumn && $0.cardId != cardId }
            .sorted { $0.ordinal < $1.ordinal }
        let clamped = max(0, min(toOrdinal, destination.count))
        destination.insert(moving, at: clamped)

        var rebuilt: [Card] = []
        rebuilt.reserveCapacity(cards.count)
        for column in BoardColumn.allCases {
            let columnCards: [Card]
            if column == toColumn {
                columnCards = destination
            } else if column == fromColumn {
                columnCards = cards
                    .filter { $0.column == column && $0.cardId != cardId }
                    .sorted { $0.ordinal < $1.ordinal }
            } else {
                columnCards = cards
                    .filter { $0.column == column }
                    .sorted { $0.ordinal < $1.ordinal }
            }
            for (position, existing) in columnCards.enumerated() {
                var packed = existing
                packed.ordinal = position
                if packed.cardId == cardId { packed.column = toColumn }
                rebuilt.append(packed)
            }
        }
        cards = rebuilt
    }

    // MARK: - Error handling

    private func reconcileOrRollback(_ error: Error, rollback snapshot: [Card]) async {
        if let code = apiCode(error) {
            switch code {
            case .revisionConflict:
                await refresh()                 // authoritative reconcile (calm)
                lastError = .conflictReconciled
                scheduleErrorClear()
                return
            case .illegalTransition:
                cards = snapshot                // undo the illegal optimistic move
                lastError = .illegalMove
                scheduleErrorClear()
                return
            default:
                break
            }
        }
        cards = snapshot                        // any other failure → restore
        surface(error)
    }

    private func surface(_ error: Error) {
        if isUnavailable(error) {
            isOffline = true
            lastError = .offline
        } else if let code = apiCode(error), code == .revisionConflict {
            lastError = .conflictReconciled
        } else if let clientError = error as? ArchonClientError, case .api(let apiError, _) = clientError {
            lastError = .message(apiError.message)
        } else {
            lastError = .message("The board action could not be completed.")
        }
        scheduleErrorClear()
    }

    private func noteOffline() {
        isOffline = true
        lastError = .offline
        scheduleErrorClear()
    }

    private func scheduleErrorClear() {
        Task { [weak self] in
            try? await Task.sleep(for: self?.errorHold ?? .seconds(4))
            self?.lastError = nil
        }
    }

    private func apiCode(_ error: Error) -> APIErrorCode? {
        guard let clientError = error as? ArchonClientError,
              case .api(let apiError, _) = clientError else { return nil }
        return apiError.code
    }

    private func isUnavailable(_ error: Error) -> Bool {
        guard let clientError = error as? ArchonClientError else { return false }
        switch clientError {
        case .orchestratorUnavailable, .transport:
            return true
        default:
            return false
        }
    }
}
