import Testing
import Foundation
@testable import Archon

// MARK: - Orb state machine (REQ-UX-040)

@Suite("Orb state machine")
struct OrbStateMachineTests {

    @Test("server states map to the six orb states")
    func serverMapping() {
        #expect(OrbState.from(conductor: .idle) == .idle)
        #expect(OrbState.from(conductor: .thinking) == .thinking)
        #expect(OrbState.from(conductor: .spawning) == .spawning)
        #expect(OrbState.from(conductor: .streaming) == .streaming)
        #expect(OrbState.from(conductor: .error) == .error)
        // Server never drives listening/unknown → collapse to idle.
        #expect(OrbState.from(conductor: .listening) == .idle)
        #expect(OrbState.from(conductor: .unknown) == .idle)
    }

    @Test("local listening overrides server phase")
    func listeningOverrides() {
        let p = OrbStateMachine.resolve(OrbInputs(serverState: .thinking, isListening: true))
        #expect(p.state == .listening)
    }

    @Test("each server state resolves when not listening")
    func resolveEach() {
        for state in [ConductorState.idle, .thinking, .spawning, .streaming, .error] {
            let p = OrbStateMachine.resolve(OrbInputs(serverState: state, isListening: false))
            #expect(p.state == OrbState.from(conductor: state))
        }
    }

    @Test("disconnection dims without changing the six-state value")
    func disconnectedVariant() {
        let p = OrbStateMachine.resolve(OrbInputs(serverState: .streaming, connection: .disconnected))
        #expect(p.state == .streaming)
        #expect(p.isDisconnected)
    }

    @Test("reduced-motion and low-power variants stack")
    func motionVariants() {
        let reduced = OrbStateMachine.resolve(OrbInputs(reduceMotion: true))
        #expect(reduced.motion.rendersStaticField)
        #expect(reduced.motion.bloomEnabled == false)
        #expect(reduced.motion.targetHz == 0)

        let lowPower = OrbStateMachine.resolve(OrbInputs(lowPower: true))
        #expect(lowPower.motion.rendersStaticField == false)
        #expect(lowPower.motion.bloomEnabled == false)
        #expect(lowPower.motion.targetHz == 30)

        let both = OrbStateMachine.resolve(OrbInputs(reduceMotion: true, lowPower: true))
        #expect(both.motion.rendersStaticField)
        #expect(both.motion.bloomEnabled == false)

        let full = OrbStateMachine.resolve(OrbInputs())
        #expect(full.motion.targetHz == 120)
        #expect(full.motion.bloomEnabled)
    }

    @Test("canonical transition sequence is legal (REQ-UX-040 acceptance)")
    func canonicalTransitions() {
        let happyPath: [OrbState] = [.idle, .listening, .thinking, .spawning, .streaming, .idle]
        for (from, to) in zip(happyPath, happyPath.dropFirst()) {
            #expect(OrbStateMachine.isLegalTransition(from: from, to: to), "\(from)→\(to)")
        }
        // Streaming → Error → Idle.
        #expect(OrbStateMachine.isLegalTransition(from: .streaming, to: .error))
        #expect(OrbStateMachine.isLegalTransition(from: .error, to: .idle))
        // Error → new intent → listening.
        #expect(OrbStateMachine.isLegalTransition(from: .error, to: .listening))
    }

    @Test("illegal transitions are rejected")
    func illegalTransitions() {
        #expect(OrbStateMachine.isLegalTransition(from: .streaming, to: .listening) == false)
        #expect(OrbStateMachine.isLegalTransition(from: .idle, to: .idle)) // self-edge ok
    }
}

// MARK: - Push-to-talk core (Q13)

@Suite("Push-to-talk state")
struct PushToTalkStateTests {

    @Test("press then release yields begin then end")
    func pressRelease() {
        var s = PushToTalkState()
        #expect(s.press() == .begin)
        #expect(s.isCapturing)
        #expect(s.release() == .end)
        #expect(s.isCapturing == false)
    }

    @Test("auto-repeat presses are swallowed")
    func autoRepeat() {
        var s = PushToTalkState()
        #expect(s.press() == .begin)
        #expect(s.press() == nil)
        #expect(s.press() == nil)
        #expect(s.release() == .end)
    }

    @Test("release without press is a no-op")
    func spuriousRelease() {
        var s = PushToTalkState()
        #expect(s.release() == nil)
    }

    @Test("reset ends an active capture")
    func resetEnds() {
        var s = PushToTalkState()
        _ = s.press()
        #expect(s.reset() == .end)
        #expect(s.reset() == nil)
    }
}

// MARK: - Hotkey binding

@Suite("Hotkey binding")
struct HotKeyBindingTests {

    @Test("default binding is ⌥Space")
    func defaultBinding() {
        let b = HotKeyBinding.defaultBinding
        #expect(b.keyCode == HotKeyBinding.spaceKeyCode)
        #expect(b.contains(.option))
        #expect(b.contains(.command) == false)
        #expect(b.displayString == "⌥Space")
    }

    @Test("modifier combinations render in order")
    func modifierGlyphs() {
        let b = HotKeyBinding(keyCode: HotKeyBinding.spaceKeyCode,
                              modifiers: HotKeyBinding.Modifier.control.rawValue
                                       | HotKeyBinding.Modifier.command.rawValue)
        #expect(b.displayString == "⌃⌘Space")
    }

    @Test("binding round-trips through Codable")
    func codable() throws {
        let b = HotKeyBinding.defaultBinding
        let data = try JSONEncoder().encode(b)
        let decoded = try JSONDecoder().decode(HotKeyBinding.self, from: data)
        #expect(decoded == b)
    }
}

// MARK: - Plan decode + confirm building (contract §2.4)

@Suite("Conductor plan")
struct ConductorPlanTests {

    private let planJSON = """
    {
      "intent_id": "01J8W",
      "plan": {
        "plan_id": "01J8V",
        "summary": "Two terminals: one refactors checkout, one writes tests.",
        "proposed_session_count": 2,
        "applied_cap": 4,
        "ceiling": 8,
        "final_count": 2,
        "reduction_reason": null,
        "actions": [
          { "action_id": "01J8V1", "kind": "spawn_session",
            "cwd": "/p/checkout", "prompt": "Refactor checkout flow...",
            "card_ref": "new:refactor-checkout", "rationale": "Primary refactor",
            "destructive": false },
          { "action_id": "01J8V2", "kind": "create_card",
            "column": "in_progress", "title": "Refactor checkout flow",
            "destructive": false },
          { "action_id": "01J8V3", "kind": "propose_memory_edit",
            "rationale": "Record the new adapter contract", "destructive": false }
        ]
      },
      "dry_run": {
        "estimate_ready": true,
        "estimated_session_count": 2,
        "estimated_tokens": 48000,
        "estimated_duration_s": 320,
        "warnings": []
      },
      "expires_at": "2026-07-10T14:08:25.000Z"
    }
    """

    @Test("plan + dry-run decode")
    func decode() throws {
        let response = try ArchonJSON.decode(ConductorMessageResponse.self, from: Data(planJSON.utf8))
        #expect(response.plan.planId == "01J8V")
        #expect(response.plan.actions.count == 3)
        #expect(response.plan.actions[0].kind == .spawnSession)
        #expect(response.plan.actions[1].kind == .createCard)
        #expect(response.plan.actions[2].kind == .proposeMemoryEdit)
        #expect(response.dryRun.estimateReady)
        #expect(response.dryRun.estimatedSessionCount == 2)
    }

    @Test("action presentation flags")
    func actionFlags() throws {
        let response = try ArchonJSON.decode(ConductorMessageResponse.self, from: Data(planJSON.utf8))
        let spawn = response.plan.actions[0]
        let memory = response.plan.actions[2]
        #expect(spawn.isDestructive == false)
        #expect(spawn.isMemoryProposal == false)
        #expect(spawn.detailLine == "Refactor checkout flow...")
        #expect(memory.isMemoryProposal)
        #expect(PlanActionKind.deleteCard.symbolName == "trash")
        #expect(PlanActionKind.spawnSession.label == "Spawn terminal")
    }

    @Test("destructive actions are flagged even without the destructive bit")
    func destructiveByKind() {
        let kill = PlanAction(actionId: "a", kind: .killSession, cwd: nil, prompt: nil,
                              cardRef: nil, column: nil, title: nil, rationale: nil,
                              destructive: false)
        #expect(kill.isDestructive)
    }

    @Test("confirm request carries the cap and a request id")
    func confirmBuilding() throws {
        let request = ConfirmPlanRequest(cap: 2)
        #expect(request.cap == 2)
        #expect(request.requestId.isEmpty == false)
        let json = String(decoding: try ArchonJSON.encode(request), as: UTF8.self)
        #expect(json.contains("\"cap\":2"))
        #expect(json.contains("request_id"))
    }
}

// MARK: - Dry-run formatting (Q14)

@Suite("Dry-run formatting")
struct DryRunFormatTests {

    @Test("nil / not-ready → No estimate")
    func noEstimate() {
        #expect(DryRunFormat.summaryLine(nil) == "No estimate")
        let notReady = DryRun(estimateReady: false, estimatedSessionCount: nil,
                              estimatedTokens: nil, estimatedDurationS: nil, warnings: nil)
        #expect(DryRunFormat.summaryLine(notReady) == "No estimate")
    }

    @Test("full estimate renders a compact line")
    func fullLine() {
        let dry = DryRun(estimateReady: true, estimatedSessionCount: 2,
                         estimatedTokens: 48000, estimatedDurationS: 320, warnings: [])
        let line = DryRunFormat.summaryLine(dry)
        #expect(line.contains("~2 terminals"))
        #expect(line.contains("48k tokens"))
        #expect(line.contains("5m"))
    }

    @Test("token + duration edge formatting")
    func edgeFormatting() {
        #expect(DryRunFormat.formatTokens(900) == "900")
        #expect(DryRunFormat.formatTokens(1500) == "1.5k")
        #expect(DryRunFormat.formatTokens(48000) == "48k")
        #expect(DryRunFormat.formatDuration(45) == "45s")
        #expect(DryRunFormat.formatDuration(320) == "5m")
    }
}

// MARK: - Error mapping (Addendum §A4)

@Suite("Conductor error mapping")
struct ConductorErrorTests {

    @Test("provider error is retriable with plain language")
    func providerError() {
        let apiError = APIError(code: .providerError, message: "529 overloaded", retriable: true, details: nil)
        let error = ConductorError(apiError: apiError)
        #expect(error.retriable)
        #expect(error.title == "Claude unavailable")
    }

    @Test("plan expired is not retriable")
    func planExpired() {
        let apiError = APIError(code: .planExpired, message: "expired", retriable: false, details: nil)
        let error = ConductorError(apiError: apiError)
        #expect(error.retriable == false)
        #expect(error.title == "Plan expired")
    }
}

// MARK: - Orb hue table (REQ-DSN-013)

@Suite("Orb hue table")
struct OrbHueTests {

    private func inRange(_ value: Double, _ low: Double, _ high: Double) -> Bool {
        value >= low && value <= high
    }

    @Test("each state's dominant hue is within the normative range")
    func hueRanges() {
        #expect(inRange(OrbHue.gradient(for: .idle).hueDegrees, 255, 290))
        #expect(inRange(OrbHue.gradient(for: .listening).hueDegrees, 200, 260))
        #expect(inRange(OrbHue.gradient(for: .thinking).hueDegrees, 280, 330))
        #expect(inRange(OrbHue.gradient(for: .spawning).hueDegrees, 160, 210))
        #expect(inRange(OrbHue.gradient(for: .streaming).hueDegrees, 140, 170))
        #expect(inRange(OrbHue.gradient(for: .error).hueDegrees, 15, 45))
    }
}

// MARK: - Orb render model (REQ-DSN-054 / REQ-DSN-057)

@Suite("Orb render model")
struct OrbRenderModelTests {

    @Test("diameter grows monotonically with amplitude")
    func diameterMonotonic() {
        let model = OrbRenderModel.model(for: .listening)
        let low = model.diameter(time: 0, amplitude: 0.1)
        let high = model.diameter(time: 0, amplitude: 0.9)
        #expect(high > low)
    }

    @Test("glow radius never decreases as amplitude increases (REQ-DSN-054)")
    func glowMonotonic() {
        let model = OrbRenderModel.model(for: .listening)
        let d: CGFloat = 80
        var previous: CGFloat = -1
        for step in 0...10 {
            let amp = Double(step) / 10
            let r = model.glowRadius(diameter: d, amplitude: amp)
            #expect(r >= previous)
            previous = r
        }
    }

    @Test("breathing stays within ±amplitude bounds (REQ-DSN-057)")
    func breathingBounds() {
        let model = OrbRenderModel.model(for: .idle)
        for step in 0...40 {
            let t = Double(step) * 0.25
            let d = model.diameter(time: t, amplitude: 0)
            #expect(d >= model.baseDiameter - model.breathingAmplitude - 0.001)
            #expect(d <= model.baseDiameter + model.breathingAmplitude + 0.001)
        }
    }
}

// MARK: - Transcript assembly (REQ-ARCH-032)

@Suite("Transcript assembly")
struct TranscriptAssemblyTests {

    private actor Collector {
        var partials: [String] = []
        var amps: [Double] = []
        func addPartial(_ s: String) { partials.append(s) }
        func addAmp(_ a: Double) { amps.append(a) }
    }

    private final class AtomicFlag: @unchecked Sendable {
        private let lock = NSLock()
        private var flag = false
        func set() { lock.lock(); flag = true; lock.unlock() }
        var value: Bool { lock.lock(); defer { lock.unlock() }; return flag }
    }

    @Test("stub transcriber streams partials and returns the final")
    func stubStreaming() async {
        let stub = StubTranscriber(finalText: "run the tests", partials: ["run", "run the", "run the tests"])
        let ready = AtomicFlag()
        await stub.prepareModel { if $0.isReady { ready.set() } }
        #expect(ready.value)

        let collector = Collector()
        try? await stub.startLiveTranscription(
            onPartial: { text in Task { await collector.addPartial(text) } },
            onAmplitude: { amp in Task { await collector.addAmp(amp) } }
        )
        try? await Task.sleep(for: .milliseconds(700))
        let final = await stub.stopLiveTranscription()

        #expect(final == "run the tests")
        let partials = await collector.partials
        #expect(partials.contains("run the tests"))
        let amps = await collector.amps
        #expect(amps.isEmpty == false)
    }
}
