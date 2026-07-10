import Foundation
import Observation

/// Wires the VoiceOrb sector together and owns its long-lived objects: the
/// stores, the push-to-talk hotkey, the speech engine, the orb environment, and
/// the WS subscriptions that fold conductor/error/dry-run events + connection
/// posture into the orb's presentation. `@Observable @MainActor` so the orb (in
/// its own hosting view) re-renders as state changes.
@MainActor
@Observable
final class VoiceOrbCoordinator {

    let voice: VoiceStore
    let conductor: ConductorStore
    let orbEnvironment: OrbEnvironment
    @ObservationIgnored let positionStore: OrbPositionStore
    @ObservationIgnored private let hotKey = HotKeyManager()
    @ObservationIgnored private let wsClient: WSClient
    @ObservationIgnored private var eventTask: Task<Void, Never>?
    @ObservationIgnored private var connectionTask: Task<Void, Never>?

    /// WS transport posture, mirrored for the disconnected orb variant (§A4).
    private(set) var connection: OrbConnection = .connected

    init(container: AppContainer) {
        self.wsClient = container.wsClient
        self.voice = VoiceStore(transcriber: makeDefaultTranscriber())
        self.conductor = ConductorStore(container: container)
        self.orbEnvironment = OrbEnvironment()
        self.positionStore = OrbPositionStore(container: container)

        wireVoice()
        wireHotKey()
        startObserving()
    }

    // MARK: - Derived orb presentation (pure fold)

    var orbPresentation: OrbPresentation {
        OrbStateMachine.resolve(
            OrbInputs(
                serverState: conductor.serverConductorState,
                isListening: voice.isListening,
                connection: connection,
                reduceMotion: orbEnvironment.reduceMotion,
                lowPower: orbEnvironment.lowPower
            )
        )
    }

    /// Whether the Conductor surface should float above the orb (activity or a
    /// pending exchange). The user can also pin it open via the edge affordance.
    var hasConductorActivity: Bool {
        voice.phase != .idle
            || conductor.currentPlan != nil
            || conductor.lastError != nil
            || conductor.isPlanning
            || !conductor.exchanges.isEmpty
    }

    /// Orb single-click behaviour (REQ-UX-043): cancel while planning, else
    /// toggle push-to-talk.
    func orbClicked() {
        if conductor.isPlanning || conductor.hasPendingPlan {
            conductor.cancelCurrentPlan()
        } else {
            voice.togglePushToTalk()
        }
    }

    // MARK: - Wiring

    private func wireVoice() {
        voice.onFinalIntent = { [weak self] text, source in
            self?.conductor.sendIntent(text: text, source: source)
        }
        // `onListeningChanged` triggers observation of `voice.isListening`, which
        // `orbPresentation` already reads — no extra state needed.
        voice.onListeningChanged = { _ in }
    }

    private func wireHotKey() {
        hotKey.onPressed = { [weak self] in self?.voice.beginPushToTalk() }
        hotKey.onReleased = { [weak self] in self?.voice.endPushToTalk() }
        hotKey.register(.defaultBinding)
    }

    private func startObserving() {
        let wsClient = self.wsClient
        eventTask = Task { @MainActor [weak self] in
            let stream = await wsClient.events()
            for await envelope in stream {
                self?.conductor.apply(envelope)
            }
        }
        connectionTask = Task { @MainActor [weak self] in
            let stream = await wsClient.connectionStates()
            for await state in stream {
                self?.updateConnection(state)
            }
        }
    }

    private func updateConnection(_ state: WSConnectionState) {
        switch state {
        case .connected:
            connection = .connected
        case .idle, .connecting, .reconnecting, .incompatible, .disconnected:
            connection = .disconnected
        }
    }
}
