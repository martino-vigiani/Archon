import Testing
import Foundation
@testable import Archon

@MainActor
@Suite("MemoryStore — user-initiated writes & proposals (§A3)")
struct MemoryStoreTests {

    private func makeService(writeRevision: Int = 5) -> MockMemoryService {
        MockMemoryService(
            listResponse: MemoryListResponse(scopes: []),
            writeResponse: MemoryWriteResponse(
                file: BoardFixtures.memoryFile(scopeDir: "/p", filename: "CLAUDE.md", revision: writeRevision)
            )
        )
    }

    @Test("Accepting a Conductor proposal writes with initiator:.user")
    func acceptProposalIsUserInitiated() async {
        let service = makeService()
        let store = MemoryStore(service: { service }, projectPath: { "/p" })
        let proposal = MemoryProposal(
            scopeDir: "/p",
            filename: "CLAUDE.md",
            baseRevision: 4,
            baseChecksum: "sha256:old",
            originalContent: "old guidance",
            proposedContent: "new guidance",
            rationale: "tidy up"
        )
        store.addProposal(proposal)

        await store.acceptProposal(proposal)

        let write = service.lastWriteRequest
        #expect(write?.initiator == .user)             // THE hard rule (§A3)
        #expect(write?.scopeDir == "/p")
        #expect(write?.filename == "CLAUDE.md")
        #expect(write?.content == "new guidance")
        #expect(write?.baseRevision == 4)
        #expect(write?.baseChecksum == "sha256:old")
        #expect(store.proposals.isEmpty)               // consumed on success
    }

    @Test("Explicit Save writes the editor buffer with initiator:.user")
    func saveIsUserInitiated() async {
        let service = makeService()
        service.readResponse = MemoryReadResponse(
            file: BoardFixtures.memoryFile(scopeDir: "/p", filename: "CLAUDE.md", revision: 7, checksum: "sha256:cur"),
            content: "hello"
        )
        let store = MemoryStore(service: { service })
        await store.select(BoardFixtures.memoryFile(scopeDir: "/p", filename: "CLAUDE.md"))
        #expect(store.editorText == "hello")

        store.editorText = "hello world"
        #expect(store.isDirty)

        await store.save()

        let write = service.lastWriteRequest
        #expect(write?.initiator == .user)
        #expect(write?.content == "hello world")
        #expect(write?.baseRevision == 7)
        #expect(write?.baseChecksum == "sha256:cur")
        #expect(store.isDirty == false)                // loaded == editor after save
    }

    @Test("Creating a file writes at base revision 0 with initiator:.user")
    func createFileIsUserInitiated() async {
        let service = makeService()
        let store = MemoryStore(service: { service })
        await store.createFile(scopeDir: "/p", filename: "NOTES.md")

        let write = service.lastWriteRequest
        #expect(write?.initiator == .user)
        #expect(write?.filename == "NOTES.md")
        #expect(write?.baseRevision == 0)
        #expect(write?.baseChecksum == "")
    }

    @Test("A stale save surfaces a calm conflict, no crash")
    func saveConflict() async {
        let service = makeService()
        service.readResponse = MemoryReadResponse(
            file: BoardFixtures.memoryFile(scopeDir: "/p", filename: "CLAUDE.md", revision: 7),
            content: "hello"
        )
        service.writeError = BoardFixtures.revisionConflict()
        let store = MemoryStore(service: { service })
        await store.select(BoardFixtures.memoryFile(scopeDir: "/p", filename: "CLAUDE.md"))
        store.editorText = "conflicting edit"

        await store.save()

        #expect(store.lastError == .conflict)
    }

    @Test("Rejecting a proposal discards it and never writes")
    func rejectProposal() {
        let service = makeService()
        let store = MemoryStore(service: { service })
        let proposal = MemoryProposal(
            scopeDir: "/p", filename: "CLAUDE.md", baseRevision: 1, baseChecksum: "x",
            originalContent: "a", proposedContent: "b"
        )
        store.addProposal(proposal)
        store.rejectProposal(proposal)

        #expect(store.proposals.isEmpty)
        #expect(service.lastWriteRequest == nil)       // nothing written on reject
    }

    @Test("A memory_changed event refreshes the listing (coalesced)")
    func memoryChangedRefreshes() async throws {
        let service = makeService()
        let store = MemoryStore(service: { service })
        let payload = MemoryChangedPayload(
            scopeDir: "/p", filename: "CLAUDE.md", kind: .claude,
            op: .updated, revision: 2, checksum: "x", initiator: .user
        )
        store.apply(EventEnvelope(seq: 1, type: "memory_changed", event: .memoryChanged(payload)))

        try await Task.sleep(for: .milliseconds(400))   // past the 300 ms debounce
        #expect(service.listCalls >= 1)
    }

    @Test("Offline save is a no-op that notes offline")
    func offlineSave() async {
        let store = MemoryStore(service: { nil })
        // select() with no service still sets the selection, then flags offline.
        await store.select(BoardFixtures.memoryFile(scopeDir: "/p", filename: "CLAUDE.md"))
        await store.save()
        #expect(store.isOffline)
        #expect(store.lastError == .offline)
    }
}
