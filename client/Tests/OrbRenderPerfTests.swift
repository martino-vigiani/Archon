import Testing
import Foundation
@testable import Archon

// Locks REQ-PERF-015 / REQ-DSN-074: the orb pauses its CPU render loop at idle
// and off-screen, and its fluid never repeats within ≥ 120 s.

@Suite("Orb render gate (REQ-PERF-015 / REQ-DSN-074)")
struct OrbRenderGateTests {

    @Test("idle with no voice on a visible window pauses the loop")
    func idleSilentPauses() {
        #expect(OrbRenderGate.wantsAnimation(state: .idle, amplitude: 0, windowVisible: true) == false)
        #expect(OrbRenderGate.wantsAnimation(state: .idle, amplitude: OrbRenderGate.quietAmplitude, windowVisible: true) == false)
    }

    @Test("idle but with voice amplitude keeps animating (reactive glow)")
    func idleWithVoiceAnimates() {
        #expect(OrbRenderGate.wantsAnimation(state: .idle, amplitude: 0.5, windowVisible: true))
    }

    @Test("non-idle states animate even in silence")
    func activeStatesAnimate() {
        for state in [OrbState.listening, .thinking, .spawning, .streaming, .error] {
            #expect(OrbRenderGate.wantsAnimation(state: state, amplitude: 0, windowVisible: true), "\(state)")
        }
    }

    @Test("an occluded/minimized window hard-pauses regardless of state")
    func occludedPauses() {
        #expect(OrbRenderGate.wantsAnimation(state: .streaming, amplitude: 0.9, windowVisible: false) == false)
        #expect(OrbRenderGate.wantsAnimation(state: .listening, amplitude: 0.9, windowVisible: false) == false)
    }
}

@Suite("Orb fluid non-repetition (REQ-DSN-074)")
struct OrbFluidFieldTests {

    /// The full blob-field configuration at `time` (all offsets concatenated) —
    /// the thing the eye perceives. Two nearby vectors look like the same frame.
    private func signature(at time: Double) -> [Double] {
        var out: [Double] = []
        out.reserveCapacity(OrbFluidField.blobCount * 2)
        for i in 0..<OrbFluidField.blobCount {
            let p = OrbFluidField.offset(blob: i, time: time, flowSpeed: 0.5, radius: 30, turbulence: 0.35)
            out.append(p.x); out.append(p.y)
        }
        return out
    }

    private func distance(_ a: [Double], _ b: [Double]) -> Double {
        zip(a, b).reduce(0) { $0 + ($1.0 - $1.1) * ($1.0 - $1.1) }.squareRoot()
    }

    @Test("the field never returns to a prior configuration within 120 s")
    func neverRepeatsWithin120s() {
        // Excluding the trivial continuity edge (lag < 8 s, where the slow idle
        // field simply hasn't drifted away yet), the closest the configuration
        // ever comes back to an earlier frame stays far from zero — no visual
        // loop — against a field amplitude scale of ~27 pt.
        var minDistance = Double.greatestFiniteMagnitude
        var atLag = 0.0
        for anchor in [0.0, 250.0, 1000.0] {
            let base = signature(at: anchor)
            for lagMillis in stride(from: 8_000, through: 120_000, by: 50) {
                let lag = Double(lagMillis) / 1000.0
                let d = distance(base, signature(at: anchor + lag))
                if d < minDistance { minDistance = d; atLag = lag }
            }
        }
        #expect(minDistance > 6.0)   // measured ≈ 12.0 pt at ~87 s
        print("PERF-ORB non-repetition: nearest return over 120s = \(String(format: "%.2f", minDistance)) pt at lag \(String(format: "%.1f", atLag))s")
    }

    @Test("field is deterministic and blobs are spatially distinct")
    func deterministicDistinct() {
        let a = OrbFluidField.offset(blob: 0, time: 12.5, flowSpeed: 0.9, radius: 30, turbulence: 0.7)
        let b = OrbFluidField.offset(blob: 0, time: 12.5, flowSpeed: 0.9, radius: 30, turbulence: 0.7)
        #expect(a == b)
        let c = OrbFluidField.offset(blob: 3, time: 12.5, flowSpeed: 0.9, radius: 30, turbulence: 0.7)
        #expect(a != c)
    }

    @Test("blob radius stays within its analytic bounds")
    func blobRadiusBounds() {
        let r = 40.0
        for i in 0..<OrbFluidField.blobCount {
            for step in 0...200 {
                let t = Double(step) * 0.37
                let br = OrbFluidField.blobRadius(blob: i, time: t, flowSpeed: 1.1, radius: r)
                #expect(br >= r * (0.5 - 0.18) - 0.001)
                #expect(br <= r * (0.5 + 0.18) + 0.001)
            }
        }
    }
}
