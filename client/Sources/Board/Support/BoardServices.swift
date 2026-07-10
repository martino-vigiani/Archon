import Foundation

// ============================================================================
// Board sector — service seams (LEAD-owned contract).
//
// The Board stores depend on narrow, injectable protocols rather than the
// concrete `APIClient`, so the optimistic-concurrency / write-provenance logic
// is unit-testable with in-memory fakes (see client/Tests). The real transport
// (`APIClient`, ArchonCore) conforms via the extension at the bottom of this
// file — no ArchonCore edits required.
// ============================================================================

/// Kanban REST surface consumed by `BoardStore` (contract §2.5).
protocol KanbanService: Sendable {
    func kanbanSnapshot() async throws -> KanbanSnapshotResponse
    func createCard(_ request: CreateCardRequest) async throws -> CardResponse
    func patchCard(_ cardId: String, request: PatchCardRequest) async throws -> CardResponse
    func moveCard(_ cardId: String, request: MoveCardRequest) async throws -> MoveCardResponse
    func deleteCard(_ cardId: String, request: DeleteCardRequest) async throws -> DeleteCardResponse
}

/// Memory REST surface consumed by `MemoryStore` (contract §2.6). Every write
/// carries `initiator: .user` — the store hard-codes it (Addendum §A3).
protocol MemoryService: Sendable {
    func listMemory(scopeDir: String?) async throws -> MemoryListResponse
    func readMemory(scopeDir: String, filename: String) async throws -> MemoryReadResponse
    func writeMemory(_ request: MemoryWriteRequest) async throws -> MemoryWriteResponse
    func deleteMemory(scopeDir: String, filename: String, request: MemoryDeleteRequest) async throws -> MemoryDeleteResponse
}

// The concrete transport already implements these exact signatures.
extension APIClient: KanbanService, MemoryService {}
