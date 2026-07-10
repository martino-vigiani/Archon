import Foundation
import Observation

/// The observable root of client UI state (@Observable, @MainActor).
///
/// The orchestrator is the source of truth for live runtime state
/// (REQ-ARCH-060); this is a cache/projection plus local-only UI state. On
/// reconnect conflict, server snapshots replace local state.
@MainActor
@Observable
final class AppState {

    // MARK: - Project

    var currentProjectURL: URL?
    var projectInfo: ProjectInfo?

    // MARK: - Navigation / UI

    var selectedPane: MainPane = .terminals
    var sidebarWidth: Double = 240
    var conductorEdgeWidth: Double = 320
    var isConductorEdgeCollapsed: Bool = false

    // MARK: - Connection / supervision

    var supervisorState: SupervisorState = .idle
    var connectionState: WSConnectionState = .idle

    /// Whether the app should show the non-modal "reconnecting" banner
    /// (REQ-UX-092).
    var isReconnecting: Bool {
        if case .reconnecting = connectionState { return true }
        return false
    }

    /// Whether orchestrator-requiring actions must be disabled (REQ-ARCH-081).
    var isOffline: Bool {
        switch connectionState {
        case .connected: return false
        default:
            switch supervisorState {
            case .ready: return false
            default: return true
            }
        }
    }

    var isIncompatible: Bool {
        if case .incompatible = connectionState { return true }
        if case .incompatible = supervisorState { return true }
        return false
    }

    // MARK: - Orb / Conductor

    /// The single source of truth for orchestration status (REQ-UX-041). Six
    /// canonical states; `listening` is client-local (voice).
    var conductorState: ConductorState = .idle

    // MARK: - Runtime projections

    var sessionsById: [String: Session] = [:]
    var cards: [Card] = []
    var boardRevision: Int = 0
    var effectiveCap: CapInfo = CapInfo(regime: .auto, value: nil)
    var hardCeiling: Int = 8

    /// The most recent recoverable error surfaced for the Conductor log
    /// (REQ-UX-093). Unrecoverable process-exit errors are surfaced separately.
    var lastError: APIError?

    // MARK: - Derived collections

    var sessions: [Session] {
        sessionsById.values.sorted { $0.createdAt < $1.createdAt }
    }

    var liveSessionCount: Int {
        sessionsById.values.filter { !$0.state.isTerminal }.count
    }

    func cards(in column: BoardColumn) -> [Card] {
        cards.filter { $0.column == column }.sorted { $0.ordinal < $1.ordinal }
    }

    // MARK: - Local orb control

    /// Sets the client-local `listening` orb state (WhisperKit push-to-talk).
    /// The server never drives `listening` (contract §3.4).
    func setListening(_ listening: Bool) {
        if listening {
            conductorState = .listening
        } else if conductorState == .listening {
            conductorState = .idle
        }
    }

    // MARK: - Snapshot application (REQ-ARCH-026)

    func applySessionsSnapshot(_ snapshot: SessionsListResponse) {
        sessionsById = Dictionary(uniqueKeysWithValues: snapshot.sessions.map { ($0.sessionId, $0) })
        effectiveCap = snapshot.cap
        hardCeiling = snapshot.ceiling
    }

    func applyKanbanSnapshot(_ snapshot: KanbanSnapshotResponse) {
        cards = snapshot.cards
        boardRevision = snapshot.boardRevision
    }

    // MARK: - Event reducer

    /// Folds a decoded stream event into observable state. Deliberately total
    /// and side-effect-free so it is unit-testable and phase-B teams extend it
    /// in one place.
    func apply(_ envelope: EventEnvelope) {
        switch envelope.event {
        case .sessionSpawned(let payload):
            sessionsById[payload.session.sessionId] = payload.session

        case .sessionState(let payload):
            guard let sessionId = envelope.sessionId,
                  var session = sessionsById[sessionId] else { return }
            session.state = payload.state
            session.status = payload.status
            session.exitCode = payload.exitCode ?? session.exitCode
            session.exitReason = payload.exitReason ?? session.exitReason
            session.idleFlagged = payload.idleFlagged ?? session.idleFlagged
            session.lastActivityAt = payload.lastActivityAt ?? session.lastActivityAt
            session.elapsedS = payload.elapsedS ?? session.elapsedS
            sessionsById[sessionId] = session

        case .kanbanUpdated(let payload):
            applyKanban(payload)

        case .conductorState(let payload):
            // Ignore a server-sent `listening` (client-local, contract §3.4).
            if payload.state != .listening {
                conductorState = payload.state
            }

        case .error(let error):
            lastError = error

        case .hello, .heartbeat, .ptyOutput, .memoryChanged, .dryRunResult, .unknown:
            // pty_output → terminal buffers (phase B); memory/dryRun → feature
            // teams; hello/heartbeat/unknown → transport-only.
            break
        }
    }

    private func applyKanban(_ payload: KanbanUpdatedPayload) {
        boardRevision = payload.boardRevision
        switch payload.op {
        case .snapshot:
            cards = payload.cards ?? cards
        case .created, .updated, .moved:
            guard let card = payload.card else { return }
            if let index = cards.firstIndex(where: { $0.cardId == card.cardId }) {
                cards[index] = card
            } else {
                cards.append(card)
            }
        case .deleted:
            if let cardId = payload.cardId ?? payload.card?.cardId {
                cards.removeAll { $0.cardId == cardId }
            }
        case .unknown:
            break
        }
    }

    // MARK: - Reset

    func resetRuntimeState() {
        sessionsById = [:]
        cards = []
        boardRevision = 0
        conductorState = .idle
        lastError = nil
    }
}
