import AppKit
import Observation

/// Observes the two OS signals that reshape the orb's render posture:
/// Accessibility Reduce Motion (REQ-DSN-071) and Low Power Mode (REQ-DSN-072 /
/// REQ-PERF-031). `@Observable @MainActor` so the orb re-renders when either
/// flips. Observers live for the app lifetime (this object is coordinator-owned).
@MainActor
@Observable
final class OrbEnvironment {
    private(set) var reduceMotion: Bool
    private(set) var lowPower: Bool

    init() {
        reduceMotion = NSWorkspace.shared.accessibilityDisplayShouldReduceMotion
        lowPower = ProcessInfo.processInfo.isLowPowerModeEnabled
        installObservers()
    }

    private func installObservers() {
        NSWorkspace.shared.notificationCenter.addObserver(
            forName: NSWorkspace.accessibilityDisplayOptionsDidChangeNotification,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            MainActor.assumeIsolated {
                self?.reduceMotion = NSWorkspace.shared.accessibilityDisplayShouldReduceMotion
            }
        }

        NotificationCenter.default.addObserver(
            forName: .NSProcessInfoPowerStateDidChange,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            MainActor.assumeIsolated {
                self?.lowPower = ProcessInfo.processInfo.isLowPowerModeEnabled
            }
        }
    }
}
