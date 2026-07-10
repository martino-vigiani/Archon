import CoreGraphics
import Foundation

/// Per-state, resolution-independent render parameters for the orb (REQ-DSN-051
/// / REQ-DSN-057). Pure value type so the numbers are inspectable/testable.
struct OrbRenderModel: Sendable, Equatable {
    /// Resting diameter in points (REQ-DSN-051: 56 pt resting, ≤ 96 pt listening).
    var baseDiameter: CGFloat
    /// Peak diameter the orb expands to for this state.
    var expandedDiameter: CGFloat
    /// Continuous breathing amplitude in points (REQ-DSN-057: ± 4 pt at 0.15 Hz).
    var breathingAmplitude: CGFloat
    /// Breathing frequency in Hz (REQ-DSN-057: ~0.15 Hz).
    var breathingHz: Double
    /// How strongly the internal fluid blobs drift (0…1).
    var turbulence: Double
    /// Base outer-glow radius as a fraction of the diameter.
    var glowScale: Double
    /// Speed multiplier of the fluid evolution for this state.
    var flowSpeed: Double

    static let restingDiameter: CGFloat = 56
    static let listeningDiameter: CGFloat = 96

    static func model(for state: OrbState) -> OrbRenderModel {
        switch state {
        case .idle:
            return OrbRenderModel(baseDiameter: 56, expandedDiameter: 60,
                                  breathingAmplitude: 4, breathingHz: 0.15,
                                  turbulence: 0.35, glowScale: 0.55, flowSpeed: 0.5)
        case .listening:
            return OrbRenderModel(baseDiameter: 72, expandedDiameter: 96,
                                  breathingAmplitude: 4, breathingHz: 0.15,
                                  turbulence: 0.85, glowScale: 0.9, flowSpeed: 1.1)
        case .thinking:
            return OrbRenderModel(baseDiameter: 62, expandedDiameter: 68,
                                  breathingAmplitude: 4, breathingHz: 0.18,
                                  turbulence: 0.7, glowScale: 0.62, flowSpeed: 1.4)
        case .spawning:
            return OrbRenderModel(baseDiameter: 64, expandedDiameter: 72,
                                  breathingAmplitude: 4, breathingHz: 0.2,
                                  turbulence: 0.6, glowScale: 0.68, flowSpeed: 1.2)
        case .streaming:
            return OrbRenderModel(baseDiameter: 60, expandedDiameter: 66,
                                  breathingAmplitude: 4, breathingHz: 0.15,
                                  turbulence: 0.5, glowScale: 0.6, flowSpeed: 0.9)
        case .error:
            return OrbRenderModel(baseDiameter: 58, expandedDiameter: 64,
                                  breathingAmplitude: 3, breathingHz: 0.5,
                                  turbulence: 0.4, glowScale: 0.7, flowSpeed: 0.7)
        }
    }

    /// The instantaneous diameter given continuous breathing + a 0…1 amplitude
    /// envelope (voice reactivity, REQ-DSN-054). Monotonic in `amplitude`.
    func diameter(time: Double, amplitude: Double) -> CGFloat {
        let breath = sin(time * breathingHz * 2 * .pi) * breathingAmplitude
        let reach = expandedDiameter - baseDiameter
        let ampReach = CGFloat(max(0, min(1, amplitude))) * reach
        return baseDiameter + breath + ampReach
    }

    /// Outer-glow radius for a given diameter and amplitude (grows with voice —
    /// REQ-DSN-054: glow radius never decreases while amplitude increases).
    func glowRadius(diameter: CGFloat, amplitude: Double) -> CGFloat {
        let amp = CGFloat(max(0, min(1, amplitude)))
        return diameter * CGFloat(glowScale) * (0.9 + amp * 0.7)
    }
}
