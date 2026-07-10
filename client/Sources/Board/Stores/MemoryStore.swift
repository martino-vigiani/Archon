import Foundation
import Observation

/// A subtle, non-modal memory error surfaced inline (§4.10).
enum MemoryError: Sendable, Equatable {
    case conflict          // 409 revision_conflict — refetched; user re-applies
    case conductorForbidden // 403 conductor_write_forbidden — never happens from here
    case writeDenied       // 403 memory_write_denied
    case tooLarge          // 413 memory_too_large
    case quota             // 409 memory_quota_exceeded
    case pathEscape        // 400 path_escape
    case offline
    case message(String)
}

/// The Memory sector's store (@Observable @MainActor): lists discovered
/// `CLAUDE.md`/`AGENTS.md` + overlay files (contract §2.6), reads one into an
/// editor, and writes it back — but ONLY on an explicit user action, ALWAYS with
/// `initiator: .user` (addendum §A3). Conductor proposals are reviewed and, on
/// Accept, become user-initiated writes; the store NEVER auto-writes.
@MainActor
@Observable
final class MemoryStore {

    // MARK: - Observable state

    private(set) var scopes: [MemoryScope] = []
    private(set) var selectedFile: MemoryFile?
    var editorText: String = ""
    private(set) var loadedContent: String = ""
    private(set) var isLoaded: Bool = false
    private(set) var isSaving: Bool = false
    private(set) var proposals: [MemoryProposal] = []
    private(set) var lastError: MemoryError?
    private(set) var lastSavedAt: Date?
    var isOffline: Bool = false

    var isDirty: Bool { selectedFile != nil && editorText != loadedContent }

    // MARK: - Dependencies

    private let service: @MainActor () -> (any MemoryService)?
    private let projectPath: @MainActor () -> String?
    private var refreshDebounce: Task<Void, Never>?

    init(
        service: @escaping @MainActor () -> (any MemoryService)?,
        projectPath: @escaping @MainActor () -> String? = { nil }
    ) {
        self.service = service
        self.projectPath = projectPath
    }

    // MARK: - Derived

    var allFiles: [MemoryFile] { scopes.flatMap(\.files) }

    func proposals(for file: MemoryFile) -> [MemoryProposal] {
        proposals.filter { $0.fileKey == file.id }
    }

    var defaultScopeDir: String? { projectPath() ?? scopes.first?.scopeDir }

    // MARK: - Listing

    func applyMemoryList(_ list: MemoryListResponse) {
        scopes = list.scopes
        isLoaded = true
    }

    func refresh() async {
        guard let service = service() else { isOffline = true; return }
        do {
            let list = try await service.listMemory(scopeDir: nil)
            applyMemoryList(list)
        } catch {
            if isUnavailable(error) { isOffline = true }
        }
    }

    // MARK: - Read one file

    func select(_ file: MemoryFile) async {
        selectedFile = file
        guard let service = service() else {
            isOffline = true
            loadedContent = ""
            editorText = ""
            return
        }
        do {
            let response = try await service.readMemory(scopeDir: file.scopeDir, filename: file.filename)
            selectedFile = response.file
            loadedContent = response.content
            editorText = response.content
            lastError = nil
        } catch {
            surface(error)
        }
    }

    func revertEdits() {
        editorText = loadedContent
    }

    // MARK: - Write (EXPLICIT user action only, §A3)

    /// Saves the current editor buffer. Explicit user action → `initiator:.user`.
    func save() async {
        guard let file = selectedFile else { return }
        await performWrite(
            scopeDir: file.scopeDir,
            filename: file.filename,
            content: editorText,
            baseRevision: file.revision,
            baseChecksum: file.checksum,
            onSuccess: { [weak self] written in
                guard let self else { return }
                self.selectedFile = written
                self.loadedContent = self.editorText
                self.lastSavedAt = Date()
            }
        )
    }

    /// Creates a new memory file in `scopeDir` (explicit user action). New file →
    /// base revision 0 / empty checksum.
    func createFile(scopeDir: String, filename: String, content: String = "") async {
        await performWrite(
            scopeDir: scopeDir,
            filename: filename,
            content: content,
            baseRevision: 0,
            baseChecksum: "",
            onSuccess: { [weak self] written in
                guard let self else { return }
                await self.refresh()
                await self.select(written)
            }
        )
    }

    func deleteSelected() async {
        guard let file = selectedFile else { return }
        guard let service = service() else { noteOffline(); return }
        do {
            _ = try await service.deleteMemory(
                scopeDir: file.scopeDir,
                filename: file.filename,
                request: MemoryDeleteRequest(baseRevision: file.revision, initiator: .user)
            )
            selectedFile = nil
            loadedContent = ""
            editorText = ""
            await refresh()
        } catch {
            surface(error)
        }
    }

    // MARK: - Conductor proposals

    func addProposal(_ proposal: MemoryProposal) {
        guard !proposals.contains(where: { $0.id == proposal.id }) else { return }
        proposals.append(proposal)
    }

    /// Accept = a user-initiated write of the proposed content (§A3). The write
    /// ALWAYS carries `initiator:.user`; the proposal's conductor origin never
    /// reaches the write path.
    func acceptProposal(_ proposal: MemoryProposal) async {
        await performWrite(
            scopeDir: proposal.scopeDir,
            filename: proposal.filename,
            content: proposal.proposedContent,
            baseRevision: proposal.baseRevision,
            baseChecksum: proposal.baseChecksum,
            onSuccess: { [weak self] written in
                guard let self else { return }
                self.proposals.removeAll { $0.id == proposal.id }
                if self.selectedFile?.id == written.id {
                    self.selectedFile = written
                    self.loadedContent = proposal.proposedContent
                    self.editorText = proposal.proposedContent
                }
                await self.refresh()
            }
        )
    }

    func rejectProposal(_ proposal: MemoryProposal) {
        proposals.removeAll { $0.id == proposal.id }
    }

    // MARK: - Event folding

    func apply(_ envelope: EventEnvelope) {
        guard case .memoryChanged(let payload) = envelope.event else { return }
        applyMemoryChanged(payload)
    }

    /// Refreshes on an out-of-band or API change (REQ-ARCH-054), coalescing rapid
    /// changes. If the changed file is the current selection and the buffer is
    /// clean, reload its content.
    func applyMemoryChanged(_ payload: MemoryChangedPayload) {
        let changedKey = "\(payload.scopeDir)::\(payload.filename)"
        let selectedKey = selectedFile?.id
        refreshDebounce?.cancel()
        refreshDebounce = Task { [weak self] in
            try? await Task.sleep(for: .milliseconds(300))
            guard let self, !Task.isCancelled else { return }
            await self.refresh()
            if selectedKey == changedKey, let file = self.selectedFile, !self.isDirty {
                await self.select(file)
            }
        }
    }

    // MARK: - Centralised write path (single source of `initiator:.user`)

    private func performWrite(
        scopeDir: String,
        filename: String,
        content: String,
        baseRevision: Int,
        baseChecksum: String,
        onSuccess: @escaping @MainActor (MemoryFile) async -> Void
    ) async {
        guard let service = service() else { noteOffline(); return }
        isSaving = true
        defer { isSaving = false }
        let request = MemoryWriteRequest(
            scopeDir: scopeDir,
            filename: filename,
            content: content,
            baseRevision: baseRevision,
            baseChecksum: baseChecksum,
            initiator: .user            // HARD RULE (§A3): never anything else.
        )
        do {
            let response = try await service.writeMemory(request)
            lastError = nil
            await onSuccess(response.file)
        } catch {
            surface(error)
        }
    }

    // MARK: - Errors

    private func surface(_ error: Error) {
        if isUnavailable(error) {
            isOffline = true
            lastError = .offline
            return
        }
        guard let clientError = error as? ArchonClientError,
              case .api(let apiError, _) = clientError else {
            lastError = .message("The memory action could not be completed.")
            return
        }
        switch apiError.code {
        case .revisionConflict: lastError = .conflict
        case .conductorWriteForbidden: lastError = .conductorForbidden
        case .memoryWriteDenied: lastError = .writeDenied
        case .memoryTooLarge: lastError = .tooLarge
        case .memoryQuotaExceeded: lastError = .quota
        case .pathEscape: lastError = .pathEscape
        default: lastError = .message(apiError.message)
        }
        // On a stale write, pull the authoritative file back so the user can
        // re-apply against the fresh revision (REQ-ARCH-053).
        if apiError.code == .revisionConflict, let file = selectedFile {
            Task { [weak self] in await self?.reloadClean(file) }
        }
    }

    private func reloadClean(_ file: MemoryFile) async {
        guard let service = service() else { return }
        if let response = try? await service.readMemory(scopeDir: file.scopeDir, filename: file.filename) {
            selectedFile = response.file
            loadedContent = response.content
            // Preserve the user's in-progress edits; only refresh the base.
        }
    }

    func clearError() { lastError = nil }

    private func noteOffline() {
        isOffline = true
        lastError = .offline
    }

    private func isUnavailable(_ error: Error) -> Bool {
        guard let clientError = error as? ArchonClientError else { return false }
        switch clientError {
        case .orchestratorUnavailable, .transport: return true
        default: return false
        }
    }
}
