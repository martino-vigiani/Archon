import Foundation
import Observation

/// Owns the full client-side voice path (REQ-ARCH-031): mic permission, lazy
/// model provisioning, push-to-talk capture, live partial transcript, and the
/// finalized intent handoff. `@Observable @MainActor` — the single source of
/// voice UI truth. Audio never leaves the device; only `onFinalIntent` (a
/// finalized UTF-8 string) is emitted (REQ-ARCH-032).
@MainActor
@Observable
final class VoiceStore {

    enum Phase: Sendable, Equatable {
        case idle
        case preparing     // first-run model download/load
        case listening     // mic live, capturing
        case transcribing  // finalizing after key release
    }

    // MARK: - Observed state

    private(set) var phase: Phase = .idle
    private(set) var partialTranscript: String = ""
    private(set) var finalTranscript: String = ""
    private(set) var amplitude: Double = 0
    private(set) var modelState: ModelLoadState = .notLoaded
    private(set) var micPermission: MicPermissionState = MicrophoneAuthorization.current()
    private(set) var errorMessage: String?

    var isListening: Bool { phase == .listening }

    /// First-run download progress (0…1) for the calm progress UI, or `nil`.
    var modelDownloadProgress: Double? {
        if case .downloading(let p) = modelState { return p }
        return nil
    }

    /// Emitted exactly once per finalized utterance / typed intent. Wired by the
    /// coordinator to `ConductorStore.sendIntent`.
    var onFinalIntent: (@MainActor (String, IntentSource) -> Void)?
    /// Notifies the coordinator that `isListening` changed (drives the orb).
    var onListeningChanged: (@MainActor (Bool) -> Void)?

    private let transcriber: any SpeechTranscribing
    private var prepareTask: Task<Void, Never>?

    init(transcriber: any SpeechTranscribing) {
        self.transcriber = transcriber
    }

    // MARK: - Push-to-talk

    /// Key-down: begin capture. On first use it kicks off model provisioning and
    /// does not capture that press (voice degrades gracefully until ready,
    /// REQ-ARCH-034); the next press captures.
    func beginPushToTalk() {
        guard phase == .idle else { return }
        errorMessage = nil

        // Permission gate (REQ-ARCH-031): mic active only with explicit grant.
        switch micPermission {
        case .denied:
            errorMessage = "Microphone access is denied. Enable it in System Settings › Privacy."
            return
        case .undetermined:
            requestPermissionThenPrepare()
            return
        case .granted:
            break
        }

        guard modelState.canCapture else {
            beginPreparingModel()
            return
        }

        startCapture()
    }

    /// Key-up: finalize and hand off the transcript.
    func endPushToTalk() {
        guard phase == .listening else { return }
        setPhase(.transcribing)
        setListening(false)
        let transcriber = self.transcriber
        Task { [weak self] in
            let final = await transcriber.stopLiveTranscription()
            guard let self else { return }
            self.finalTranscript = final
            self.partialTranscript = ""
            self.amplitude = 0
            self.setPhase(.idle)
            let trimmed = final.trimmingCharacters(in: .whitespacesAndNewlines)
            if !trimmed.isEmpty {
                self.onFinalIntent?(trimmed, .voiceTranscript)
            }
        }
    }

    /// Toggle helper for the orb single-click affordance (REQ-UX-043).
    func togglePushToTalk() {
        if phase == .listening { endPushToTalk() } else { beginPushToTalk() }
    }

    /// Typed intent path (alternative to voice, REQ-ARCH-041). Bypasses capture.
    func submitTyped(_ text: String) {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        onFinalIntent?(trimmed, .text)
    }

    // MARK: - Model provisioning

    /// Proactively provision the model (e.g. from Settings) without capturing.
    func warmUpModel() {
        guard modelState == .notLoaded else { return }
        beginPreparingModel(startCaptureWhenReady: false)
    }

    private func beginPreparingModel(startCaptureWhenReady: Bool = false) {
        guard prepareTask == nil else { return }
        setPhase(.preparing)
        let transcriber = self.transcriber
        prepareTask = Task { [weak self] in
            await transcriber.prepareModel { [weak self] state in
                Task { @MainActor in
                    self?.modelState = state
                }
            }
            guard let self else { return }
            self.prepareTask = nil
            if self.modelState.isReady {
                self.setPhase(.idle)
                if startCaptureWhenReady { self.startCapture() }
            } else {
                if case .failed(let message) = self.modelState {
                    self.errorMessage = "Could not prepare dictation: \(message)"
                }
                self.setPhase(.idle)
            }
        }
    }

    private func requestPermissionThenPrepare() {
        Task { [weak self] in
            let result = await MicrophoneAuthorization.request()
            guard let self else { return }
            self.micPermission = result
            if result == .granted {
                self.beginPreparingModel()
            } else {
                self.errorMessage = "Microphone access is required for voice dictation."
            }
        }
    }

    // MARK: - Capture

    private func startCapture() {
        setPhase(.listening)
        partialTranscript = ""
        finalTranscript = ""
        setListening(true)
        let transcriber = self.transcriber
        Task { [weak self] in
            do {
                try await transcriber.startLiveTranscription(
                    onPartial: { [weak self] text in
                        Task { @MainActor in
                            guard let self, self.phase == .listening else { return }
                            self.partialTranscript = text
                        }
                    },
                    onAmplitude: { [weak self] value in
                        Task { @MainActor in
                            guard let self, self.phase == .listening else { return }
                            self.amplitude = value
                        }
                    }
                )
            } catch {
                Task { @MainActor [weak self] in
                    guard let self else { return }
                    self.errorMessage = "Could not start the microphone."
                    self.setPhase(.idle)
                    self.setListening(false)
                }
            }
        }
    }

    // MARK: - Helpers

    private func setPhase(_ newPhase: Phase) {
        phase = newPhase
    }

    private func setListening(_ listening: Bool) {
        onListeningChanged?(listening)
    }
}
