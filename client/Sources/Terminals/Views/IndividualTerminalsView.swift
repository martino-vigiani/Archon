import SwiftUI

// ============================================================================
// Terminals · Views · IndividualTerminalsView
//
// The Individual Terminals main pane (REQ-UX-010/012/015). All active terminals
// in a responsive grid (1-2 → 1×N; 3-4 → 2×2; 5-9 → 3×3; >9 → 4-col scroll);
// click/keyboard focus expands one terminal to fill the pane (Esc/⌘W returns).
// A calm toolbar offers "New session", "Stop All" (⌃⌥S, confirmed), and the
// dashboard-driven status filter (REQ-UX-024).
// ============================================================================

struct IndividualTerminalsView: View {
    let store: TerminalsStore

    @Environment(\.archonTheme) private var theme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var showingNewSession = false
    @State private var confirmingStopAll = false

    private var sessions: [TerminalSession] { store.filteredSessions() }

    var body: some View {
        VStack(spacing: 0) {
            toolbar
            Divider().overlay(theme.hairline)
            content
        }
        .background(theme.background)
        .sheet(isPresented: $showingNewSession) {
            NewSessionSheet(store: store, isPresented: $showingNewSession)
        }
        .alert("Stop all sessions?", isPresented: $confirmingStopAll) {
            Button("Stop All", role: .destructive) { Task { await store.stopAll() } }
            Button("Cancel", role: .cancel) { }
        } message: {
            Text("All \(store.liveSessions.count) running session(s) will be terminated.")
        }
        .background { keyboardShortcuts }
    }

    // MARK: - Toolbar

    private var toolbar: some View {
        HStack(spacing: Space.sm) {
            Button {
                showingNewSession = true
            } label: {
                Label("New Session", systemImage: "plus")
            }
            .archonButtonStyle(.secondary)
            .disabled(!store.canSpawn)
            .help(store.canSpawn ? "Spawn a new Claude Code session" : "Unavailable while offline")

            if !store.liveSessions.isEmpty {
                Button(role: .destructive) {
                    confirmingStopAll = true
                } label: {
                    Label("Stop All", systemImage: "stop.circle")
                }
                .archonButtonStyle(.ghost)
                .help("Stop all sessions (⌃⌥S)")
            }

            Spacer(minLength: Space.sm)

            if let filter = store.statusFilter {
                filterChip(filter)
            }

            Text("\(store.liveSessions.count) live · \(store.orderedSessions.count) total")
                .archonText(.caption)
                .foregroundStyle(theme.textSecondary)
                .monospacedDigit()
        }
        .padding(.horizontal, Space.md)
        .padding(.vertical, Space.sm)
        .archonMaterial(.flatElevated)
    }

    private func filterChip(_ status: SessionStatus) -> some View {
        Button {
            store.clearFilter()
        } label: {
            HStack(spacing: Space.xs) {
                Image(systemName: status.systemImageName)
                    .font(.system(size: IconSize.inline - 2, weight: .medium))
                Text("Filtered: \(status.label)")
                    .archonText(.captionEmphasis)
                Image(systemName: "xmark")
                    .font(.system(size: IconSize.inline - 4, weight: .semibold))
            }
            .foregroundStyle(theme.textSecondary)
            .padding(.horizontal, Space.sm)
            .padding(.vertical, Space.xs)
            .archonMaterial(.flatSurface, cornerRadius: Radius.badge)
            .overlay {
                RoundedRectangle(cornerRadius: Radius.badge, style: .continuous)
                    .strokeBorder(theme.borderSubtle, lineWidth: Space.hairline)
            }
        }
        .buttonStyle(.plain)
        .help("Clear filter")
        .accessibilityLabel("Clear \(status.label) filter")
    }

    // MARK: - Content

    @ViewBuilder
    private var content: some View {
        if let focusedId = store.focusedSessionId, let session = store.sessionsById[focusedId] {
            TerminalFocusView(store: store, session: session)
                .transition(reduceMotion ? .opacity : .opacity.combined(with: .scale(scale: 0.98)))
        } else if store.orderedSessions.isEmpty {
            emptyState
        } else if sessions.isEmpty {
            filteredEmptyState
        } else {
            grid
        }
    }

    private var grid: some View {
        GeometryReader { geo in
            let columns = TerminalGridLayout.columns(forCount: sessions.count)
            if sessions.count > 9 {
                ScrollView {
                    LazyVGrid(columns: fixedColumns(columns), spacing: Space.md) {
                        ForEach(sessions) { session in
                            TerminalPaneView(store: store, session: session, isFocused: false)
                                .frame(minHeight: 260)
                        }
                    }
                    .padding(Space.md)
                }
            } else {
                let rows = Int(ceil(Double(sessions.count) / Double(columns)))
                let spacing = Space.md
                let cellHeight = (geo.size.height - spacing * CGFloat(rows + 1)) / CGFloat(max(1, rows))
                VStack(spacing: spacing) {
                    ForEach(0..<rows, id: \.self) { row in
                        HStack(spacing: spacing) {
                            ForEach(0..<columns, id: \.self) { col in
                                let index = row * columns + col
                                if index < sessions.count {
                                    TerminalPaneView(store: store, session: sessions[index], isFocused: false)
                                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                                } else {
                                    Color.clear.frame(maxWidth: .infinity, maxHeight: .infinity)
                                }
                            }
                        }
                        .frame(height: max(180, cellHeight))
                    }
                }
                .padding(spacing)
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
            }
        }
        .animation(MotionEvent.terminalSpawn.animation(reduceMotion: reduceMotion), value: sessions.count)
    }

    private func fixedColumns(_ count: Int) -> [GridItem] {
        Array(repeating: GridItem(.flexible(), spacing: Space.md), count: count)
    }

    private var emptyState: some View {
        EmptyStateView(
            systemImage: "square.grid.2x2",
            title: store.isOffline ? "Offline" : "No terminals yet",
            message: store.isOffline
                ? "Reconnecting to the orchestrator. Existing output stays readable."
                : "Start a Claude Code session to see its live terminal here.",
            actionTitle: store.canSpawn ? "New Session" : nil,
            action: store.canSpawn ? { showingNewSession = true } : nil
        )
    }

    private var filteredEmptyState: some View {
        EmptyStateView(
            systemImage: store.statusFilter?.systemImageName ?? "line.3.horizontal.decrease.circle",
            title: "No matching terminals",
            message: "No sessions are \(store.statusFilter?.label.lowercased() ?? "matching") right now.",
            actionTitle: "Clear filter",
            action: { store.clearFilter() }
        )
    }

    // MARK: - Keyboard (arrows navigate, Return focuses, Esc exits, ⌃⌥S stop-all)

    private var keyboardShortcuts: some View {
        ZStack {
            Button("") { moveSelection(-1) }
                .keyboardShortcut(.leftArrow, modifiers: [])
            Button("") { moveSelection(1) }
                .keyboardShortcut(.rightArrow, modifiers: [])
            Button("") { moveSelection(-1) }
                .keyboardShortcut(.upArrow, modifiers: [])
            Button("") { moveSelection(1) }
                .keyboardShortcut(.downArrow, modifiers: [])
            Button("") { focusSelected() }
                .keyboardShortcut(.return, modifiers: [])
            Button("") { store.focus(nil) }
                .keyboardShortcut(.escape, modifiers: [])
            Button("") { store.focus(nil) }
                .keyboardShortcut("w", modifiers: .command)
            Button("") { if !store.liveSessions.isEmpty { confirmingStopAll = true } }
                .keyboardShortcut("s", modifiers: [.control, .option])
        }
        .opacity(0)
        .frame(width: 0, height: 0)
        .accessibilityHidden(true)
    }

    private func moveSelection(_ delta: Int) {
        let list = sessions
        guard !list.isEmpty else { return }
        let currentIndex = list.firstIndex { $0.id == store.selectedSessionId } ?? 0
        let next = min(max(0, currentIndex + delta), list.count - 1)
        store.selectedSessionId = list[next].id
    }

    private func focusSelected() {
        if let id = store.selectedSessionId, store.sessionsById[id] != nil {
            store.focus(id)
        }
    }
}

// MARK: - Adaptive grid layout (REQ-UX-010)

enum TerminalGridLayout {
    /// Column count for a session count: 1-2 → 1×N; 3-4 → 2×2; 5-9 → 3×3; >9 → 4.
    static func columns(forCount count: Int) -> Int {
        switch count {
        case 0, 1: return 1
        case 2, 3, 4: return 2
        case 5...9: return 3
        default: return 4
        }
    }
}
