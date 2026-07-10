import Foundation
import Observation

// ============================================================================
// Terminals · Store · TerminalsStore
//
// The @Observable @MainActor owner of the Terminals sector: consumes
// WSClient.events() (session lifecycle + pty_output + conductor log) and
// APIClient (snapshots + spawn/kill/flag), maintaining one TerminalSession per
// session_id. Drives the grid, summary dashboard, and sidebar.
//
// Resilience (Addendum §A4): reconnect/replay gaps never crash — on (re)connect
// the store re-fetches the authoritative snapshot (REQ-ARCH-008/026) and the UI
// shows the DesignSystem reconnect banner via connectionState. Everything
// already rendered stays readable while offline.
// ============================================================================

/// A compact spawn/termination event for the dashboard timeline (REQ-UX-022).
struct TerminalTimelineEvent: Identifiable, Sendable, Equatable {
    enum Kind: Sendable, Equatable { case spawned, ended }
    let id: String
    let sessionId: String
    let index: Int
    let kind: Kind
    let at: Date
}

/// Aggregate KPIs for the summary dashboard, refreshed ≤ 1 Hz (REQ-UX-021).
struct DashboardKPI: Sendable, Equatable {
    var activeCount: Int = 0
    var totalSpawned: Int = 0
    var statusCounts: [SessionStatus: Int] = [:]
    var elapsedRunSeconds: Int = 0
    /// Live aggregate token consumption is not carried by the frozen `pv=1`
    /// protocol (§3.4 has no token event); surfaced as "unavailable".
    var aggregateTokens: Int? = nil

    func count(_ status: SessionStatus) -> Int { statusCounts[status] ?? 0 }
}

@MainActor
@Observable
final class TerminalsStore {

    // MARK: - Dependencies

    @ObservationIgnored private unowned let container: AppContainer

    // MARK: - Sessions

    private(set) var sessionsById: [String: TerminalSession] = [:]

    /// Sessions in stable spawn order (by display index).
    var orderedSessions: [TerminalSession] {
        sessionsById.values.sorted { $0.index < $1.index }
    }

    var liveSessions: [TerminalSession] {
        orderedSessions.filter { !$0.isTerminal }
    }

    /// Sessions matching the active `statusFilter` (all when nil).
    func filteredSessions() -> [TerminalSession] {
        guard let filter = statusFilter else { return orderedSessions }
        return orderedSessions.filter { $0.status == filter }
    }

    // MARK: - Selection / focus / filter

    var selectedSessionId: String?
    /// Non-nil = focus mode (one terminal expanded to the pane, REQ-UX-012).
    var focusedSessionId: String?
    /// Dashboard→terminals status filter (REQ-UX-024).
    var statusFilter: SessionStatus?

    // MARK: - Connection

    private(set) var connectionState: WSConnectionState = .idle

    var isReconnecting: Bool {
        if case .reconnecting = connectionState { return true }
        return false
    }

    var isOffline: Bool { container.appState.isOffline }

    // MARK: - Aggregates (dashboard)

    private(set) var kpi = DashboardKPI()
    private(set) var timeline: [TerminalTimelineEvent] = []
    var lastConductorDecision: String?
    var lastConductorAt: Date?

    /// 1 Hz clock used by elapsed timers + KPI refresh throttle.
    private(set) var now = Date()

    @ObservationIgnored private var seenSessionIds: Set<String> = []
    @ObservationIgnored private var runStartedAt: Date?
    @ObservationIgnored private var nextIndex = 1

    // MARK: - Tasks / coalescing

    @ObservationIgnored private var started = false
    @ObservationIgnored private var eventTask: Task<Void, Never>?
    @ObservationIgnored private var connectionTask: Task<Void, Never>?
    @ObservationIgnored private var clockTask: Task<Void, Never>?
    @ObservationIgnored private var coalescer: FrameCoalescer?

    // MARK: - Init

    init(container: AppContainer) {
        self.container = container
    }

    // MARK: - Project

    var projectDir: String? {
        container.appState.projectInfo?.path ?? container.appState.currentProjectURL?.path
    }

    /// Whether a manual "New session" spawn is currently possible.
    var canSpawn: Bool {
        container.apiClient != nil && projectDir != nil && !container.appState.isOffline
    }

    // MARK: - Lifecycle

    /// Begins observers, the 1 Hz clock, and an initial snapshot fetch.
    /// Idempotent — safe to call once at feature registration.
    func start() {
        guard !started else { return }
        started = true

        coalescer = FrameCoalescer { [weak self] in
            guard let self else { return }
            for session in self.sessionsById.values { session.flushRender() }
        }

        connectionState = container.appState.connectionState
        observeConnection()
        observeEvents()
        startClock()

        if let api = container.apiClient {
            Task { [weak self] in await self?.refreshSnapshot(using: api) }
        }
    }

    func stop() {
        eventTask?.cancel(); eventTask = nil
        connectionTask?.cancel(); connectionTask = nil
        clockTask?.cancel(); clockTask = nil
        started = false
    }

    // MARK: - Observers

    private func observeEvents() {
        eventTask?.cancel()
        eventTask = Task { [weak self] in
            guard let self else { return }
            let stream = await self.container.wsClient.events()
            for await envelope in stream {
                self.apply(envelope)
            }
        }
    }

    private func observeConnection() {
        connectionTask?.cancel()
        connectionTask = Task { [weak self] in
            guard let self else { return }
            let stream = await self.container.wsClient.connectionStates()
            for await state in stream {
                self.connectionState = state
                if case .connected = state, let api = self.container.apiClient {
                    await self.refreshSnapshot(using: api)
                }
            }
        }
    }

    private func startClock() {
        clockTask?.cancel()
        clockTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(1))
                guard let self else { return }
                self.now = Date()
                self.recomputeKPI()
            }
        }
    }

    // MARK: - Snapshot reconciliation (authoritative, REQ-ARCH-026)

    private func refreshSnapshot(using api: APIClient) async {
        guard let snapshot = try? await api.listSessions() else { return }
        applySessionsSnapshot(snapshot.sessions)
    }

    /// Reconciles the authoritative session list: updates metadata for known
    /// sessions and creates panes for new ones, preserving existing scrollback.
    /// Terminated sessions absent from the snapshot are retained locally so
    /// their transcript stays readable.
    func applySessionsSnapshot(_ sessions: [Session]) {
        if sessions.isEmpty && sessionsById.isEmpty {
            resetRun()
        }
        for session in sessions {
            if let existing = sessionsById[session.sessionId] {
                existing.replaceMeta(session)
            } else {
                register(session)
            }
        }
        recomputeKPI()
    }

    // MARK: - Event reducer (pure projection over the stream)

    func apply(_ envelope: EventEnvelope) {
        switch envelope.event {
        case .sessionSpawned(let payload):
            reduceSpawned(payload.session)

        case .sessionState(let payload):
            guard let id = envelope.sessionId, let session = sessionsById[id] else { return }
            let wasTerminal = session.isTerminal
            session.applyStatePayload(payload)
            if !wasTerminal, session.isTerminal {
                appendTimeline(session, kind: .ended, at: envelope.ts)
            }
            recomputeKPI()

        case .ptyOutput(let payload):
            guard let id = envelope.sessionId, let session = sessionsById[id] else { return }
            session.ingest(payload)
            coalescer?.schedule()

        case .conductorState(let payload):
            if let detail = payload.detail, !detail.isEmpty {
                lastConductorDecision = detail
                lastConductorAt = envelope.ts
            }

        case .hello, .heartbeat, .kanbanUpdated, .memoryChanged, .dryRunResult, .error, .unknown:
            break
        }
    }

    private func reduceSpawned(_ session: Session) {
        if let existing = sessionsById[session.sessionId] {
            existing.replaceMeta(session)
        } else {
            let created = register(session)
            appendTimeline(created, kind: .spawned, at: session.createdAt)
        }
        recomputeKPI()
    }

    @discardableResult
    private func register(_ session: Session) -> TerminalSession {
        let terminal = TerminalSession(meta: session, index: nextIndex)
        nextIndex += 1
        sessionsById[session.sessionId] = terminal
        seenSessionIds.insert(session.sessionId)
        if runStartedAt == nil || session.createdAt < runStartedAt! {
            runStartedAt = session.createdAt
        }
        if selectedSessionId == nil { selectedSessionId = session.sessionId }
        return terminal
    }

    private func appendTimeline(_ session: TerminalSession, kind: TerminalTimelineEvent.Kind, at: Date) {
        let event = TerminalTimelineEvent(
            id: "\(session.id)-\(kind == .spawned ? "s" : "e")",
            sessionId: session.id, index: session.index, kind: kind, at: at
        )
        timeline.append(event)
        if timeline.count > 200 { timeline.removeFirst(timeline.count - 200) }
    }

    private func recomputeKPI() {
        var counts: [SessionStatus: Int] = [:]
        for session in sessionsById.values {
            counts[session.status, default: 0] += 1
        }
        let elapsed = runStartedAt.map { Swift.max(0, Int(now.timeIntervalSince($0))) } ?? 0
        kpi = DashboardKPI(
            activeCount: liveSessions.count,
            totalSpawned: seenSessionIds.count,
            statusCounts: counts,
            elapsedRunSeconds: elapsed,
            aggregateTokens: nil
        )
    }

    private func resetRun() {
        seenSessionIds.removeAll()
        runStartedAt = nil
        timeline.removeAll()
        nextIndex = 1
    }

    // MARK: - Actions (routed through APIClient with initiator: .user)

    func spawnSession(prompt: String) async {
        guard let api = container.apiClient, let cwd = projectDir else { return }
        let trimmed = prompt.trimmingCharacters(in: .whitespacesAndNewlines)
        let request = SpawnSessionRequest(
            cwd: cwd,
            initiator: .user,
            prompt: trimmed.isEmpty ? nil : trimmed
        )
        do {
            _ = try await api.spawnSession(request)
            // The pane appears via the subsequent `session_spawned` event.
        } catch let error as ArchonClientError {
            surface(error)
        } catch {
            container.appState.lastError = APIError(code: .orchestratorError, message: error.localizedDescription, retriable: false, details: nil)
        }
    }

    func kill(_ sessionId: String) async {
        guard let api = container.apiClient else { return }
        do {
            _ = try await api.killSession(sessionId)
        } catch let error as ArchonClientError {
            surface(error)
        } catch { }
    }

    func stopAll() async {
        guard container.apiClient != nil else { return }
        let ids = liveSessions.map(\.id)
        await withTaskGroup(of: Void.self) { group in
            for id in ids {
                group.addTask { [weak self] in await self?.kill(id) }
            }
        }
    }

    func setFlagIdle(_ sessionId: String, flagged: Bool) async {
        guard let api = container.apiClient else { return }
        do {
            let response = try await api.flagIdle(sessionId, request: FlagIdleRequest(flagged: flagged))
            sessionsById[sessionId]?.setIdleFlagged(response.idleFlagged)
        } catch { }
    }

    private func surface(_ error: ArchonClientError) {
        switch error {
        case .api(let apiError, _):
            container.appState.lastError = apiError
        case .incompatibleVersion:
            container.appState.lastError = APIError(code: .incompatibleVersion, message: "Incompatible orchestrator version.", retriable: false, details: nil)
        case .orchestratorUnavailable:
            container.appState.lastError = APIError(code: .orchestratorError, message: "The orchestrator is not reachable.", retriable: true, details: nil)
        case .transport(let message), .decoding(let message):
            container.appState.lastError = APIError(code: .orchestratorError, message: message, retriable: false, details: nil)
        }
    }

    // MARK: - Navigation

    /// Selects a session and surfaces the Terminals pane (sidebar-driven focus).
    func select(_ sessionId: String?) {
        selectedSessionId = sessionId
        if sessionId != nil {
            container.appState.selectedPane = .terminals
        }
    }

    /// Enters (non-nil) or exits (nil) focus mode for a session.
    func focus(_ sessionId: String?) {
        focusedSessionId = sessionId
        if let sessionId { selectedSessionId = sessionId }
    }

    /// Navigates to Terminals filtered by a status (dashboard tile tap).
    func showTerminals(filteredBy status: SessionStatus?) {
        statusFilter = status
        focusedSessionId = nil
        container.appState.selectedPane = .terminals
    }

    func clearFilter() {
        statusFilter = nil
    }
}
