import Foundation

/// Lazy on-device model provisioning state (Q25 / REQ-ARCH-034). Drives the calm
/// first-run download progress UI; nothing is bundled.
enum ModelLoadState: Sendable, Equatable {
    case notLoaded
    /// Downloading the model; `progress` is 0…1.
    case downloading(Double)
    case loading
    case ready
    case failed(String)

    var isReady: Bool { self == .ready }

    /// Whether voice capture may begin.
    var canCapture: Bool { self == .ready }
}

/// On-device speech transcription boundary (REQ-ARCH-030/031/032). Audio never
/// leaves the device; only the final UTF-8 transcript is handed upward. Behind a
/// protocol so the pipeline is unit-testable with a deterministic stub and so
/// the WhisperKit dependency is confined to one file.
protocol SpeechTranscribing: AnyObject, Sendable {
    /// Provision the model lazily (download + load), reporting progress. Safe to
    /// call repeatedly; a no-op once ready.
    func prepareModel(progress: @escaping @Sendable (ModelLoadState) -> Void) async

    /// Begin a live utterance. Partial hypotheses are delivered via `onPartial`
    /// (shown locally only, never sent — REQ-ARCH-032). `onAmplitude` (0…1)
    /// drives the orb's voice reactivity (REQ-DSN-054).
    func startLiveTranscription(
        onPartial: @escaping @Sendable (String) -> Void,
        onAmplitude: @escaping @Sendable (Double) -> Void
    ) async throws

    /// Stop capture and return the finalized transcript.
    func stopLiveTranscription() async -> String
}

/// A deterministic transcriber for tests, previews, and the graceful-degradation
/// path when WhisperKit is unavailable (REQ-ARCH-034). Emits scripted partials
/// and a fixed final; never touches the microphone.
final class StubTranscriber: SpeechTranscribing, @unchecked Sendable {
    private let finalText: String
    private let partials: [String]
    private var streamTask: Task<Void, Never>?

    init(finalText: String = "", partials: [String] = []) {
        self.finalText = finalText
        self.partials = partials
    }

    func prepareModel(progress: @escaping @Sendable (ModelLoadState) -> Void) async {
        progress(.downloading(0.5))
        progress(.ready)
    }

    func startLiveTranscription(
        onPartial: @escaping @Sendable (String) -> Void,
        onAmplitude: @escaping @Sendable (Double) -> Void
    ) async throws {
        let partials = self.partials
        streamTask = Task {
            var i = 0
            for partial in partials {
                if Task.isCancelled { return }
                onPartial(partial)
                onAmplitude(0.3 + 0.5 * abs(sin(Double(i))))
                i += 1
                try? await Task.sleep(for: .milliseconds(120))
            }
        }
    }

    func stopLiveTranscription() async -> String {
        streamTask?.cancel()
        streamTask = nil
        return finalText
    }
}
