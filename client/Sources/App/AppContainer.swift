import Foundation
import Observation

/// The dependency container and lifecycle coordinator (task item 2).
///
/// Owns the single instances of the stores/clients, wires the orchestrator
/// supervisor + WebSocket stream into `AppState`, and drives the project
/// open/close flow. The client NEVER holds the provider key — only the
/// per-session bearer token from the handshake (REQ-VIS-002).
@MainActor
@Observable
final class AppContainer {

    let projectStore: ProjectStore
    let supervisor: OrchestratorSupervisor
    let wsClient: WSClient
    let appState: AppState
    let registry: ShellRegistry

    /// The active REST client, valid once the orchestrator is healthy.
    private(set) var apiClient: APIClient?

    /// Recent projects for the launcher (Addendum §A2).
    private(set) var recentProjects: [RecentProject]

    private var supervisorTask: Task<Void, Never>?
    private var connectionTask: Task<Void, Never>?
    private var eventTask: Task<Void, Never>?
    private var didRegisterFeatures = false

    init() {
        let store = ProjectStore()
        self.projectStore = store
        self.supervisor = OrchestratorSupervisor(store: store)
        self.wsClient = WSClient()
        self.appState = AppState()
        self.registry = ShellRegistry()
        self.recentProjects = store.loadRecentProjects()
    }

    /// Starts the long-lived observers that mirror transport state into
    /// `AppState`. Idempotent.
    func bootstrap() {
        registerFeatures()
        observeSupervisor()
        observeConnection()
    }

    /// Plugs the phase-B feature modules into the shell registry (task item 2),
    /// replacing the neutral placeholder slots. Each feature owns its slots and
    /// starts its own store/coordinator (event pump + snapshot refresh) off the
    /// shared `WSClient`/`APIClient`; the WS event/state streams are multicast,
    /// so the independent per-feature subscribers coexist with the container's
    /// own `AppState` pump. Guarded so double `bootstrap()` never duplicates
    /// stores.
    ///
    /// Slot map after registration:
    ///   • `.sidebar`            → Terminals (session list / focus driver)
    ///   • `.main(.terminals)`   → Terminals grid + focus
    ///   • `.main(.summary)`     → Terminals summary dashboard
    ///   • `.main(.kanban)`      → Board kanban  (⌘4)
    ///   • `.main(.memory)`      → Board memory  (⌘5)
    ///   • `.main(.codebase)`    → Board codebase (⌘3)
    ///   • `.conductorEdge`      → Board kanban drawer (REQ-UX-001)
    ///   • `.orbOverlay`         → VoiceOrb floating orb + conductor surface
    ///   • `.conductorSurface`   → VoiceOrb conductor exchange
    private func registerFeatures() {
        guard !didRegisterFeatures else { return }
        didRegisterFeatures = true
        TerminalsFeature.register(into: registry, container: self)
        BoardFeature.register(into: registry, container: self)
        VoiceOrbFeature.register(into: registry, container: self)
    }

    // MARK: - Project lifecycle

    /// Opens ANY directory as the active project (Addendum §A2): supervises the
    /// orchestrator, fetches initial snapshots, and starts the event stream.
    func openProject(at url: URL) async {
        appState.currentProjectURL = url
        appState.resetRuntimeState()
        recentProjects = projectStore.recordOpenedProject(at: url)

        do {
            let handshake = try await supervisor.start(projectURL: url)
            let api = APIClient(
                baseURL: APIClient.baseURL(port: handshake.port),
                token: handshake.token
            )
            apiClient = api
            await refreshSnapshots(using: api)

            await wsClient.start(
                baseURL: WSClient.baseURL(port: handshake.port),
                token: handshake.token,
                resumeFrom: nil
            )
            startEventPump()
        } catch ArchonClientError.incompatibleVersion {
            appState.connectionState = .incompatible
        } catch {
            appState.lastError = APIError(
                code: .orchestratorError,
                message: "Could not start orchestrator: \(error.localizedDescription)",
                retriable: true,
                details: nil
            )
        }
    }

    func closeProject() async {
        eventTask?.cancel()
        eventTask = nil
        await wsClient.stop()
        await supervisor.stop()
        apiClient = nil
        appState.currentProjectURL = nil
        appState.projectInfo = nil
        appState.resetRuntimeState()
    }

    func removeRecent(_ project: RecentProject) {
        recentProjects = projectStore.removeRecentProject(projectId: project.projectId)
    }

    // MARK: - Snapshots (REQ-ARCH-026 / REQ-ARCH-008)

    private func refreshSnapshots(using api: APIClient) async {
        if let project = try? await api.project() {
            appState.projectInfo = project
        }
        if let sessions = try? await api.listSessions() {
            appState.applySessionsSnapshot(sessions)
        }
        if let kanban = try? await api.kanbanSnapshot() {
            appState.applyKanbanSnapshot(kanban)
        }
    }

    // MARK: - Observers

    private func observeSupervisor() {
        supervisorTask?.cancel()
        supervisorTask = Task { [weak self] in
            guard let self else { return }
            let stream = await self.supervisor.stateStream()
            for await state in stream {
                self.appState.supervisorState = state
            }
        }
    }

    private func observeConnection() {
        connectionTask?.cancel()
        connectionTask = Task { [weak self] in
            guard let self else { return }
            let stream = await self.wsClient.connectionStates()
            for await state in stream {
                self.appState.connectionState = state
                // On (re)connect, re-fetch authoritative snapshots (REQ-ARCH-008/026).
                if case .connected = state, let api = self.apiClient {
                    await self.refreshSnapshots(using: api)
                }
            }
        }
    }

    private func startEventPump() {
        eventTask?.cancel()
        eventTask = Task { [weak self] in
            guard let self else { return }
            let stream = await self.wsClient.events()
            for await envelope in stream {
                self.appState.apply(envelope)
            }
        }
    }
}
