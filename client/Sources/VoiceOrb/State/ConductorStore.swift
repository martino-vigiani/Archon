import Foundation
import Observation

/// Owns the Conductor exchange: intent → plan → confirm/cancel, dry-run
/// estimate, the exchange log, and resilience (Addendum §A4). `@Observable
/// @MainActor`, fed by `APIClient` (via the container) and the WS event stream
/// (folded in by the coordinator through `apply(_:)`).
///
/// The client holds no provider key (REQ-ARCH-040) — every Claude call goes
/// through the loopback orchestrator. Memory proposals are surfaced for review,
/// never auto-applied (Addendum §A3).
@MainActor
@Observable
final class ConductorStore {

    // MARK: - Observed state

    private(set) var exchanges: [ConductorExchange] = []
    private(set) var currentPlan: Plan?
    private(set) var currentDryRun: DryRun?
    private(set) var planExpiresAt: Date?
    private(set) var isPlanning: Bool = false
    private(set) var isExecuting: Bool = false

    /// Server-owned conductor phase (from `conductor_state` events). Feeds the
    /// orb state machine.
    private(set) var serverConductorState: ConductorState = .idle
    /// Latest recoverable error, with a retry affordance.
    private(set) var lastError: ConductorError?

    /// User-adjustable terminal cap (REQ-UX-033): 1…ceiling, default 8.
    ///
    /// The `didSet` clamps to `1…hardCeiling`, but only re-assigns when the
    /// clamped value actually differs — Swift fires `didSet` on *every* set
    /// (including equal-value writes and the clamp write itself), so an
    /// unconditional `cap = …` here recurses without bound and overflows the
    /// stack. The guard makes it converge in at most one extra assignment.
    var cap: Int = 8 {
        didSet {
            let clamped = min(max(cap, 1), hardCeiling)
            if cap != clamped { cap = clamped }
        }
    }
    private(set) var hardCeiling: Int = 8

    /// Conductor pre-flight terminal estimate (REQ-UX-032).
    var estimatedTerminalCount: Int? {
        if let count = currentDryRun?.estimatedSessionCount { return count }
        return currentPlan?.finalCount
    }

    /// Whether the estimate exceeds the cap (REQ-UX-034 warning).
    var capWarning: Bool {
        guard let estimate = estimatedTerminalCount else { return false }
        return estimate > cap
    }

    var hasPendingPlan: Bool { currentPlan != nil }

    private weak var container: AppContainer?
    private var lastIntent: (text: String, source: IntentSource)?
    private var inFlight: Task<Void, Never>?

    init(container: AppContainer) {
        self.container = container
        self.hardCeiling = container.appState.hardCeiling
        self.cap = container.appState.hardCeiling
    }

    // MARK: - Intent → plan

    /// Submit a finalized intent (voice or typed). Returns immediately; the plan
    /// + dry-run arrive asynchronously.
    func sendIntent(text: String, source: IntentSource) {
        appendUser(text)
        guard let container, let api = container.apiClient else {
            lastError = ConductorError(
                title: "Orchestrator offline",
                message: "Open a project to start the Conductor.",
                retriable: false
            )
            return
        }
        lastIntent = (text, source)
        clearPlan()
        lastError = nil
        isPlanning = true
        serverConductorState = .thinking
        hardCeiling = container.appState.hardCeiling
        cap = min(cap, hardCeiling)

        let projectPath = container.appState.currentProjectURL?.path
        let requestCap = cap
        inFlight?.cancel()
        inFlight = Task { [weak self] in
            let context = ConductorContext(activeDir: projectPath, selectedCardId: nil, cap: requestCap)
            let request = ConductorMessageRequest(text: text, source: source, context: context)
            do {
                let response = try await api.conductorMessage(request)
                guard let self else { return }
                self.currentPlan = response.plan
                self.currentDryRun = response.dryRun
                self.planExpiresAt = response.expiresAt
                self.isPlanning = false
                if let applied = response.plan.appliedCap { self.cap = min(applied, self.hardCeiling) }
                self.appendConductor(response.plan.summary)
            } catch {
                guard let self else { return }
                self.isPlanning = false
                self.handle(error: error)
            }
        }
    }

    // MARK: - Confirm / cancel (contract §2.4)

    /// Confirm the pending plan (explicit user action, REQ-UX-032). Applies the
    /// plan server-side with the chosen cap. Memory proposals in the plan are
    /// NOT written by the Conductor — the backend rejects conductor-provenance
    /// writes (§A3); the UI marks them "review".
    func confirmCurrentPlan() {
        guard let container, let api = container.apiClient, let plan = currentPlan else { return }
        isExecuting = true
        let requestCap = cap
        Task { [weak self] in
            do {
                let response = try await api.confirmPlan(plan.planId, request: ConfirmPlanRequest(cap: requestCap))
                guard let self else { return }
                self.isExecuting = false
                self.clearPlan()
                switch response.status {
                case .partial:
                    self.appendConductor("Some actions could not be applied.")
                default:
                    self.appendConductor("Confirmed — applying the plan.")
                }
            } catch {
                guard let self else { return }
                self.isExecuting = false
                self.handle(error: error)
            }
        }
    }

    /// Cancel/discard the pending plan (REQ-UX-043). Does not kill already-running
    /// sessions.
    func cancelCurrentPlan() {
        guard let container, let api = container.apiClient, let plan = currentPlan else {
            clearPlan()
            return
        }
        let planId = plan.planId
        clearPlan()
        appendConductor("Cancelled.")
        Task { [weak self] in
            do {
                _ = try await api.cancelPlan(planId)
            } catch {
                // The local plan is already discarded; surface the server-side
                // cancel failure so a still-pending plan isn't invisibly swallowed
                // (Addendum §A4 typed-error surface).
                self?.handle(error: error)
            }
        }
    }

    // MARK: - Resilience (Addendum §A4)

    /// Retry the last failed intent.
    func retryLastFailed() {
        guard let intent = lastIntent else { return }
        lastError = nil
        sendIntent(text: intent.text, source: intent.source)
    }

    /// Dismiss the error and auto-recover the orb to idle.
    func dismissError() {
        lastError = nil
        if serverConductorState == .error { serverConductorState = .idle }
    }

    // MARK: - Event folding (called by coordinator)

    func apply(_ envelope: EventEnvelope) {
        switch envelope.event {
        case .conductorState(let payload):
            // Ignore a server-sent `listening` (client-local, contract §3.4).
            if payload.state != .listening {
                serverConductorState = payload.state
            }
            if let detail = payload.detail, !detail.isEmpty, payload.state == .thinking {
                updateThinking(detail)
            }
            if payload.state != .error { /* recovered path */ }

        case .dryRunResult(let dryRun):
            // Async estimate for a pending plan (Q14).
            if envelope.planId == nil || envelope.planId == currentPlan?.planId {
                currentDryRun = dryRun
            }

        case .error(let apiError):
            surface(ConductorError(apiError: apiError))
            serverConductorState = .error

        default:
            break
        }
    }

    // MARK: - Internals

    private func handle(error: Error) {
        if let clientError = error as? ArchonClientError {
            switch clientError {
            case .api(let apiError, _):
                surface(ConductorError(apiError: apiError))
            case .incompatibleVersion:
                surface(ConductorError(title: "Incompatible orchestrator",
                                       message: "Update required to continue.", retriable: false))
            case .orchestratorUnavailable, .transport:
                surface(ConductorError(title: "Orchestrator offline",
                                       message: "Lost contact with the local orchestrator.", retriable: true))
            case .decoding:
                surface(ConductorError(title: "Unexpected response",
                                       message: "The orchestrator sent an unreadable reply.", retriable: false))
            }
        } else {
            surface(ConductorError(title: "Conductor error",
                                   message: error.localizedDescription, retriable: true))
        }
        serverConductorState = .error
    }

    private func surface(_ error: ConductorError) {
        lastError = error
    }

    private func appendUser(_ text: String) {
        exchanges.append(ConductorExchange(role: .user, text: text))
    }

    private func appendConductor(_ text: String) {
        exchanges.append(ConductorExchange(role: .conductor, text: text))
    }

    private func updateThinking(_ detail: String) {
        guard isPlanning else { return }
        // Update the trailing conductor "thinking" line if it is the most recent
        // turn; otherwise start one. Never reaches back over a user turn or a
        // prior exchange's reply.
        if let last = exchanges.last, last.role == .conductor {
            exchanges[exchanges.count - 1].text = detail
        } else {
            appendConductor(detail)
        }
    }

    private func clearPlan() {
        currentPlan = nil
        currentDryRun = nil
        planExpiresAt = nil
    }
}
