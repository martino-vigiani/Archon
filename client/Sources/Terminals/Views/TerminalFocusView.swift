import SwiftUI
import AppKit

// ============================================================================
// Terminals · Views · TerminalFocusView
//
// Focus mode (REQ-UX-012): one terminal expanded to fill the central pane with
// an untruncated scrollable transcript, the task title, and per-session actions
// (Pause = flag-idle, Stop, Copy output). Esc / ⌘W return to the grid (wired by
// the grid's keyboard shortcuts).
// ============================================================================

struct TerminalFocusView: View {
    let store: TerminalsStore
    let session: TerminalSession

    @Environment(\.archonTheme) private var theme
    @State private var confirmingKill = false
    @State private var copied = false

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider().overlay(theme.hairline)
            TerminalRenderView(session: session, followsTail: true, fontSize: 13)
                .padding(.vertical, Space.xs)
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                .background(theme.background)
        }
        .background(theme.background)
        .alert("Stop this session?", isPresented: $confirmingKill) {
            Button("Stop", role: .destructive) { Task { await store.kill(session.id) } }
            Button("Cancel", role: .cancel) { }
        } message: {
            Text("Terminal #\(session.index) “\(session.displayName)” will be terminated.")
        }
    }

    private var header: some View {
        HStack(spacing: Space.sm) {
            Button {
                store.focus(nil)
            } label: {
                Label("Back", systemImage: "chevron.left")
                    .labelStyle(.titleAndIcon)
            }
            .archonButtonStyle(.ghost)
            .keyboardShortcut(.escape, modifiers: [])
            .help("Back to grid (Esc)")

            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: Space.xs) {
                    Text("#\(session.index)")
                        .archonText(.captionEmphasis)
                        .foregroundStyle(theme.textSecondary)
                        .monospacedDigit()
                    Text(session.displayName)
                        .archonText(.title2)
                        .foregroundStyle(theme.textPrimary)
                        .lineLimit(1)
                        .truncationMode(.middle)
                }
                Text("\(session.agentType) · \(TerminalFormat.elapsed(session.elapsedSeconds(now: store.now)))")
                    .archonText(.caption)
                    .foregroundStyle(theme.textSecondary)
                    .monospacedDigit()
            }

            Spacer(minLength: Space.sm)

            StatusBadge(status: session.status, emphasized: session.status == .running)

            HStack(spacing: Space.xs) {
                PaneIconButton(systemImage: copied ? "checkmark" : "doc.on.doc", label: "Copy output") {
                    copyOutput()
                }
                if !session.isTerminal {
                    PaneIconButton(
                        systemImage: session.idleFlagged ? "flag.slash" : "pause",
                        label: session.idleFlagged ? "Clear idle flag" : "Pause (flag idle)"
                    ) {
                        Task { await store.setFlagIdle(session.id, flagged: !session.idleFlagged) }
                    }
                    PaneIconButton(systemImage: "stop.circle", label: "Stop session") {
                        confirmingKill = true
                    }
                    .disabled(store.isOffline)
                }
            }
        }
        .padding(.horizontal, Space.md)
        .padding(.vertical, Space.sm)
        .archonMaterial(.flatElevated)
    }

    private func copyOutput() {
        let pasteboard = NSPasteboard.general
        pasteboard.clearContents()
        pasteboard.setString(session.fullTranscript(), forType: .string)
        copied = true
        Task {
            try? await Task.sleep(for: .seconds(1.5))
            copied = false
        }
    }
}
