import CoreGraphics
import Foundation

/// The analytic drifting-blob field the orb `Canvas` composites (REQ-DSN-057).
/// Extracted as a pure, resolution-independent function so its **non-repetition**
/// can be verified (REQ-DSN-074 wants no visually identical frame within ≥ 120 s).
///
/// The per-component angular-frequency multipliers are mutually incommensurate —
/// distinct square-root scalings, whose pairwise ratios are irrational — so the
/// composite motion is quasi-periodic and never exactly repeats. A very slow
/// phase drift removes any lingering near-alignment cheaply, and the blobs are
/// spaced by the golden angle so they never phase-lock into a rosette.
enum OrbFluidField {

    static let blobCount = 5

    // Incommensurate frequency multipliers (× flow). Each is 0.1·√p for a
    // distinct prime p, so no fi/fj is a low-order rational → no short common
    // period → the field does not repeat within the ≥ 120 s target.
    static let f1 = 0.1 * 2.0.squareRoot()    // √2  ≈ 0.141421
    static let f2 = 0.1 * 3.0.squareRoot()    // √3  ≈ 0.173205
    static let f3 = 0.1 * 5.0.squareRoot()    // √5  ≈ 0.223607
    static let f4 = 0.1 * 7.0.squareRoot()    // √7  ≈ 0.264575
    static let f5 = 0.1 * 11.0.squareRoot()   // √11 ≈ 0.331662

    /// Golden angle (radians) — an irrational blob spacing that avoids symmetry.
    static let goldenAngle = 2.399963229728653

    /// Very slow phase drift (Hz) that de-aligns the components over time.
    static let driftHz = 0.013

    static func allFrequencies() -> [Double] { [f1, f2, f3, f4, f5] }

    /// Per-blob centre offset (points) from the orb centre at `time`.
    static func offset(
        blob i: Int,
        time: Double,
        flowSpeed: Double,
        radius: Double,
        turbulence: Double
    ) -> CGPoint {
        let flow = time * flowSpeed
        let drift = time * driftHz
        let phase = Double(i) * goldenAngle
        // Layer 1 drift.
        let ax = sin(flow * f1 + phase + drift) * radius * 0.5 * turbulence
        let ay = cos(flow * f2 + phase * 1.3 - drift) * radius * 0.5 * turbulence
        // Layer 2 domain warp of the drift.
        let wx = sin(flow * f3 + ay * 0.03) * radius * 0.22
        let wy = cos(flow * f4 + ax * 0.03) * radius * 0.22
        return CGPoint(x: ax + wx, y: ay + wy)
    }

    /// Per-blob radius (points) at `time`.
    static func blobRadius(blob i: Int, time: Double, flowSpeed: Double, radius: Double) -> Double {
        let flow = time * flowSpeed
        let phase = Double(i) * goldenAngle
        return radius * (0.5 + 0.18 * sin(flow * f5 + phase))
    }
}
