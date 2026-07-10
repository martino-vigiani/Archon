import Foundation

/// Pure policy for when the orb's animation timeline should run, so the CPU-side
/// `Canvas` loop is not driven at 120 Hz forever (REQ-PERF-015 / REQ-DSN-074).
///
/// The orb animates only when it has something to express — a non-idle state or
/// live voice amplitude — AND its host window is actually on screen. At idle with
/// no voice, or when the window is occluded / minimized / hidden, the timeline
/// pauses and the `Canvas` simply holds its last frame, dropping steady-state
/// idle CPU toward the ≤ 1 % budget (REQ-PERF-006).
enum OrbRenderGate {

    /// Voice amplitude at or below this counts as silence for pause purposes.
    static let quietAmplitude: Double = 0.02

    /// Grace period the orb keeps animating after becoming quiescent, so it eases
    /// to rest rather than freezing abruptly (graceful settle). Occlusion pauses
    /// immediately (no settle) since nothing is visible to ease.
    static let settle: Duration = .milliseconds(2200)

    /// Whether the orb wants continuous animation right now.
    static func wantsAnimation(state: OrbState, amplitude: Double, windowVisible: Bool) -> Bool {
        guard windowVisible else { return false }
        if state == .idle && amplitude <= quietAmplitude { return false }
        return true
    }
}
