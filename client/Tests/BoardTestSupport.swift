import Foundation
@testable import Archon

// ============================================================================
// Board sector test doubles + factories.
// ============================================================================

/// Configurable in-memory `KanbanService`. `@MainActor` (hence Sendable) so it
/// can witness the sector's async service protocol from tests.
@MainActor
final class MockKanbanService: KanbanService {
    var snapshot: KanbanSnapshotResponse
    var moveError: Error?
    var moveResponse: MoveCardResponse?
    var createResponse: CardResponse?
    var patchError: Error?
    var patchResponse: CardResponse?
    var deleteError: Error?

    private(set) var lastMoveRequest: MoveCardRequest?
    private(set) var lastCreateRequest: CreateCardRequest?
    private(set) var lastPatchRequest: PatchCardRequest?
    private(set) var snapshotCalls = 0

    init(snapshot: KanbanSnapshotResponse) {
        self.snapshot = snapshot
    }

    func kanbanSnapshot() async throws -> KanbanSnapshotResponse {
        snapshotCalls += 1
        return snapshot
    }

    func createCard(_ request: CreateCardRequest) async throws -> CardResponse {
        lastCreateRequest = request
        if let createResponse { return createResponse }
        return CardResponse(card: BoardFixtures.card(
            id: "new", title: request.title, column: request.column, ordinal: 99, provenance: request.provenance
        ))
    }

    func patchCard(_ cardId: String, request: PatchCardRequest) async throws -> CardResponse {
        lastPatchRequest = request
        if let patchError { throw patchError }
        if let patchResponse { return patchResponse }
        return CardResponse(card: BoardFixtures.card(id: cardId, title: request.title ?? "?", column: .queued, ordinal: 0))
    }

    func moveCard(_ cardId: String, request: MoveCardRequest) async throws -> MoveCardResponse {
        lastMoveRequest = request
        if let moveError { throw moveError }
        if let moveResponse { return moveResponse }
        return MoveCardResponse(
            card: BoardFixtures.card(id: cardId, title: "moved", column: request.toColumn, ordinal: request.toOrdinal, revision: 2),
            boardRevision: snapshot.boardRevision + 1
        )
    }

    func deleteCard(_ cardId: String, request: DeleteCardRequest) async throws -> DeleteCardResponse {
        if let deleteError { throw deleteError }
        return DeleteCardResponse(cardId: cardId, deleted: true)
    }
}

/// Configurable in-memory `MemoryService` capturing the write request so tests
/// can assert `initiator == .user` (addendum §A3).
@MainActor
final class MockMemoryService: MemoryService {
    var listResponse: MemoryListResponse
    var readResponse: MemoryReadResponse?
    var writeResponse: MemoryWriteResponse
    var writeError: Error?

    private(set) var lastWriteRequest: MemoryWriteRequest?
    private(set) var listCalls = 0

    init(listResponse: MemoryListResponse, writeResponse: MemoryWriteResponse) {
        self.listResponse = listResponse
        self.writeResponse = writeResponse
    }

    func listMemory(scopeDir: String?) async throws -> MemoryListResponse {
        listCalls += 1
        return listResponse
    }

    func readMemory(scopeDir: String, filename: String) async throws -> MemoryReadResponse {
        if let readResponse { return readResponse }
        return MemoryReadResponse(file: BoardFixtures.memoryFile(scopeDir: scopeDir, filename: filename), content: "")
    }

    func writeMemory(_ request: MemoryWriteRequest) async throws -> MemoryWriteResponse {
        lastWriteRequest = request
        if let writeError { throw writeError }
        return writeResponse
    }

    func deleteMemory(scopeDir: String, filename: String, request: MemoryDeleteRequest) async throws -> MemoryDeleteResponse {
        MemoryDeleteResponse(deleted: true)
    }
}

enum BoardFixtures {
    static func card(
        id: String,
        title: String = "Card",
        column: BoardColumn = .queued,
        ordinal: Int = 0,
        priority: CardPriority = .normal,
        provenance: Initiator = .user,
        status: SessionStatus = .idle,
        revision: Int = 1,
        sessionId: String? = nil
    ) -> Card {
        Card(
            cardId: id,
            title: title,
            body: nil,
            column: column,
            ordinal: ordinal,
            priority: priority,
            provenance: provenance,
            sessionId: sessionId,
            status: status,
            revision: revision,
            createdAt: Date(timeIntervalSince1970: 1_700_000_000),
            updatedAt: Date(timeIntervalSince1970: 1_700_000_000)
        )
    }

    static func memoryFile(
        scopeDir: String,
        filename: String,
        revision: Int = 1,
        checksum: String = "sha256:abc"
    ) -> MemoryFile {
        MemoryFile(
            scopeDir: scopeDir,
            filename: filename,
            kind: .claude,
            location: .project,
            size: 0,
            mtime: Date(timeIntervalSince1970: 1_700_000_000),
            owner: .user,
            revision: revision,
            checksum: checksum,
            editable: true
        )
    }

    static func revisionConflict() -> ArchonClientError {
        .api(APIError(code: .revisionConflict, message: "stale", retriable: false, details: nil), httpStatus: 409)
    }

    static func illegalTransition() -> ArchonClientError {
        .api(APIError(code: .illegalTransition, message: "no", retriable: false, details: nil), httpStatus: 409)
    }

    /// A `kanban_updated` envelope for folding tests.
    static func kanbanEvent(op: KanbanOp, card: Card?, boardRevision: Int, cardId: String? = nil) -> EventEnvelope {
        let payload = KanbanUpdatedPayload(
            op: op, card: card, cards: nil, cardId: cardId, from: nil, to: nil, boardRevision: boardRevision
        )
        return EventEnvelope(seq: 1, type: "kanban_updated", taskId: card?.cardId ?? cardId, event: .kanbanUpdated(payload))
    }
}
