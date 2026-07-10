import Testing
import Foundation
@testable import Archon

/// Decode smoke tests against the FROZEN contract JSON shapes (API_CONTRACT_V3).
@Suite("Model decoding")
struct ModelDecodingTests {

    private func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        try ArchonJSON.decode(T.self, from: Data(json.utf8))
    }

    @Test("Session object (§2.3)")
    func sessionDecodes() throws {
        let json = """
        {
          "session_id": "01J8Z",
          "state": "running",
          "status": "running",
          "provider": "claude_code",
          "cwd": "/Users/mara/subralabs-v2/packages/api",
          "card_id": "01J8Y",
          "initiator": "conductor",
          "request_id": "01J8X",
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
        }
        """
        let session = try decode(Session.self, json)
        #expect(session.sessionId == "01J8Z")
        #expect(session.state == .running)
        #expect(session.status == .running)
        #expect(session.initiator == .conductor)
        #expect(session.pid == 90233)
        #expect(session.lastOutputSeq == 4821)
        #expect(session.elapsedS == 97.4)
        #expect(session.endedAt == nil)
        #expect(session.idleFlagged == false)
    }

    @Test("Sessions list with cap regime (§2.3)")
    func sessionsListDecodes() throws {
        let json = """
        { "sessions": [], "count": 0, "ceiling": 8, "cap": { "regime": "user", "value": 2 } }
        """
        let list = try decode(SessionsListResponse.self, json)
        #expect(list.ceiling == 8)
        #expect(list.cap.regime == .user)
        #expect(list.cap.value == 2)
    }

    @Test("Card object (§2.5)")
    func cardDecodes() throws {
        let json = """
        {
          "card_id": "01J8Y",
          "title": "Refactor checkout flow",
          "body": "Extract the payment adapter...",
          "column": "in_progress",
          "ordinal": 0,
          "priority": "high",
          "provenance": "conductor",
          "session_id": "01J8Z",
          "status": "running",
          "revision": 3,
          "created_at": "2026-07-10T14:03:25.400Z",
          "updated_at": "2026-07-10T14:05:10.220Z"
        }
        """
        let card = try decode(Card.self, json)
        #expect(card.column == .inProgress)
        #expect(card.priority == .high)
        #expect(card.provenance == .conductor)
        #expect(card.revision == 3)
    }

    @Test("Health + capabilities (§2.1)")
    func healthDecodes() throws {
        let json = """
        {
          "status": "ok", "pv": 1, "orchestrator_version": "3.0.0",
          "project_id": "9f2c", "uptime_s": 412.8, "provider_ready": true,
          "conductor_state": "idle", "session_count": 2,
          "capabilities": {
            "stream_transport": "websocket", "replay_events": 2000,
            "replay_window_s": 60, "hard_ceiling": 8,
            "supported_provider": "claude_code",
            "memory_kinds": ["CLAUDE.md", "AGENTS.md", "overlay"],
            "dry_run_max_s": 1.5
          }
        }
        """
        let health = try decode(HealthResponse.self, json)
        #expect(health.status == .ok)
        #expect(health.pv == 1)
        #expect(health.capabilities.hardCeiling == 8)
        #expect(health.capabilities.memoryKinds.count == 3)
        #expect(health.conductorState == .idle)
    }

    @Test("Conductor message → plan + dry-run (§2.4)")
    func planDecodes() throws {
        let json = """
        {
          "intent_id": "01J8W",
          "plan": {
            "plan_id": "01J8V", "summary": "Two terminals.",
            "proposed_session_count": 2, "applied_cap": 4, "ceiling": 8,
            "final_count": 2, "reduction_reason": null,
            "actions": [
              { "action_id": "01J8V1", "kind": "spawn_session",
                "cwd": "/p", "prompt": "Refactor...", "card_ref": "new:refactor",
                "rationale": "primary", "destructive": false },
              { "action_id": "01J8V2", "kind": "create_card",
                "column": "in_progress", "title": "Refactor", "destructive": false }
            ]
          },
          "dry_run": {
            "estimate_ready": true, "estimated_session_count": 2,
            "estimated_tokens": 48000, "estimated_duration_s": 320, "warnings": []
          },
          "expires_at": "2026-07-10T14:08:25.000Z"
        }
        """
        let response = try decode(ConductorMessageResponse.self, json)
        #expect(response.plan.actions.count == 2)
        #expect(response.plan.actions[0].kind == .spawnSession)
        #expect(response.plan.actions[1].kind == .createCard)
        #expect(response.plan.actions[1].column == .inProgress)
        #expect(response.dryRun.estimateReady == true)
        #expect(response.dryRun.estimatedTokens == 48000)
    }

    @Test("Memory file list (§2.6)")
    func memoryListDecodes() throws {
        let json = """
        { "scopes": [ { "scope_dir": "/p", "files": [
          { "scope_dir": "/p", "filename": "CLAUDE.md", "kind": "CLAUDE.md",
            "location": "project", "size": 2048, "mtime": "2026-07-09T18:11:02.000Z",
            "owner": "user", "revision": 4, "checksum": "sha256:1a2b", "editable": true }
        ] } ] }
        """
        let list = try decode(MemoryListResponse.self, json)
        #expect(list.scopes.count == 1)
        let file = try #require(list.scopes.first?.files.first)
        #expect(file.kind == .claude)
        #expect(file.location == .project)
        #expect(file.owner == .user)
        #expect(file.editable)
    }

    @Test("Error envelope + code registry (§1.6)")
    func errorEnvelopeDecodes() throws {
        let json = """
        { "error": { "code": "revision_conflict",
          "message": "stale", "retriable": false,
          "details": { "card_id": "01J", "expected_revision": 9 } } }
        """
        let envelope = try decode(APIErrorEnvelope.self, json)
        #expect(envelope.error.code == .revisionConflict)
        #expect(envelope.error.retriable == false)
        #expect(envelope.error.details?["expected_revision"] == .number(9))
    }

    @Test("Unknown enum values fall back, not throw (additive tolerance)")
    func unknownEnumFallsBack() throws {
        let json = """
        { "code": "some_future_code", "message": "x", "retriable": true }
        """
        let error = try decode(APIError.self, json)
        #expect(error.code == .unknown)
    }
}
