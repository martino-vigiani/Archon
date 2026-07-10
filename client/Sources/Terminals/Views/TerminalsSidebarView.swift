import SwiftUI

// ============================================================================
// Terminals · Views · TerminalsSidebarView
//
// The compact session list for the left sidebar slot (task item 4): each row
// carries a monochrome state dot (REQ-UX-060), short name + index, and elapsed
// time. Selecting a row drives focus in the Terminals pane (navigates there and
// highlights the pane). Strictly achromatic (§5).
// ============================================================================

struct TerminalsSidebarView: View {
    let store: TerminalsStore

    @Environment(\.archonTheme) private var theme
    @Environment(\.archonCompactLayout) private var compact
    @FocusState private var focusedRowId: String?

    var body: some View {
        Group {
            if compact {
                rail
            } else {
                VStack(alignment: .leading, spacing: 0) {
                    header
                    Divider().overlay(theme.hairline)
                    list
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .archonMaterial(.glassSidebar)
    }

    // MARK: - Compact icon rail (< 1100 pt, REQ-DSN-042)

    private var rail: some View {
        VStack(spacing: Space.sm) {
            Text("\(store.liveSessions.count)")
                .archonText(.monoSm)
                .foregroundStyle(theme.textSecondary)
                .monospacedDigit()
                .padding(.top, Space.sm)
                .accessibilityLabel("\(store.liveSessions.count) live sessions")
            Divider().overlay(theme.hairline)
            if store.orderedSessions.isEmpty {
                Image(systemName: "square.grid.2x2")
                    .font(.system(size: IconSize.row, weight: .light))
                    .foregroundStyle(theme.iconSecondary)
                    .padding(.top, Space.sm)
                Spacer(minLength: 0)
            } else {
                ScrollView {
                    LazyVStack(spacing: Space.xs) {
                        ForEach(store.orderedSessions) { session in
                            railDot(session)
                        }
                    }
                    .padding(.vertical, Space.xs)
                }
            }
        }
    }

    private func railDot(_ session: TerminalSession) -> some View {
        Button {
            store.select(session.id)
        } label: {
            StatusDot(status: session.status)
                .frame(width: 32, height: 32)
                .background {
                    RoundedRectangle(cornerRadius: Radius.badge, style: .continuous)
                        .fill(store.selectedSessionId == session.id ? theme.selectionFill : .clear)
                }
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .focusEffectDisabled()
        .focused($focusedRowId, equals: session.id)
        .archonFocusRing(focusedRowId == session.id, cornerRadius: Radius.badge)
        .help("#\(session.index) \(session.displayName) — \(session.status.label)")
        .accessibilityLabel("Session \(session.index), \(session.displayName), \(session.status.label)")
    }

    // MARK: - Full list

    private var header: some View {
        HStack(spacing: Space.sm) {
            Text("Sessions")
                .archonText(.captionEmphasis)
                .foregroundStyle(theme.textSecondary)
            Spacer(minLength: 0)
            Text("\(store.liveSessions.count) live · \(store.orderedSessions.count) total")
                .archonText(.caption)
                .foregroundStyle(theme.textSecondary)
                .monospacedDigit()
                .lineLimit(1)
        }
        .padding(.horizontal, Space.md)
        .padding(.vertical, Space.sm)
    }

    @ViewBuilder
    private var list: some View {
        if store.orderedSessions.isEmpty {
            VStack(spacing: Space.sm) {
                Image(systemName: "square.grid.2x2")
                    .font(.system(size: IconSize.emptyState, weight: .light))
                    .foregroundStyle(theme.iconSecondary)
                Text(store.isOffline ? "Offline" : "No sessions")
                    .archonText(.caption)
                    .foregroundStyle(theme.textSecondary)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .padding(Space.md)
        } else {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 2) {
                    ForEach(store.orderedSessions) { session in
                        row(session)
                    }
                }
                .padding(.horizontal, Space.sm)
                .padding(.vertical, Space.xs)
            }
        }
    }

    private func row(_ session: TerminalSession) -> some View {
        Button {
            store.select(session.id)
        } label: {
            ArchonListRow(isSelected: store.selectedSessionId == session.id) {
                StatusDot(status: session.status)
            } content: {
                VStack(alignment: .leading, spacing: 0) {
                    HStack(spacing: Space.xs) {
                        Text("#\(session.index)")
                            .archonText(.caption)
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
                        }
                    }
                    HStack(spacing: Space.xs) {
                        Text(session.status.label)
                            .archonText(.caption)
                            .foregroundStyle(theme.textSecondary)
                        Text("·")
                            .archonText(.caption)
                            .foregroundStyle(theme.textSecondary)
                        Text(TerminalFormat.elapsed(session.elapsedSeconds(now: store.now)))
                            .archonText(.caption)
                            .foregroundStyle(theme.textSecondary)
                            .monospacedDigit()
                    }
                }
            }
        }
        .buttonStyle(.plain)
        .focusEffectDisabled()
        .focused($focusedRowId, equals: session.id)
        .archonFocusRing(focusedRowId == session.id)
        .accessibilityLabel("Session \(session.index), \(session.displayName), \(session.status.label)")
    }
}
