import SwiftUI

// ============================================================================
// Terminals · Views · TerminalPaneView
//
// One live terminal card (REQ-UX-011): header (index + short name + agent type,
// status badge, elapsed timer, activity cue), the live auto-scrolling PTY
// transcript, and per-session controls (focus/expand, flag-idle, stop w/
// confirm). A subtle border distinction marks recent errors (REQ-UX-014) and
// selection — strictly achromatic (§5).
// ============================================================================

struct TerminalPaneView: View {
    let store: TerminalsStore
    let session: TerminalSession
    var isFocused: Bool = false

    @Environment(\.archonTheme) private var theme
    @State private var confirmingKill = false

    private var isSelected: Bool { store.selectedSessionId == session.id }

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider().overlay(theme.hairline)
            transcript
        }
        .archonMaterial(.flatSurface, cornerRadius: Radius.card)
        .overlay { borderOverlay }
        .contentShape(Rectangle())
        .onTapGesture { store.select(session.id) }
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Terminal \(session.index): \(session.displayName), \(session.status.label)")
    }

    // MARK: - Header

    private var header: some View {
        HStack(spacing: Space.sm) {
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: Space.xs) {
                    Text("#\(session.index)")
                        .archonText(.captionEmphasis)
                        .foregroundStyle(theme.textSecondary)
                        .monospacedDigit()
                    Text(session.displayName)
                        .archonText(.bodyEmphasis)
                        .foregroundStyle(theme.textPrimary)
                        .lineLimit(1)
                        .truncationMode(.middle)
                    if session.idleFlagged {
                        Image(systemName: "flag.fill")
                            .font(.system(size: IconSize.caption, weight: .medium))
                            .foregroundStyle(theme.iconSecondary)
                            .accessibilityLabel("Flagged idle")
                    }
                }
                HStack(spacing: Space.sm) {
                    Text(session.agentType)
                        .archonText(.caption)
                        .foregroundStyle(theme.textSecondary)
                        .lineLimit(1)
                        .truncationMode(.tail)
                    Text(TerminalFormat.elapsed(session.elapsedSeconds(now: store.now)))
                        .archonText(.caption)
                        .foregroundStyle(theme.textSecondary)
                        .monospacedDigit()
                }
            }
            Spacer(minLength: Space.sm)
            StatusBadge(status: session.status, emphasized: session.status == .running)
            controls
        }
        .padding(.horizontal, Space.md)
        .padding(.vertical, Space.sm)
        .archonMaterial(.flatElevated)
    }

    private var controls: some View {
        HStack(spacing: Space.xs) {
            PaneIconButton(
                systemImage: isFocused ? "arrow.down.right.and.arrow.up.left" : "arrow.up.left.and.arrow.down.right",
                label: isFocused ? "Exit focus" : "Focus terminal"
            ) {
                store.focus(isFocused ? nil : session.id)
            }
            if !session.isTerminal {
                PaneIconButton(
                    systemImage: session.idleFlagged ? "flag.slash" : "flag",
                    label: session.idleFlagged ? "Clear idle flag" : "Flag idle"
                ) {
                    Task { await store.setFlagIdle(session.id, flagged: !session.idleFlagged) }
                }
                PaneIconButton(systemImage: "stop.circle", label: "Stop session") {
                    confirmingKill = true
                }
                .disabled(store.isOffline)
            }
        }
        .alert("Stop this session?", isPresented: $confirmingKill) {
            Button("Stop", role: .destructive) { Task { await store.kill(session.id) } }
            Button("Cancel", role: .cancel) { }
        } message: {
            Text("Terminal #\(session.index) “\(session.displayName)” will be terminated. This cannot be undone.")
        }
    }

    // MARK: - Transcript

    private var transcript: some View {
        ZStack(alignment: .topLeading) {
            TerminalRenderView(session: session, followsTail: true)
                .padding(.vertical, Space.xs)
            if session.emulator.lineCount <= 1 && session.emulator.line(at: 0).isEmpty {
                waitingOverlay
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .clipShape(RoundedRectangle(cornerRadius: Radius.card, style: .continuous))
    }

    @ViewBuilder
    private var waitingOverlay: some View {
        HStack(spacing: Space.sm) {
            Image(systemName: session.isTerminal ? "checkmark.circle" : "ellipsis")
                .font(.system(size: IconSize.inline, weight: .regular))
                .foregroundStyle(theme.iconSecondary)
            Text(session.isTerminal ? "Session ended — no output" : "Waiting for output…")
                .archonText(.caption)
                .foregroundStyle(theme.textSecondary)
        }
        .padding(Space.md)
    }

    // MARK: - Border

    @ViewBuilder
    private var borderOverlay: some View {
        let color: Color = isSelected ? theme.selectionBorder
            : (session.hasRecentError ? theme.borderStrong : theme.borderSubtle)
        let width: CGFloat = (isSelected || session.hasRecentError) ? 1.5 : Space.hairline
        RoundedRectangle(cornerRadius: Radius.card, style: .continuous)
            .strokeBorder(color, lineWidth: width)
    }
}

// MARK: - Small icon button

/// A compact achromatic ghost icon button for pane controls.
struct PaneIconButton: View {
    let systemImage: String
    let label: String
    let action: () -> Void

    @Environment(\.archonTheme) private var theme
    @Environment(\.isEnabled) private var isEnabled
    @State private var hovering = false

    var body: some View {
        Button(action: action) {
            Image(systemName: systemImage)
                .font(.system(size: IconSize.inline, weight: .medium))
                .foregroundStyle(isEnabled ? theme.iconSecondary : theme.textDisabled)
                .frame(width: 24, height: 24)
                .background {
                    RoundedRectangle(cornerRadius: Radius.badge, style: .continuous)
                        .fill(hovering && isEnabled ? theme.surfaceRaised : .clear)
                }
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hovering = $0 }
        .help(label)
        .accessibilityLabel(label)
    }
}

// MARK: - Formatting

enum TerminalFormat {
    /// Formats a duration in seconds as `m:ss` or `h:mm:ss`.
    static func elapsed(_ seconds: Int) -> String {
        let s = max(0, seconds)
        let h = s / 3600
        let m = (s % 3600) / 60
        let sec = s % 60
        if h > 0 {
            return String(format: "%d:%02d:%02d", h, m, sec)
        }
        return String(format: "%d:%02d", m, sec)
    }
}
