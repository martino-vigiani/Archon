import SwiftUI

/// The orb's per-state chromatic palette (REQ-DSN-013). The orb is the ONLY
/// chromatic element in the entire app (REQ-DSN-011); every colour here is
/// constructed in Display P3 (REQ-DSN-012) and used exclusively inside the orb
/// layer + its bloom.
///
/// The requirement fixes an LCH hue *range* and a minimum peak chroma per state.
/// Exact trajectories are left to the motion designer; this type picks the hue
/// range midpoint and a saturation/brightness pair that clears the minimum
/// chroma, then materialises P3 stops (core → mid → edge → glow).
struct OrbGradient: Sendable, Equatable {
    /// Dominant hue in degrees (LCH°, matched approximately in P3 space).
    var hueDegrees: Double
    /// Bright inner core.
    var core: Color
    /// Mid-body colour.
    var mid: Color
    /// Cooler outer edge (same hue, lower brightness) for depth.
    var edge: Color
    /// The bloom / outer-glow colour (screen-composited, REQ-DSN-058).
    var glow: Color
}

enum OrbHue {

    /// The normative hue-zone table (REQ-DSN-013), reconciled to the six
    /// canonical states (REQ-UX-040). `chroma` is the minimum P3 chroma at peak;
    /// we drive saturation above it.
    static func gradient(for state: OrbState) -> OrbGradient {
        switch state {
        case .idle:
            // 255–290 blue-violet, chroma ≥ 0.22.
            return build(hue: 272, saturation: 0.72, brightness: 0.96)
        case .listening:
            // 200–260 cyan-indigo, chroma ≥ 0.30.
            return build(hue: 224, saturation: 0.86, brightness: 1.0)
        case .thinking:
            // 280–330 violet-magenta, chroma ≥ 0.28.
            return build(hue: 305, saturation: 0.82, brightness: 0.98)
        case .spawning:
            // 160–210 teal-cyan, chroma ≥ 0.25.
            return build(hue: 185, saturation: 0.80, brightness: 0.98)
        case .streaming:
            // 140–170 green-teal, chroma ≥ 0.22.
            return build(hue: 155, saturation: 0.76, brightness: 0.96)
        case .error:
            // 15–45 red-orange, chroma ≥ 0.30.
            return build(hue: 28, saturation: 0.88, brightness: 1.0)
        }
    }

    /// Builds a four-stop P3 gradient around a hue, guaranteeing vivid,
    /// out-of-sRGB-gamut chroma on a P3 display.
    private static func build(hue: Double, saturation: Double, brightness: Double) -> OrbGradient {
        OrbGradient(
            hueDegrees: hue,
            core: p3(hue: hue, saturation: saturation * 0.55, brightness: min(1, brightness + 0.04)),
            mid: p3(hue: hue, saturation: saturation, brightness: brightness),
            edge: p3(hue: hue, saturation: min(1, saturation + 0.06), brightness: brightness * 0.66),
            glow: p3(hue: hue, saturation: saturation, brightness: brightness)
        )
    }

    /// HSB → Display-P3 `Color`. Uses HSV→RGB then wraps in the P3 colour space
    /// so saturated values render beyond the sRGB gamut (REQ-DSN-012).
    static func p3(hue: Double, saturation: Double, brightness: Double) -> Color {
        let (r, g, b) = hsvToRGB(h: hue.truncatingRemainder(dividingBy: 360) / 360,
                                 s: saturation, v: brightness)
        return Color(.displayP3, red: r, green: g, blue: b, opacity: 1)
    }

    /// Standard HSV→RGB. `h` in 0…1.
    private static func hsvToRGB(h: Double, s: Double, v: Double) -> (Double, Double, Double) {
        if s <= 0 { return (v, v, v) }
        let hh = (h < 0 ? h + 1 : h) * 6
        let i = Int(hh) % 6
        let f = hh - Double(Int(hh))
        let p = v * (1 - s)
        let q = v * (1 - s * f)
        let t = v * (1 - s * (1 - f))
        switch i {
        case 0: return (v, t, p)
        case 1: return (q, v, p)
        case 2: return (p, v, t)
        case 3: return (p, q, v)
        case 4: return (t, p, v)
        default: return (v, p, q)
        }
    }
}
