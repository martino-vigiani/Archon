import Foundation

/// Coalesces high-frequency "dirty" signals into at most one flush per frame
/// (~16 ms / 60 Hz), so PTY throughput never triggers more than ≤ 63 main-thread
/// UI updates per second (REQ-PERF-020 / REQ-ARCH-010). A single instance drives
/// all terminals: many `schedule()` calls within one window collapse into one
/// `onFlush`.
@MainActor
final class FrameCoalescer {
    private let interval: Duration
    private let onFlush: () -> Void
    private var scheduled = false

    init(interval: Duration = .milliseconds(16), onFlush: @escaping () -> Void) {
        self.interval = interval
        self.onFlush = onFlush
    }

    /// Requests a flush. No-op if one is already pending within this frame.
    func schedule() {
        guard !scheduled else { return }
        scheduled = true
        Task { @MainActor [weak self] in
            guard let self else { return }
            try? await Task.sleep(for: self.interval)
            self.scheduled = false
            self.onFlush()
        }
    }
}
