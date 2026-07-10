import Testing
import Foundation
@testable import Archon

/// Verbatim JSON fixture tests — every JSON example from API_CONTRACT_V3.md
/// decoded against the frozen Swift models. If a model changes shape and
/// breaks an example the contract defines, this suite catches it immediately.
@Suite("Contract conformance — verbatim JSON fixtures (API_CONTRACT_V3.md)")
struct ContractConformanceTests {

    private func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        try ArchonJSON.decode(T.self, from: Data(json.utf8))
    }

    // MARK: - §2.2 Project info

    @Test("Project info (§2.2) — all required fields decode")
    func projectInfoDecodes() throws {
        let json = """
        {
          "project_id": "9f2c1a2b3c4d5e6f7890abcdef1234567890abcdef1234567890abcdef123456",
          "path": "/Users/mara/subralabs-v2",
          "name": "subralabs-v2",
          "provider": "claude_code",
          "opened_at": "2026-07-10T14:03:20.001Z",
          "git": { "is_repo": true, "branch": "main", "head": "a1b2c3d", "dirty": false },
          "state_dir": "~/Library/Application Support/Archon/projects/9f2c.../"
        }
        """
        let info = try decode(ProjectInfo.self, json)
        #expect(info.projectId.count == 64)
        #expect(info.name == "subralabs-v2")
        #expect(info.provider == "claude_code")
        #expect(info.git?.isRepo == true)
        #expect(info.git?.branch == "main")
    }

    // MARK: - §2.3 Kill session response

    @Test("Kill session response (§2.3) decodes")
    func killSessionResponseDecodes() throws {
        let json = """
        { "session_id": "01J8Z...", "state": "killed", "accepted": true }
        """
        let r = try decode(KillSessionResponse.self, json)
        #expect(r.sessionId == "01J8Z...")
        #expect(r.accepted == true)
        #expect(r.state == .killed)
    }

    // MARK: - §2.3 Sessions list with auto regime + null value

    @Test("Sessions list auto regime with null value (§2.3)")
    func sessionsListAutoRegimeNullValue() throws {
        let json = """
        { "sessions": [], "count": 0, "ceiling": 8, "cap": { "regime": "auto", "value": null } }
        """
        let list = try decode(SessionsListResponse.self, json)
        #expect(list.cap.regime == .auto)
        #expect(list.cap.value == nil)
        #expect(list.ceiling == 8)
    }

    // MARK: - §2.3 Session exit_reason values

    @Test("All exit_reason enum values decode (§2.3)")
    func exitReasonDecodes() throws {
        let cases: [(String, ExitReason)] = [
            ("normal", .normal),
            ("killed", .killed),
            ("crash_recovery", .crashRecovery),
            ("resource_exceeded", .resourceExceeded),
            ("spawn_failed", .spawnFailed),
        ]
        for (raw, expected) in cases {
            let json = """
            { "state": "completed", "status": "done",
              "exit_code": 0, "exit_reason": "\(raw)",
              "idle_flagged": false, "last_activity_at": "2026-07-10T14:07:41.100Z",
              "elapsed_s": 1.0 }
            """
            let p = try decode(SessionStatePayload.self, json)
            #expect(p.exitReason == expected, "exit_reason '\(raw)' did not decode to \(expected)")
        }
    }

    // MARK: - §2.4 Conductor confirm response

    @Test("Conductor confirm response (§2.4) decodes")
    func confirmPlanResponseDecodes() throws {
        let json = """
        {
          "plan_id": "01J8V...",
          "status": "executing",
          "created_session_ids": ["01J8Z..."],
          "created_card_ids": ["01J8Y..."],
          "applied_cap": 2,
          "final_count": 2
        }
        """
        let r = try decode(ConfirmPlanResponse.self, json)
        #expect(r.planId == "01J8V...")
        #expect(r.status == .executing)
        #expect(r.createdSessionIds?.count == 1)
        #expect(r.createdCardIds?.count == 1)
        #expect(r.appliedCap == 2)
        #expect(r.finalCount == 2)
    }

    @Test("Conductor confirm partial status decodes")
    func confirmPlanPartialDecodes() throws {
        let json = """
        {
          "plan_id": "01J8V...",
          "status": "partial",
          "created_session_ids": [],
          "created_card_ids": [],
          "applied_cap": 2,
          "final_count": 0,
          "action_results": [
            { "action_id": "01J8V1", "ok": false,
              "error": { "code": "cap_exceeded", "message": "session cap reached", "retriable": false } }
          ]
        }
        """
        let r = try decode(ConfirmPlanResponse.self, json)
        #expect(r.status == .partial)
    }

    // MARK: - §1.6 Error code registry

    @Test("All error codes from §1.6 decode (no unknown fallback)")
    func allErrorCodesDecodeExactly() throws {
        let errorCodes: [String] = [
            "unauthorized", "forbidden", "incompatible_version", "not_found",
            "validation_error", "revision_conflict", "cap_exceeded",
            "ceiling_reached", "illegal_transition", "memory_write_denied",
            "conductor_write_forbidden", "memory_too_large", "memory_quota_exceeded",
            "path_escape", "plan_expired", "session_not_found", "rate_limited",
            "orchestrator_error", "provider_error",
        ]
        for code in errorCodes {
            let json = """
            { "code": "\(code)", "message": "test", "retriable": false }
            """
            let err = try decode(APIError.self, json)
            #expect(err.code != .unknown, "error code '\(code)' fell back to .unknown")
        }
    }

    @Test("retriable flag correctly decoded for known codes")
    func retriableFlagDecoded() throws {
        // rate_limited and orchestrator_error are retriable per §1.6
        for (code, expected) in [("rate_limited", true), ("unauthorized", false), ("orchestrator_error", true)] {
            let json = """
            { "code": "\(code)", "message": "x", "retriable": \(expected) }
            """
            let err = try decode(APIError.self, json)
            #expect(err.retriable == expected, "retriable mismatch for \(code)")
        }
    }

    // MARK: - §3.4 hello with truncated: true

    @Test("hello frame with truncated=true sets flag (§3.3 resume truncation notice)")
    func helloTruncatedDecodes() throws {
        let json = """
        { "v":1, "seq":4820, "ts":"2026-07-10T14:05:02.900Z", "type":"hello",
          "payload": { "pv":1, "orchestrator_version":"3.0.0", "current_seq":4820,
            "replay_window_events":2000, "replay_window_s":60,
            "resume_supported":true, "conductor_state":"streaming",
            "truncated": true } }
        """
        let env = try decode(EventEnvelope.self, json)
        guard case .hello(let hello) = env.event else {
            Issue.record("expected hello, got \(env.event)")
            return
        }
        #expect(hello.truncated == true)
        #expect(hello.pv == 1)
        #expect(hello.currentSeq == 4820)
    }

    @Test("hello frame without truncated field (truncated=nil, normal reconnect)")
    func helloNoTruncatedField() throws {
        let json = """
        { "v":1, "seq":1, "ts":"2026-07-10T14:05:02.900Z", "type":"hello",
          "payload": { "pv":1, "current_seq":1,
            "replay_window_events":2000, "replay_window_s":60,
            "resume_supported":true } }
        """
        let env = try decode(EventEnvelope.self, json)
        guard case .hello(let hello) = env.event else { Issue.record("not hello"); return }
        #expect(hello.truncated == nil)
    }

    // MARK: - §3.4 memory_changed event

    @Test("memory_changed event verbatim (§3.4)")
    func memoryChangedDecodes() throws {
        let json = """
        { "v":1, "seq":4870, "ts":"2026-07-10T14:05:02.900Z", "type":"memory_changed",
          "payload": {
            "scope_dir": "/Users/mara/subralabs-v2/packages/api",
            "filename": "CLAUDE.md",
            "kind": "CLAUDE.md",
            "op": "updated",
            "revision": 5,
            "checksum": "sha256:9c8d...",
            "initiator": "user"
          } }
        """
        let env = try decode(EventEnvelope.self, json)
        guard case .memoryChanged(let p) = env.event else {
            Issue.record("expected memory_changed, got \(env.event)")
            return
        }
        #expect(p.scopeDir == "/Users/mara/subralabs-v2/packages/api")
        #expect(p.filename == "CLAUDE.md")
        #expect(p.kind == .claude)
        #expect(p.op == .updated)
        #expect(p.revision == 5)
        #expect(p.initiator == .user)
    }

    @Test("memory_changed deleted op decodes")
    func memoryChangedDeletedDecodes() throws {
        let json = """
        { "v":1, "seq":100, "ts":"2026-07-10T14:05:02.900Z", "type":"memory_changed",
          "payload": {
            "scope_dir": "/p",
            "filename": "AGENTS.md",
            "kind": "AGENTS.md",
            "op": "deleted",
            "revision": 2,
            "initiator": "user"
          } }
        """
        let env = try decode(EventEnvelope.self, json)
        guard case .memoryChanged(let p) = env.event else { Issue.record("not memory_changed"); return }
        #expect(p.op == .deleted)
        #expect(p.kind == .agents)
    }

    // MARK: - §3.4 dry_run_result event

    @Test("dry_run_result event verbatim (§3.4)")
    func dryRunResultDecodes() throws {
        let json = """
        { "v":1, "seq":4824, "ts":"2026-07-10T14:05:02.900Z", "type":"dry_run_result",
          "plan_id":"01J8V...",
          "payload": {
            "estimate_ready": true,
            "estimated_session_count": 2,
            "estimated_tokens": 48000,
            "estimated_duration_s": 320,
            "warnings": []
          } }
        """
        let env = try decode(EventEnvelope.self, json)
        #expect(env.planId == "01J8V...")
        guard case .dryRunResult(let dr) = env.event else {
            Issue.record("expected dry_run_result, got \(env.event)")
            return
        }
        #expect(dr.estimateReady == true)
        #expect(dr.estimatedSessionCount == 2)
        #expect(dr.estimatedTokens == 48000)
        #expect(dr.estimatedDurationS == 320)
    }

    @Test("dry_run_result with estimate_ready=false and null figures")
    func dryRunResultNotReadyDecodes() throws {
        let json = """
        { "v":1, "seq":1, "ts":"2026-07-10T14:05:02.900Z", "type":"dry_run_result",
          "payload": {
            "estimate_ready": false,
            "estimated_session_count": null,
            "estimated_tokens": null,
            "estimated_duration_s": null,
            "warnings": ["Estimate still pending"]
          } }
        """
        let env = try decode(EventEnvelope.self, json)
        guard case .dryRunResult(let dr) = env.event else { Issue.record("not dry_run_result"); return }
        #expect(dr.estimateReady == false)
        #expect(dr.estimatedTokens == nil)
    }

    // MARK: - §3.4 session_spawned event verbatim

    @Test("session_spawned event verbatim (§3.4)")
    func sessionSpawnedDecodes() throws {
        let json = """
        { "v":1, "seq":4822, "ts":"2026-07-10T14:05:02.900Z", "type":"session_spawned",
          "session_id":"01J8Z...",
          "payload": { "session": {
            "session_id": "01J8Z...",
            "state": "running",
            "status": "running",
            "provider": "claude_code",
            "cwd": "/Users/mara/subralabs-v2/packages/api",
            "card_id": "01J8Y...",
            "initiator": "conductor",
            "request_id": "01J8X...",
            "pid": 90233,
            "created_at": "2026-07-10T14:03:25.100Z",
            "started_at": "2026-07-10T14:03:25.412Z",
            "ended_at": null,
            "exit_code": null,
            "exit_reason": null,
            "idle_flagged": false,
            "last_activity_at": "2026-07-10T14:05:02.900Z",
            "last_output_seq": 4821,
            "elapsed_s": 97.4
          } } }
        """
        let env = try decode(EventEnvelope.self, json)
        #expect(env.sessionId == "01J8Z...")
        guard case .sessionSpawned(let p) = env.event else {
            Issue.record("expected session_spawned, got \(env.event)")
            return
        }
        #expect(p.session.sessionId == "01J8Z...")
        #expect(p.session.state == .running)
        #expect(p.session.initiator == .conductor)
        #expect(p.session.pid == 90233)
        #expect(p.session.lastOutputSeq == 4821)
    }

    // MARK: - §3.4 kanban_updated snapshot op

    @Test("kanban_updated snapshot op decodes (§3.4)")
    func kanbanSnapshotOpDecodes() throws {
        let json = """
        { "v":1, "seq":100, "ts":"2026-07-10T14:05:02.900Z", "type":"kanban_updated",
          "payload": {
            "op": "snapshot",
            "cards": [
              { "card_id":"01J8Y", "title":"T", "column":"queued",
                "ordinal":0, "priority":"normal", "provenance":"user",
                "status":"idle", "revision":1,
                "created_at":"2026-07-10T14:03:25.400Z",
                "updated_at":"2026-07-10T14:05:10.220Z" }
            ],
            "board_revision": 40
          } }
        """
        let env = try decode(EventEnvelope.self, json)
        guard case .kanbanUpdated(let p) = env.event else {
            Issue.record("expected kanban_updated, got \(env.event)")
            return
        }
        #expect(p.op == .snapshot)
        #expect(p.cards?.count == 1)
        #expect(p.cards?.first?.cardId == "01J8Y")
        #expect(p.boardRevision == 40)
    }

    // MARK: - §1.2 RuntimeHandshake edge cases

    @Test("RuntimeHandshake decodes all required §1.2 fields")
    func runtimeHandshakeDecodes() throws {
        let json = """
        {
          "pv": 1,
          "port": 51423,
          "pid": 88412,
          "token": "b6f1c0d9e2a74f3d8a1e2c7f4b9d0e5a8c3f6a2d9b4e7f0c1a5d8b2e6f3a9c4b",
          "project_id": "9f2c1a2b3c4d5e6f7890abcdef1234567890abcdef1234567890abcdef123456",
          "project_path": "/Users/mara/subralabs-v2",
          "started_at": "2026-07-10T14:03:22.481Z"
        }
        """
        let h = try decode(RuntimeHandshake.self, json)
        #expect(h.pv == 1)
        #expect(h.port == 51423)
        #expect(h.pid == 88412)
        #expect(h.token.count == 64)
    }

    @Test("RuntimeHandshake with pv=2 decodes but must be rejected by supervisor")
    func runtimeHandshakeWrongPv() throws {
        let json = """
        {
          "pv": 2,
          "port": 51423,
          "pid": 99999,
          "token": "aaaaaaaabbbbbbbbccccccccddddddddeeeeeeeeffffffffaaaaaaaabbbbbbbb",
          "project_id": "dead",
          "project_path": "/tmp/proj",
          "started_at": "2026-07-10T14:03:22.481Z"
        }
        """
        let h = try decode(RuntimeHandshake.self, json)
        // Decodes cleanly…
        #expect(h.pv == 2)
        // …but the supervisor must reject pv != 1 → .incompatible.
        // The client's `launchAndConnect` checks `handshake.pv == 1`.
        #expect(h.pv != 1)
    }

    // MARK: - §2.5 Card object — all fields

    @Test("Card object with all §2.5 fields (session_id, body, priority, status)")
    func cardAllFieldsDecodes() throws {
        let json = """
        {
          "card_id": "01J8Y...",
          "title": "Refactor checkout flow",
          "body": "Extract the payment adapter...",
          "column": "in_progress",
          "ordinal": 0,
          "priority": "high",
          "provenance": "conductor",
          "session_id": "01J8Z...",
          "status": "running",
          "revision": 3,
          "created_at": "2026-07-10T14:03:25.400Z",
          "updated_at": "2026-07-10T14:05:10.220Z"
        }
        """
        let card = try decode(Card.self, json)
        #expect(card.sessionId == "01J8Z...")
        #expect(card.body == "Extract the payment adapter...")
        #expect(card.priority == .high)
        #expect(card.status == .running)
    }

    // MARK: - §2.6 Memory file — all fields

    @Test("Memory file object with all §2.6 fields decodes")
    func memoryFileAllFieldsDecodes() throws {
        let json = """
        {
          "scope_dir": "/Users/mara/subralabs-v2/packages/api",
          "filename": "CLAUDE.md",
          "kind": "CLAUDE.md",
          "location": "project",
          "size": 2048,
          "mtime": "2026-07-09T18:11:02.000Z",
          "owner": "user",
          "revision": 4,
          "checksum": "sha256:1a2b3c4d",
          "editable": true
        }
        """
        let f = try decode(MemoryFile.self, json)
        #expect(f.scopeDir == "/Users/mara/subralabs-v2/packages/api")
        #expect(f.kind == .claude)
        #expect(f.location == .project)
        #expect(f.size == 2048)
        #expect(f.owner == .user)
        #expect(f.revision == 4)
        #expect(f.checksum == "sha256:1a2b3c4d")
        #expect(f.editable == true)
    }

    @Test("Memory file with overlay location decodes")
    func memoryFileOverlayDecodes() throws {
        let json = """
        {
          "scope_dir": "/Users/mara/subralabs-v2",
          "filename": "NOTES.md",
          "kind": "overlay",
          "location": "overlay",
          "size": 512,
          "mtime": "2026-07-09T18:11:02.000Z",
          "owner": "user",
          "revision": 1,
          "checksum": "sha256:abcd",
          "editable": true
        }
        """
        let f = try decode(MemoryFile.self, json)
        #expect(f.kind == .overlay)
        #expect(f.location == .overlay)
    }
}
