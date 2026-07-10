import Testing
import Foundation
@testable import Archon

/// Decode smoke tests for the WebSocket event envelope (contract §3).
@Suite("Event decoding")
struct EventDecodingTests {

    private func decodeEnvelope(_ json: String) throws -> EventEnvelope {
        try ArchonJSON.decode(EventEnvelope.self, from: Data(json.utf8))
    }

    @Test("hello frame + version fields")
    func helloDecodes() throws {
        let json = """
        { "v":1, "seq":4820, "ts":"2026-07-10T14:05:02.900Z", "type":"hello",
          "payload": { "pv":1, "orchestrator_version":"3.0.0", "current_seq":4820,
            "replay_window_events":2000, "replay_window_s":60,
            "resume_supported":true, "conductor_state":"streaming" } }
        """
        let env = try decodeEnvelope(json)
        #expect(env.seq == 4820)
        guard case .hello(let hello) = env.event else { Issue.record("not hello"); return }
        #expect(hello.pv == 1)
        #expect(hello.currentSeq == 4820)
        #expect(hello.conductorState == .streaming)
    }

    @Test("session_state lifecycle transition")
    func sessionStateDecodes() throws {
        let json = """
        { "v":1, "seq":4901, "ts":"2026-07-10T14:07:41.100Z", "type":"session_state",
          "session_id":"01J8Z",
          "payload": { "state":"completed", "status":"done", "exit_code":0,
            "exit_reason":"normal", "idle_flagged":false,
            "last_activity_at":"2026-07-10T14:07:41.100Z", "elapsed_s":421.0 } }
        """
        let env = try decodeEnvelope(json)
        #expect(env.sessionId == "01J8Z")
        guard case .sessionState(let p) = env.event else { Issue.record("not session_state"); return }
        #expect(p.state == .completed)
        #expect(p.status == .done)
        #expect(p.exitReason == .normal)
        #expect(p.elapsedS == 421.0)
    }

    @Test("pty_output base64 decodes to raw bytes")
    func ptyOutputDecodes() throws {
        let raw = "\u{1B}[0mHello world"
        let b64 = Data(raw.utf8).base64EncodedString()
        let json = """
        { "v":1, "seq":4830, "ts":"2026-07-10T14:05:02.900Z", "type":"pty_output",
          "session_id":"01J8Z",
          "payload": { "stream_seq":512, "encoding":"base64", "bytes":"\(b64)",
            "dropped":false, "dropped_bytes":0 } }
        """
        let env = try decodeEnvelope(json)
        guard case .ptyOutput(let p) = env.event else { Issue.record("not pty_output"); return }
        #expect(p.streamSeq == 512)
        #expect(p.dropped == false)
        let data = try #require(p.data)
        #expect(String(decoding: data, as: UTF8.self) == raw)
    }

    @Test("kanban_updated moved event")
    func kanbanMovedDecodes() throws {
        let json = """
        { "v":1, "seq":4850, "ts":"2026-07-10T14:05:02.900Z", "type":"kanban_updated",
          "task_id":"01J8Y",
          "payload": { "op":"moved",
            "card": { "card_id":"01J8Y", "title":"t", "column":"in_progress",
              "ordinal":0, "priority":"normal", "provenance":"user",
              "status":"running", "revision":4,
              "created_at":"2026-07-10T14:03:25.400Z",
              "updated_at":"2026-07-10T14:05:10.220Z" },
            "from": { "column":"queued", "ordinal":2 },
            "to": { "column":"in_progress", "ordinal":0 },
            "board_revision":58 } }
        """
        let env = try decodeEnvelope(json)
        #expect(env.taskId == "01J8Y")
        guard case .kanbanUpdated(let p) = env.event else { Issue.record("not kanban_updated"); return }
        #expect(p.op == .moved)
        #expect(p.boardRevision == 58)
        #expect(p.card?.column == .inProgress)
        #expect(p.from?.column == .queued)
    }

    @Test("conductor_state six-state")
    func conductorStateDecodes() throws {
        let json = """
        { "v":1, "seq":4823, "ts":"2026-07-10T14:05:02.900Z", "type":"conductor_state",
          "payload": { "state":"thinking", "detail":"Planning...",
            "plan_id":"01J8V", "intent_id":"01J8W" } }
        """
        let env = try decodeEnvelope(json)
        guard case .conductorState(let p) = env.event else { Issue.record("not conductor_state"); return }
        #expect(p.state == .thinking)
        #expect(p.planId == "01J8V")
    }

    @Test("error frame")
    func errorFrameDecodes() throws {
        let json = """
        { "v":1, "seq":4999, "ts":"2026-07-10T14:05:02.900Z", "type":"error",
          "session_id":"01J8Z",
          "payload": { "error": { "code":"provider_error",
            "message":"overloaded", "retriable":true, "details": { "attempt":1 } } } }
        """
        let env = try decodeEnvelope(json)
        guard case .error(let error) = env.event else { Issue.record("not error"); return }
        #expect(error.code == .providerError)
        #expect(error.retriable)
    }

    @Test("unknown event type does not throw (REQ-ARCH-006)")
    func unknownTypeIgnored() throws {
        let json = """
        { "v":1, "seq":5000, "ts":"2026-07-10T14:05:02.900Z", "type":"future_event",
          "payload": { "anything": 1 } }
        """
        let env = try decodeEnvelope(json)
        guard case .unknown(let type) = env.event else { Issue.record("expected unknown"); return }
        #expect(type == "future_event")
    }

    @Test("control frames encode to wire JSON (§3.3)")
    func controlFramesEncode() throws {
        let resume = try ClientControlFrame.resume(afterSeq: 4700).jsonText()
        #expect(resume.contains("\"type\":\"resume\""))
        #expect(resume.contains("\"after_seq\":4700"))

        let sub = try ClientControlFrame.subscribe(topics: [.kanban, .ptyOutput]).jsonText()
        #expect(sub.contains("\"subscribe\""))
        #expect(sub.contains("pty_output"))
    }
}
