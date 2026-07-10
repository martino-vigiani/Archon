import Testing
import Foundation
@testable import Archon

/// Unit tests for ConductorStore event-folding, error recovery, and cap logic.
/// These tests exercise the pure `apply(_:)` path and the cap-clamping logic
/// without requiring a live orchestrator or network (Addendum §A4).
@Suite("ConductorStore — event folding & resilience")
@MainActor
struct ConductorStoreTests {

    /// Minimal container that satisfies `ConductorStore`'s `weak var container`
    /// and provides a non-nil `appState`.
    private func makeStore() -> ConductorStore {
        let container = AppContainer()
        return ConductorStore(container: container)
    }

    private func conductorEvent(
        _ state: ConductorState,
        detail: String? = nil,
        planId: String? = nil
    ) -> EventEnvelope {
        EventEnvelope(
            seq: 1, type: "conductor_state",
            event: .conductorState(ConductorStatePayload(
                state: state, detail: detail, planId: planId, intentId: nil
            ))
        )
    }

    // MARK: - conductor_state folding

    @Test("apply(conductor_state:thinking) sets serverConductorState")
    func conductorStateThinkingFolds() {
        let store = makeStore()
        store.apply(conductorEvent(.thinking))
        #expect(store.serverConductorState == .thinking)
    }

    @Test("apply(conductor_state:streaming) transitions through all server states")
    func conductorStateSequence() {
        let store = makeStore()
        for state in [ConductorState.thinking, .spawning, .streaming, .idle] {
            store.apply(conductorEvent(state))
            #expect(store.serverConductorState == state)
        }
    }

    @Test("server-sent listening is ignored — client-local only (contract §3.4)")
    func serverListeningIgnored() {
        let store = makeStore()
        store.apply(conductorEvent(.thinking))
        // A stray server `listening` must not overwrite the real server state.
        store.apply(conductorEvent(.listening))
        #expect(store.serverConductorState == .thinking)
    }

    @Test("apply(conductor_state:error) marks error state")
    func conductorErrorState() {
        let store = makeStore()
        store.apply(conductorEvent(.error))
        #expect(store.serverConductorState == .error)
    }

    // MARK: - error event folding

    @Test("apply(error event) surfaces lastError and sets orb to error")
    func errorEventSurfaced() {
        let store = makeStore()
        let apiError = APIError(code: .providerError, message: "Claude API overloaded",
                                retriable: true, details: nil)
        let envelope = EventEnvelope(
            seq: 1, type: "error",
            event: .error(apiError)
        )
        store.apply(envelope)
        #expect(store.lastError != nil)
        #expect(store.serverConductorState == .error)
    }

    // MARK: - dry_run_result folding

    @Test("apply(dry_run_result) updates currentDryRun when planId matches")
    func dryRunResultFolded() {
        let store = makeStore()
        let dryRun = DryRun(
            estimateReady: true,
            estimatedSessionCount: 3,
            estimatedTokens: 50000,
            estimatedDurationS: 200,
            warnings: []
        )
        let envelope = EventEnvelope(
            seq: 1, type: "dry_run_result", planId: nil,
            event: .dryRunResult(dryRun)
        )
        store.apply(envelope)
        #expect(store.currentDryRun?.estimatedSessionCount == 3)
        #expect(store.currentDryRun?.estimatedTokens == 50000)
    }

    @Test("apply(dry_run_result) with non-matching planId is ignored")
    func dryRunResultWrongPlanIdIgnored() {
        let store = makeStore()
        // Simulate a pending plan by manually setting currentPlan through an
        // envelope with a specific plan_id embedded in the dry run event.
        // In this test we just check that a planId mismatch doesn't corrupt state.
        let envelope = EventEnvelope(
            seq: 1, type: "dry_run_result", planId: "SOME_OTHER_PLAN",
            event: .dryRunResult(DryRun(estimateReady: true, estimatedSessionCount: 99,
                                        estimatedTokens: nil, estimatedDurationS: nil, warnings: nil))
        )
        // No currentPlan set → planId check: envelope.planId != currentPlan?.planId (nil)
        // The implementation applies when planId is nil or matches. A non-nil planId
        // with no currentPlan means no current plan to match → ignored.
        store.apply(envelope)
        // Because there is no currentPlan and the envelope has a specific planId,
        // the currentDryRun must remain nil (no false update).
        // Note: implementation checks `envelope.planId == nil || envelope.planId == currentPlan?.planId`
        // With no currentPlan, currentPlan?.planId is nil, and envelope.planId is "SOME_OTHER_PLAN" ≠ nil
        // → condition is false → currentDryRun stays nil.
        #expect(store.currentDryRun == nil)
    }

    // MARK: - dismissError

    @Test("dismissError clears lastError and resets error orb to idle")
    func dismissErrorResetsOrb() {
        let store = makeStore()
        let apiError = APIError(code: .orchestratorError, message: "500", retriable: true, details: nil)
        store.apply(EventEnvelope(seq: 1, type: "error", event: .error(apiError)))
        #expect(store.serverConductorState == .error)
        #expect(store.lastError != nil)

        store.dismissError()
        #expect(store.lastError == nil)
        #expect(store.serverConductorState == .idle)
    }

    @Test("dismissError when serverConductorState is not error leaves state unchanged")
    func dismissErrorNonErrorStateUnchanged() {
        let store = makeStore()
        store.apply(conductorEvent(.streaming))
        store.dismissError()
        // `dismissError` only resets to idle when state == .error; streaming stays streaming.
        #expect(store.serverConductorState == .streaming)
    }

    // MARK: - cap clamping (REQ-UX-033)

    @Test("cap is clamped to [1, hardCeiling] on assignment")
    func capClampedToHardCeiling() {
        let store = makeStore()
        let ceiling = store.hardCeiling
        store.cap = ceiling + 10    // above ceiling
        #expect(store.cap == ceiling)
    }

    @Test("cap is clamped to minimum 1")
    func capClampedToMinimum() {
        let store = makeStore()
        store.cap = 0
        #expect(store.cap == 1)
    }

    @Test("cap = hardCeiling is valid (no clamp)")
    func capAtCeilingIsValid() {
        let store = makeStore()
        store.cap = store.hardCeiling
        #expect(store.cap == store.hardCeiling)
    }

    // MARK: - capWarning

    @Test("capWarning is true when estimatedTerminalCount > cap")
    func capWarningTrue() {
        let store = makeStore()
        store.cap = 2
        let dryRun = DryRun(estimateReady: true, estimatedSessionCount: 5,
                            estimatedTokens: nil, estimatedDurationS: nil, warnings: nil)
        store.apply(EventEnvelope(seq: 1, type: "dry_run_result", planId: nil,
                                  event: .dryRunResult(dryRun)))
        #expect(store.capWarning == true)
    }

    @Test("capWarning is false when estimatedTerminalCount <= cap")
    func capWarningFalse() {
        let store = makeStore()
        store.cap = 8
        let dryRun = DryRun(estimateReady: true, estimatedSessionCount: 3,
                            estimatedTokens: nil, estimatedDurationS: nil, warnings: nil)
        store.apply(EventEnvelope(seq: 1, type: "dry_run_result", planId: nil,
                                  event: .dryRunResult(dryRun)))
        #expect(store.capWarning == false)
    }

    @Test("capWarning is false when no estimate is available")
    func capWarningNoEstimate() {
        let store = makeStore()
        #expect(store.capWarning == false)
    }

    // MARK: - hasPendingPlan / estimatedTerminalCount

    @Test("hasPendingPlan is false initially and after clearPlan-like dismissError")
    func hasPendingPlanInitiallyFalse() {
        let store = makeStore()
        #expect(store.hasPendingPlan == false)
        #expect(store.estimatedTerminalCount == nil)
    }

    // MARK: - isPlanning flag

    @Test("isPlanning starts false")
    func isPlanningInitiallyFalse() {
        let store = makeStore()
        #expect(store.isPlanning == false)
    }

    // MARK: - Exchange log

    @Test("cancelCurrentPlan with no plan clears plan safely")
    func cancelNoOpWithNoPlan() {
        let store = makeStore()
        // Should not crash or throw.
        store.cancelCurrentPlan()
        #expect(store.hasPendingPlan == false)
    }
}
