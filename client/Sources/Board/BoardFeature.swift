import SwiftUI
import Observation

/// The Board sector's single public entry point. The integrator calls
/// `BoardFeature.register(into:container:)` once; it constructs the sector's
/// stores, starts the live event/connection pumps, and registers the three
/// main-pane views into the shell registry.
///
/// Owned slots: `.main(.kanban)`, `.main(.memory)`, `.main(.codebase)`. No edits
/// to `App/`, other feature dirs, or (beyond the additive MainPane cases)
/// ArchonCore.
enum BoardFeature {

    @MainActor
    static func register(into registry: ShellRegistry, container: AppContainer) {
        let coordinator = BoardCoordinator(container: container)
        // The coordinator's long-lived pump tasks strong-capture it, so it stays
        // alive for the app lifetime (see `BoardCoordinator.start`).
        coordinator.start()

        let board = coordinator.board
        let memory = coordinator.memory
        let codebase = coordinator.codebase

        registry.register(.main(.kanban)) { KanbanBoardView(store: board) }
        registry.register(.main(.memory)) { MemoryView(store: memory) }
        registry.register(.main(.codebase)) { CodebaseView(store: codebase) }

        // REQ-UX-001: the shell's right drawer ("conductor edge") houses the
        // Kanban board. Register the same board (shared store) there so the
        // drawer shows live content instead of a placeholder; ⌘4 additionally
        // surfaces it as a full main pane per the integration directive.
        registry.register(.conductorEdge) { KanbanBoardView(store: board) }
    }
}

/// Wires the sector stores to `WSClient.events()` + `APIClient` (via the shared
/// service seams) and mirrors connectivity into each store. Mirrors the
/// foundation's own connect→resnapshot pattern (REQ-ARCH-008/026); harmless
/// duplication — the WS event/state streams are multicast.
@MainActor
final class BoardCoordinator {

    let board: BoardStore
    let memory: MemoryStore
    let codebase: CodebaseStore

    private let container: AppContainer
    private var eventTask: Task<Void, Never>?
    private var connectionTask: Task<Void, Never>?

    init(container: AppContainer) {
        self.container = container
        self.board = BoardStore(service: { container.apiClient })
        self.memory = MemoryStore(
            service: { container.apiClient },
            projectPath: { container.appState.projectInfo?.path ?? container.appState.currentProjectURL?.path }
        )
        self.codebase = CodebaseStore(
            projectURL: container.appState.currentProjectURL,
            stateDirectory: Self.stateDirectory(for: container),
            appState: container.appState
        )
    }

    func start() {
        observeConnection()
        pumpEvents()
    }

    /// On every (re)connect: mark online, (re)bind the codebase to the current
    /// project, and fetch authoritative snapshots. On disconnect: mark offline
    /// but keep the last-good state visible (addendum §A4).
    private func observeConnection() {
        connectionTask?.cancel()
        connectionTask = Task { [self] in
            let stream = await container.wsClient.connectionStates()
            for await state in stream {
                let online = (state == .connected)
                board.setOffline(!online)
                memory.isOffline = !online
                if online {
                    codebase.configure(
                        projectURL: container.appState.currentProjectURL,
                        stateDirectory: Self.stateDirectory(for: container)
                    )
                    await board.refresh()
                    await memory.refresh()
                    await codebase.loadRoot()
                }
            }
        }
    }

    private func pumpEvents() {
        eventTask?.cancel()
        eventTask = Task { [self] in
            let stream = await container.wsClient.events()
            for await envelope in stream {
                board.apply(envelope)
                memory.apply(envelope)
            }
        }
    }

    private static func stateDirectory(for container: AppContainer) -> URL? {
        guard let url = container.appState.currentProjectURL else { return nil }
        return container.projectStore.stateDirectory(forProjectAt: url)
    }
}
