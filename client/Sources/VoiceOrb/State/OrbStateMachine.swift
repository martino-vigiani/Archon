import Foundation

/// Pure, deterministic reducer from `OrbInputs` → `OrbPresentation` (REQ-UX-040).
/// Deliberately side-effect-free so the full transition matrix is unit-testable
/// without any UI, timers, or Metal.
///
/// Priority rules (deterministic, ≤ one resolution per input set):
/// 1. Local push-to-talk (`isListening`) always presents `.listening` — a user
///    action outranks server phase (REQ-UX-040 Listening row).
/// 2. Otherwise the server-owned `ConductorState` maps into the six states.
/// 3. Disconnection is an orthogonal overlay: it dims the orb but preserves the
///    last resolved state (Addendum §A4) — it never changes the six-state value.
enum OrbStateMachine {

    /// Fold inputs into a single presentation. Total and pure.
    static func resolve(_ inputs: OrbInputs) -> OrbPresentation {
        let base: OrbState = inputs.isListening
            ? .listening
            : OrbState.from(conductor: inputs.serverState)
        let motion = OrbMotionProfile(
            reduceMotion: inputs.reduceMotion,
            lowPower: inputs.lowPower
        )
        return OrbPresentation(
            state: base,
            isDisconnected: inputs.connection == .disconnected,
            motion: motion
        )
    }

    /// The behavioural transitions permitted by the REQ-UX-040 state table.
    /// Used to validate the canonical acceptance sequence
    /// (Idle→Listening→Thinking→Spawning→Streaming→Idle; Streaming→Error→Idle).
    static func allowedNext(from state: OrbState) -> Set<OrbState> {
        switch state {
        case .idle:
            // "Any of the five below".
            return [.listening, .thinking, .spawning, .streaming, .error]
        case .listening:
            // Key release / silence / Discard → dispatch (thinking), abort
            // (idle), or an error surfaces.
            return [.thinking, .idle, .error]
        case .thinking:
            // First spawn event OR error.
            return [.spawning, .error, .idle]
        case .spawning:
            // All requested sessions open → streaming; a failure → error;
            // an immediate all-terminal outcome → idle.
            return [.streaming, .error, .idle]
        case .streaming:
            // All sessions reach terminal states → idle; any error → error.
            return [.idle, .error]
        case .error:
            // User dismisses → idle; a new intent → listening.
            return [.idle, .listening]
        }
    }

    /// Whether `to` is a legal successor of `from` per REQ-UX-040. A self-edge
    /// (no-op) is always legal.
    static func isLegalTransition(from: OrbState, to: OrbState) -> Bool {
        from == to || allowedNext(from: from).contains(to)
    }
}
