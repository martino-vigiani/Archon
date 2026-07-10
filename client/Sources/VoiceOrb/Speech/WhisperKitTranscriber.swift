import Foundation

#if canImport(WhisperKit)
import WhisperKit

/// On-device push-to-talk transcription backed by WhisperKit (Q25). All audio
/// stays on the device (REQ-ARCH-030): the model runs only while the key is
/// held, partials are shown locally, and only the final UTF-8 transcript is
/// returned upward. The model (base tier, ~145 MB) downloads lazily on first use
/// (REQ-ARCH-034) — never bundled.
///
/// A `final class` (not an `actor`): WhisperKit's `open class` is non-Sendable
/// and its async methods are nonisolated, so awaiting them from an actor trips
/// region isolation. The push-to-talk lifecycle serializes prepare → start →
/// stop (never concurrent), so `@unchecked Sendable` is sound here; the
/// live-recording amplitude callback only forwards to a `@Sendable` sink.
final class WhisperKitTranscriber: SpeechTranscribing, @unchecked Sendable {

    /// Base tier per Q25 (~145 MB English/multilingual base model).
    private let variant = "base"

    private var whisperKit: WhisperKit?
    private var loadState: ModelLoadState = .notLoaded
    private var partialLoop: Task<Void, Never>?
    private var isCapturing = false

    init() {}

    func prepareModel(progress: @escaping @Sendable (ModelLoadState) -> Void) async {
        if loadState.isReady { progress(.ready); return }
        do {
            progress(.downloading(0))
            let folder = try await WhisperKit.download(
                variant: variant,
                progressCallback: { p in
                    progress(.downloading(p.fractionCompleted))
                }
            )
            progress(.loading)
            let config = WhisperKitConfig(
                model: variant,
                modelFolder: folder.path,
                verbose: false,
                prewarm: false,
                load: true,
                download: false
            )
            whisperKit = try await WhisperKit(config)
            loadState = .ready
            progress(.ready)
        } catch {
            loadState = .failed(error.localizedDescription)
            progress(.failed(error.localizedDescription))
        }
    }

    func startLiveTranscription(
        onPartial: @escaping @Sendable (String) -> Void,
        onAmplitude: @escaping @Sendable (Double) -> Void
    ) async throws {
        guard let whisperKit else { throw WhisperKitTranscriberError.modelNotReady }
        guard !isCapturing else { return }
        isCapturing = true

        // Live mic capture. The callback runs on the audio thread and only
        // forwards an amplitude envelope to the `@Sendable` sink.
        try whisperKit.audioProcessor.startRecordingLive(inputDeviceID: nil) { chunk in
            onAmplitude(Self.amplitude(of: chunk))
        }

        // Poll the accumulating buffer for partial hypotheses (~2 Hz). Cheap
        // relative to the live audio; final accuracy comes on release.
        partialLoop = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .milliseconds(500))
                guard let self else { return }
                await self.emitPartial(onPartial)
            }
        }
    }

    func stopLiveTranscription() async -> String {
        partialLoop?.cancel()
        partialLoop = nil
        guard let whisperKit, isCapturing else { isCapturing = false; return "" }
        isCapturing = false
        whisperKit.audioProcessor.stopRecording()

        let samples = Array(whisperKit.audioProcessor.audioSamples)
        whisperKit.audioProcessor.purgeAudioSamples(keepingLast: 0)
        guard samples.count > 1_600 else { return "" } // < ~0.1 s → nothing said
        let text = (try? await whisperKit.transcribe(audioArray: samples))?
            .map(\.text)
            .joined(separator: " ") ?? ""
        return Self.clean(text)
    }

    // MARK: - Internals

    private func emitPartial(_ onPartial: @escaping @Sendable (String) -> Void) async {
        guard let whisperKit, isCapturing else { return }
        let samples = Array(whisperKit.audioProcessor.audioSamples)
        guard samples.count > 8_000 else { return } // wait for ~0.5 s of audio
        guard let results = try? await whisperKit.transcribe(audioArray: samples) else { return }
        let text = Self.clean(results.map(\.text).joined(separator: " "))
        if !text.isEmpty { onPartial(text) }
    }

    /// RMS amplitude, gained + clamped to 0…1 for orb reactivity.
    private static func amplitude(of samples: [Float]) -> Double {
        guard !samples.isEmpty else { return 0 }
        var sum: Double = 0
        for s in samples { sum += Double(s) * Double(s) }
        let rms = (sum / Double(samples.count)).squareRoot()
        return min(1, rms * 8)
    }

    /// WhisperKit emits special tokens/whitespace; strip them for display.
    private static func clean(_ text: String) -> String {
        text
            .replacingOccurrences(of: "<|endoftext|>", with: "")
            .replacingOccurrences(of: "<|nospeech|>", with: "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }
}

enum WhisperKitTranscriberError: Error {
    case modelNotReady
}

/// Factory: the real WhisperKit engine when the package is linked.
func makeDefaultTranscriber() -> any SpeechTranscribing {
    WhisperKitTranscriber()
}

#else

/// Graceful degradation when WhisperKit is not linked (REQ-ARCH-034): voice is
/// disabled with an explanation; typed intent still works.
func makeDefaultTranscriber() -> any SpeechTranscribing {
    StubTranscriber()
}

#endif
