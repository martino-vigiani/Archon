import SwiftUI

/// A physical spring (SI units) converted to SwiftUI's `response` /
/// `dampingFraction` parameters. Pure and testable (REQ-DSN-055).
///
/// For a unit mass `m`:
///   - `response`        = 2π · √(m / k)
///   - `dampingFraction` = c / (2 · √(k · m))
struct SpringParameters: Sendable, Equatable {
    var stiffness: Double   // k, N/m
    var damping: Double     // c, N·s/m
    var mass: Double        // m, kg

    init(stiffness: Double, damping: Double, mass: Double = 1) {
        self.stiffness = stiffness
        self.damping = damping
        self.mass = mass
    }

    var response: Double {
        2 * Double.pi * (mass / stiffness).squareRoot()
    }

    var dampingFraction: Double {
        damping / (2 * (stiffness * mass).squareRoot())
    }

    var animation: Animation {
        .spring(response: response, dampingFraction: dampingFraction)
    }
}

/// Named motion events with their locked spring constants (REQ-DSN-055) and
/// reduced-motion substitutions (REQ-DSN-071).
enum MotionEvent: Sendable, CaseIterable {
    case orbExpand           // idle → listening
    case orbContract         // listening → idle
    case orbMorph            // listening → thinking
    case terminalSpawn       // panel slide + fade in
    case terminalDismiss
    case kanbanDragRelease
    case viewSwitch          // primary view cross-slide
    case sidebarToggle       // collapse / expand

    var spring: SpringParameters {
        switch self {
        case .orbExpand:        return SpringParameters(stiffness: 280, damping: 24)
        case .orbContract:      return SpringParameters(stiffness: 200, damping: 20)
        case .orbMorph:         return SpringParameters(stiffness: 320, damping: 26)
        case .terminalSpawn:    return SpringParameters(stiffness: 240, damping: 22)
        case .terminalDismiss:  return SpringParameters(stiffness: 300, damping: 28)
        case .kanbanDragRelease:return SpringParameters(stiffness: 350, damping: 30)
        case .viewSwitch:       return SpringParameters(stiffness: 260, damping: 24)
        case .sidebarToggle:    return SpringParameters(stiffness: 220, damping: 22)
        }
    }

    /// Reduced-motion substitution durations (seconds) per REQ-DSN-071.
    private var reducedMotionDuration: Double {
        switch self {
        case .orbExpand, .orbContract, .orbMorph: return 0.12   // cross-fade
        case .terminalSpawn, .terminalDismiss:    return 0.12   // opacity fade
        case .kanbanDragRelease:                  return 0      // instant snap
        case .viewSwitch:                         return 0.15   // cross-fade
        case .sidebarToggle:                      return 0.10   // opacity fade
        }
    }

    /// The animation to use, honouring Reduce Motion (REQ-UX-102 / REQ-DSN-071).
    func animation(reduceMotion: Bool) -> Animation? {
        if reduceMotion {
            let duration = reducedMotionDuration
            return duration > 0 ? .easeInOut(duration: duration) : nil
        }
        return spring.animation
    }
}

/// Micro-interaction easing (≤ 150 ms) for taps/hovers (REQ-DSN-056c). Never
/// linear (REQ-DSN-056).
enum Micro {
    static let tap: Animation = .easeInOut(duration: 0.12)
    static let hover: Animation = .easeInOut(duration: 0.10)
}

extension View {
    /// Applies a named motion event's animation to a value change, honouring
    /// the environment's Reduce Motion setting.
    func archonMotion<V: Equatable>(_ event: MotionEvent, value: V) -> some View {
        modifier(ArchonMotionModifier(event: event, value: value))
    }
}

private struct ArchonMotionModifier<V: Equatable>: ViewModifier {
    let event: MotionEvent
    let value: V
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    func body(content: Content) -> some View {
        content.animation(event.animation(reduceMotion: reduceMotion), value: value)
    }
}
