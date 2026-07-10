import SwiftUI

/// The three-pane shell (REQ-UX-001): left sidebar, central main pane, right
/// "conductor edge" (collapsible Kanban drawer), with the always-visible
/// floating orb overlay (REQ-UX-002). Content comes entirely from the
/// `ShellRegistry`, so phase-B teams plug views in without touching this file.
struct ThreePaneShell: View {
    @Bindable var appState: AppState
    var registry: ShellRegistry
    @Environment(\.archonTheme) private var theme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        // Drive the responsive tier from the live window width (REQ-DSN-042):
        // < 1100 pt collapses the sidebar to an icon rail and auto-hides the
        // conductor edge so the centre pane always keeps ≥ 420 pt and nothing
        // clips or wraps letter-by-letter.
        GeometryReader { geo in
            let width = geo.size.width
            let compact = Breakpoint.isCompact(windowWidth: width)
            let drawerCollapsed = appState.isConductorEdgeCollapsed
                || Breakpoint.collapsesConductorEdge(windowWidth: width)
            shell(compact: compact, drawerCollapsed: drawerCollapsed)
                .animation(MotionEvent.sidebarToggle.animation(reduceMotion: reduceMotion),
                           value: drawerCollapsed)
                .animation(MotionEvent.sidebarToggle.animation(reduceMotion: reduceMotion),
                           value: compact)
        }
    }

    @ViewBuilder
    private func shell(compact: Bool, drawerCollapsed: Bool) -> some View {
        HSplitView {
            // Left — sidebar (icon rail in the compact tier)
            registry.view(for: .sidebar)
                .environment(\.archonCompactLayout, compact)
                .frame(
                    minWidth: compact ? Breakpoint.railWidth : 200,
                    idealWidth: compact ? Breakpoint.railWidth : appState.sidebarWidth,
                    maxWidth: compact ? Breakpoint.railWidth : 360
                )
                .layoutPriority(compact ? 0 : 1)

            // Center — view switcher + main pane
            VStack(spacing: 0) {
                ViewSwitcher(selected: $appState.selectedPane)
                    .padding(Space.sm)
                    .frame(maxWidth: .infinity)
                    .archonMaterial(.flatElevated)
                Divider().overlay(theme.hairline)
                registry.view(for: .main(appState.selectedPane))
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .archonMotion(.viewSwitch, value: appState.selectedPane)
            }
            .frame(minWidth: 420, maxWidth: .infinity)
            .layoutPriority(2)

            // Right — conductor edge (compact agenda), collapsible to zero width
            if !drawerCollapsed {
                registry.view(for: .conductorEdge)
                    .frame(minWidth: 280, idealWidth: appState.conductorEdgeWidth, maxWidth: 520)
                    .transition(.move(edge: .trailing).combined(with: .opacity))
                    .layoutPriority(1)
            }
        }
        .background(theme.background)
        .overlay(alignment: .top) { connectionBanner }
        .overlay(alignment: .bottom) {
            registry.view(for: .orbOverlay)
                .padding(.bottom, Space.xl)
                .allowsHitTesting(true)
        }
        .background { paneShortcuts }
    }

    @ViewBuilder
    private var connectionBanner: some View {
        if appState.isReconnecting {
            DisconnectedBanner()
                .padding(Space.md)
                .transition(.move(edge: .top).combined(with: .opacity))
        } else if appState.isIncompatible {
            DisconnectedBanner(message: "Incompatible orchestrator — update required.")
                .padding(Space.md)
        }
    }

    /// ⌘1–⌘5 destinations (REQ-UX-003), kept active but invisible.
    private var paneShortcuts: some View {
        ZStack {
            ForEach(MainPane.allCases) { pane in
                Button("") { appState.selectedPane = pane }
                    .keyboardShortcut(KeyEquivalent(pane.shortcutKey), modifiers: .command)
                    .frame(width: 0, height: 0)
                    .opacity(0)
            }
        }
        .accessibilityHidden(true)
    }
}

/// The five-destination segmented view switcher (REQ-UX-003).
struct ViewSwitcher: View {
    @Binding var selected: MainPane

    var body: some View {
        Picker("View", selection: $selected) {
            ForEach(MainPane.allCases) { pane in
                Label(pane.title, systemImage: pane.systemImageName)
                    .tag(pane)
            }
        }
        .pickerStyle(.segmented)
        .labelsHidden()
        .accessibilityLabel("Main view switcher")
    }
}
