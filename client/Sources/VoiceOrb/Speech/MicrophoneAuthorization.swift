import AVFoundation

/// Microphone permission posture (REQ-ARCH-031: mic access is gated by explicit
/// user action; the listening indicator is visible only while the mic is live).
enum MicPermissionState: Sendable, Equatable {
    case undetermined
    case granted
    case denied

    var canCapture: Bool { self == .granted }
}

/// Thin wrapper over `AVCaptureDevice` audio authorization. Kept separate so the
/// permission flow can be surfaced calmly in the Conductor surface.
enum MicrophoneAuthorization {

    static func current() -> MicPermissionState {
        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .authorized: return .granted
        case .denied, .restricted: return .denied
        case .notDetermined: return .undetermined
        @unknown default: return .undetermined
        }
    }

    /// Request access (shows the system prompt on first call). Idempotent
    /// afterwards.
    static func request() async -> MicPermissionState {
        if current() == .granted { return .granted }
        let granted = await AVCaptureDevice.requestAccess(for: .audio)
        return granted ? .granted : .denied
    }
}
