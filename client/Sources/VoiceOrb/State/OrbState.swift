import Foundation

/// The six canonical orb behavioural states (REQ-UX-040 / Q18). This is the
/// *resolved presentation* state the renderer draws — distinct from
/// `ConductorState` (contract enum, which additionally carries the client-local
/// `listening` case and a decode-tolerant `unknown`).
///
/// The server owns `idle | thinking | spawning | streaming | error`; the client
/// owns `listening` (WhisperKit push-to-talk). `OrbStateMachine` folds both
/// sources plus connection/energy signals into a single `OrbPresentation`.
enum OrbState: String, Sendable, Equatable, CaseIterable {
    case idle
    case listening
    case thinking
    case spawning
    case streaming
    case error

    /// Maps a server-owned `ConductorState` into the six-state orb vocabulary.
    /// A server `listening`/`unknown` collapses to `idle` (server never drives
    /// `listening`; local push-to-talk is layered on top by `OrbStateMachine`).
    static func from(conductor: ConductorState) -> OrbState {
        switch conductor {
        case .idle, .listening, .unknown: return .idle
        case .thinking: return .thinking
        case .spawning: return .spawning
        case .streaming: return .streaming
        case .error: return .error
        }
    }

    /// VoiceOver read-back for the orb (REQ-UX-041 — the orb is the single
    /// source of truth for orchestration status).
    var accessibilityLabel: String {
        switch self {
        case .idle: return "Conductor idle"
        case .listening: return "Listening"
        case .thinking: return "Conductor thinking"
        case .spawning: return "Spawning terminals"
        case .streaming: return "Terminals running"
        case .error: return "Conductor error"
        }
    }

    var isError: Bool { self == .error }
}

/// Reduced-motion + energy-saver render posture (REQ-DSN-071 / REQ-DSN-072).
/// The two flags stack: Low Power Mode + Reduce Motion apply together.
struct OrbMotionProfile: Sendable, Equatable {
    var reduceMotion: Bool
    var lowPower: Bool

    init(reduceMotion: Bool = false, lowPower: Bool = false) {
        self.reduceMotion = reduceMotion
        self.lowPower = lowPower
    }

    /// With Reduce Motion the fluid field is replaced by a static radial
    /// gradient (REQ-DSN-071).
    var rendersStaticField: Bool { reduceMotion }

    /// The soft chromatic bloom is disabled under Reduce Motion or Low Power
    /// (REQ-DSN-072: `bloom.isHidden = true`).
    var bloomEnabled: Bool { !reduceMotion && !lowPower }

    /// Target animation cadence. `0` means "no continuous animation"
    /// (Reduce Motion). Low Power caps the shader loop to 30 Hz
    /// (REQ-DSN-072 / REQ-PERF-031); otherwise 120 Hz (REQ-DSN-053).
    var targetHz: Double {
        if reduceMotion { return 0 }
        return lowPower ? 30 : 120
    }

    static let full = OrbMotionProfile()
}

/// Transport posture layered onto the orb (Addendum §A4): on WS drop the orb
/// dims to a "disconnected" variant while keeping its last known state.
enum OrbConnection: Sendable, Equatable {
    case connected
    case disconnected
}

/// The inputs the pure state machine folds into a presentation.
struct OrbInputs: Sendable, Equatable {
    /// Latest server-owned conductor state (from `conductor_state` events).
    var serverState: ConductorState
    /// Client-local push-to-talk capture is active.
    var isListening: Bool
    /// WebSocket transport posture.
    var connection: OrbConnection
    /// Accessibility Reduce Motion is on.
    var reduceMotion: Bool
    /// Low Power Mode is active.
    var lowPower: Bool

    init(
        serverState: ConductorState = .idle,
        isListening: Bool = false,
        connection: OrbConnection = .connected,
        reduceMotion: Bool = false,
        lowPower: Bool = false
    ) {
        self.serverState = serverState
        self.isListening = isListening
        self.connection = connection
        self.reduceMotion = reduceMotion
        self.lowPower = lowPower
    }
}

/// The fully-resolved thing the orb renderer draws.
struct OrbPresentation: Sendable, Equatable {
    var state: OrbState
    var isDisconnected: Bool
    var motion: OrbMotionProfile

    init(state: OrbState = .idle, isDisconnected: Bool = false, motion: OrbMotionProfile = .full) {
        self.state = state
        self.isDisconnected = isDisconnected
        self.motion = motion
    }
}
