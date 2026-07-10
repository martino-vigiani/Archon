import SwiftUI

/// The Conductor exchange surface (REQ-ARCH-043: exactly one Conductor presence).
/// A minimal, non-modal pane: exchange log, live transcript preview, the pending
/// plan with confirm/cancel, a typed-intent input, and inline resilience
/// (retry). Registered into `ShellSlot.conductorSurface` and also floated above
/// the orb by the coordinator.
struct ConductorSurfaceView: View {
    @Bindable var conductor: ConductorStore
    var voice: VoiceStore
    @Environment(\.archonTheme) private var theme

    @State private var draft: String = ""
    @FocusState private var inputFocused: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: Space.sm) {
            header
            content
            inputRow
        }
        .padding(Space.md)
        .frame(minWidth: 320, idealWidth: 400, maxWidth: 460)
        .archonMaterial(.glassFloating, cornerRadius: Radius.floatingPanel)
        .overlay {
            RoundedRectangle(cornerRadius: Radius.floatingPanel, style: .continuous)
                .strokeBorder(theme.borderSubtle, lineWidth: Space.hairline)
        }
        .frame(maxWidth: .infinity, alignment: .center)
    }

    // MARK: - Header

    private var header: some View {
        HStack(spacing: Space.sm) {
            Text("Conductor")
                .archonText(.title2)
                .foregroundStyle(theme.textPrimary)
            Spacer(minLength: 0)
            if conductor.isPlanning {
                Text("Planning…")
                    .archonText(.caption)
                    .foregroundStyle(theme.textSecondary)
            }
        }
    }

    // MARK: - Content

    @ViewBuilder
    private var content: some View {
        if let error = conductor.lastError {
            errorCard(error)
        }

        if !conductor.exchanges.isEmpty {
            exchangeLog
        }

        if voice.phase == .listening || voice.phase == .preparing {
            LiveTranscriptView(
                text: voice.partialTranscript,
                isPreparing: voice.phase == .preparing,
                downloadProgress: voice.modelDownloadProgress
            )
        }

        if let plan = conductor.currentPlan {
            PlanView(plan: plan, dryRun: conductor.currentDryRun, conductor: conductor)
        }

        if isEmptyState {
            EmptyStateView(
                systemImage: "waveform",
                title: "Conductor",
                message: "Hold \(HotKeyBinding.defaultBinding.displayString) to speak, or type below."
            )
            .frame(minHeight: 120)
        }

        if let message = voice.errorMessage {
            Text(message)
                .archonText(.caption)
                .foregroundStyle(theme.textSecondary)
        }
    }

    private var isEmptyState: Bool {
        conductor.exchanges.isEmpty
            && conductor.currentPlan == nil
            && conductor.lastError == nil
            && voice.phase == .idle
    }

    private var exchangeLog: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: Space.sm) {
                    ForEach(conductor.exchanges) { exchange in
                        ConductorMessageRow(exchange: exchange)
                            .id(exchange.id)
                    }
                }
                .padding(.vertical, Space.xs)
            }
            .frame(maxHeight: 220)
            .onChange(of: conductor.exchanges.count) {
                if let last = conductor.exchanges.last {
                    withAnimation(Micro.tap) { proxy.scrollTo(last.id, anchor: .bottom) }
                }
            }
        }
    }

    private func errorCard(_ error: ConductorError) -> some View {
        VStack(alignment: .leading, spacing: Space.xs) {
            HStack(spacing: Space.sm) {
                Image(systemName: "exclamationmark.triangle")
                    .foregroundStyle(theme.iconSecondary)
                Text(error.title)
                    .archonText(.captionEmphasis)
                    .foregroundStyle(theme.textPrimary)
                Spacer(minLength: 0)
            }
            Text(error.message)
                .archonText(.caption)
                .foregroundStyle(theme.textSecondary)
            HStack(spacing: Space.sm) {
                if error.retriable {
                    Button("Retry") { conductor.retryLastFailed() }
                        .archonButtonStyle(.secondary)
                }
                Button("Dismiss") { conductor.dismissError() }
                    .archonButtonStyle(.ghost)
            }
            .frame(maxWidth: .infinity, alignment: .trailing)
        }
        .padding(Space.sm)
        .archonMaterial(.flatSurface, cornerRadius: Radius.input)
        .overlay {
            RoundedRectangle(cornerRadius: Radius.input, style: .continuous)
                .strokeBorder(theme.borderStrong, lineWidth: Space.hairline)
        }
    }

    // MARK: - Input

    private var inputRow: some View {
        HStack(spacing: Space.sm) {
            Button {
                voice.togglePushToTalk()
            } label: {
                Image(systemName: voice.isListening ? "mic.fill" : "mic")
                    .font(.system(size: IconSize.row))
                    .foregroundStyle(voice.isListening ? theme.textPrimary : theme.iconSecondary)
                    .frame(width: 28, height: 28)
            }
            .buttonStyle(.plain)
            .accessibilityLabel(voice.isListening ? "Stop listening" : "Start listening")

            TextField("Message the Conductor…", text: $draft, axis: .vertical)
                .textFieldStyle(.plain)
                .archonText(.body)
                .foregroundStyle(theme.textPrimary)
                .lineLimit(1...4)
                .focused($inputFocused)
                .onSubmit(send)
                .padding(.horizontal, Space.sm)
                .padding(.vertical, Space.xs)
                .archonMaterial(.flatElevated, cornerRadius: Radius.input)

            Button("Send", action: send)
                .archonButtonStyle(.primary)
                .disabled(draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
        }
    }

    private func send() {
        let text = draft
        draft = ""
        voice.submitTyped(text)
    }
}

/// A slim edge affordance that summons/dismisses the Conductor surface (the
/// "conductor edge" handle). Used inside the orb overlay composition — it is NOT
/// registered into `ShellSlot.conductorEdge` (that slot houses the Kanban board,
/// owned by the Board sector).
struct ConductorEdgeAffordance: View {
    @Binding var isExpanded: Bool
    @Environment(\.archonTheme) private var theme

    var body: some View {
        Button {
            withAnimation(MotionEvent.sidebarToggle.spring.animation) { isExpanded.toggle() }
        } label: {
            Image(systemName: isExpanded ? "chevron.down" : "chevron.up")
                .font(.system(size: IconSize.inline, weight: .semibold))
                .foregroundStyle(theme.iconSecondary)
                .frame(width: 32, height: 18)
                .archonMaterial(.glassFloating, cornerRadius: Radius.badge)
        }
        .buttonStyle(.plain)
        .accessibilityLabel(isExpanded ? "Hide Conductor" : "Show Conductor")
    }
}
