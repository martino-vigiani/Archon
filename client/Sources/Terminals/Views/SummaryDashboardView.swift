import SwiftUI

// ============================================================================
// Terminals · Views · SummaryDashboardView
//
// The Summary Dashboard (REQ-UX-020/021/024): a condensed, glanceable overview
// — active/total sessions, sessions by status, aggregate tokens, elapsed run
// time, and the last Conductor decision — all visible without scrolling at
// ≥ 1200×800. KPI tiles reflect the store's ≤ 1 Hz `kpi` snapshot; the Conductor
// log reflects live events immediately. Status tiles navigate to the filtered
// Terminals view (REQ-UX-024). A compact spawn/termination timeline (REQ-UX-022)
// fills the remaining space. Calm technology: quiet, monochrome, no noise.
// ============================================================================

struct SummaryDashboardView: View {
    let store: TerminalsStore

    @Environment(\.archonTheme) private var theme

    private let statusOrder: [SessionStatus] = [.idle, .running, .blocked, .error, .done]

    var body: some View {
        VStack(alignment: .leading, spacing: Space.md) {
            runStatusStrip
            kpiRow
            statusRow
            conductorAndTimeline
        }
        .padding(Space.md)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(theme.background)
    }

    // MARK: - Run status strip

    private var runStatusStrip: some View {
        HStack(spacing: Space.md) {
            HStack(spacing: Space.sm) {
                Image(systemName: connectionIcon)
                    .font(.system(size: IconSize.row, weight: .medium))
                    .foregroundStyle(theme.iconSecondary)
                VStack(alignment: .leading, spacing: 0) {
                    Text(connectionTitle)
                        .archonText(.bodyEmphasis)
                        .foregroundStyle(theme.textPrimary)
                    Text("Run time \(TerminalFormat.elapsed(store.kpi.elapsedRunSeconds))")
                        .archonText(.caption)
                        .foregroundStyle(theme.textSecondary)
                        .monospacedDigit()
                }
            }
            Spacer()
            Text("Archon · \(store.orderedSessions.count) session(s) this run")
                .archonText(.caption)
                .foregroundStyle(theme.textSecondary)
        }
        .padding(Space.md)
        .archonMaterial(.flatElevated, cornerRadius: Radius.card)
        .overlay {
            RoundedRectangle(cornerRadius: Radius.card, style: .continuous)
                .strokeBorder(theme.borderSubtle, lineWidth: Space.hairline)
        }
    }

    private var connectionIcon: String {
        switch store.connectionState {
        case .connected: return "dot.radiowaves.left.and.right"
        case .reconnecting, .connecting: return "arrow.triangle.2.circlepath"
        case .incompatible: return "exclamationmark.triangle"
        case .idle, .disconnected: return "bolt.horizontal.circle"
        }
    }

    private var connectionTitle: String {
        switch store.connectionState {
        case .connected: return "Live"
        case .connecting: return "Connecting…"
        case .reconnecting: return "Reconnecting…"
        case .incompatible: return "Incompatible orchestrator"
        case .idle, .disconnected: return store.isOffline ? "Offline" : "Idle"
        }
    }

    // MARK: - KPI tiles

    private var kpiRow: some View {
        HStack(spacing: Space.md) {
            KPITile(title: "Active", value: "\(store.kpi.activeCount)", caption: "running now", theme: theme)
            KPITile(title: "Total spawned", value: "\(store.kpi.totalSpawned)", caption: "this run", theme: theme)
            KPITile(title: "Elapsed", value: TerminalFormat.elapsed(store.kpi.elapsedRunSeconds), caption: "run time", theme: theme)
            KPITile(
                title: "Tokens",
                value: store.kpi.aggregateTokens.map { "\($0)" } ?? "—",
                caption: store.kpi.aggregateTokens == nil ? "not reported" : "consumed",
                theme: theme
            )
        }
    }

    // MARK: - Status tiles (clickable → filtered Terminals, REQ-UX-024)

    private var statusRow: some View {
        HStack(spacing: Space.sm) {
            ForEach(statusOrder, id: \.self) { status in
                StatusCountTile(
                    status: status,
                    count: store.kpi.count(status),
                    theme: theme
                ) {
                    store.showTerminals(filteredBy: status)
                }
            }
        }
    }

    // MARK: - Conductor log + timeline

    private var conductorAndTimeline: some View {
        HStack(alignment: .top, spacing: Space.md) {
            conductorPanel
                .frame(maxWidth: .infinity, alignment: .topLeading)
            timelinePanel
                .frame(maxWidth: .infinity, alignment: .topLeading)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }

    private var conductorPanel: some View {
        ArchonPanel {
            VStack(alignment: .leading, spacing: Space.sm) {
                Label("Last Conductor decision", systemImage: "waveform")
                    .archonText(.captionEmphasis)
                    .foregroundStyle(theme.textSecondary)
                if let decision = store.lastConductorDecision {
                    Text(decision)
                        .archonText(.body)
                        .foregroundStyle(theme.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                    if let at = store.lastConductorAt {
                        Text(at, style: .time)
                            .archonText(.caption)
                            .foregroundStyle(theme.textSecondary)
                    }
                } else {
                    Text("No decisions yet. The Conductor’s reasoning appears here.")
                        .archonText(.body)
                        .foregroundStyle(theme.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }

    private var timelinePanel: some View {
        ArchonPanel {
            VStack(alignment: .leading, spacing: Space.sm) {
                Label("Timeline", systemImage: "clock")
                    .archonText(.captionEmphasis)
                    .foregroundStyle(theme.textSecondary)
                if store.timeline.isEmpty {
                    Text("Spawn and termination events appear here.")
                        .archonText(.caption)
                        .foregroundStyle(theme.textSecondary)
                } else {
                    ScrollView {
                        VStack(alignment: .leading, spacing: Space.xs) {
                            ForEach(store.timeline.reversed()) { event in
                                TimelineRow(event: event, theme: theme)
                            }
                        }
                    }
                    .frame(maxHeight: .infinity)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
    }
}

// MARK: - KPI tile

private struct KPITile: View {
    let title: String
    let value: String
    let caption: String
    let theme: Theme

    var body: some View {
        VStack(alignment: .leading, spacing: Space.xs) {
            Text(title.uppercased())
                .archonText(.caption)
                .foregroundStyle(theme.textSecondary)
            Text(value)
                .archonText(.title1)
                .foregroundStyle(theme.textPrimary)
                .monospacedDigit()
                .lineLimit(1)
                .minimumScaleFactor(0.6)
            Text(caption)
                .archonText(.caption)
                .foregroundStyle(theme.textSecondary)
        }
        .padding(Space.md)
        .frame(maxWidth: .infinity, alignment: .leading)
        .archonMaterial(.flatSurface, cornerRadius: Radius.card)
        .overlay {
            RoundedRectangle(cornerRadius: Radius.card, style: .continuous)
                .strokeBorder(theme.borderSubtle, lineWidth: Space.hairline)
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(title): \(value), \(caption)")
    }
}

// MARK: - Status count tile

private struct StatusCountTile: View {
    let status: SessionStatus
    let count: Int
    let theme: Theme
    let action: () -> Void

    @State private var hovering = false

    var body: some View {
        Button(action: action) {
            VStack(spacing: Space.xs) {
                Image(systemName: status.systemImageName)
                    .font(.system(size: IconSize.row, weight: .medium))
                    .foregroundStyle(theme.iconSecondary)
                Text("\(count)")
                    .archonText(.title2)
                    .foregroundStyle(theme.textPrimary)
                    .monospacedDigit()
                Text(status.label)
                    .archonText(.caption)
                    .foregroundStyle(theme.textSecondary)
            }
            .padding(.vertical, Space.md)
            .frame(maxWidth: .infinity)
            .archonMaterial(hovering ? .flatElevated : .flatSurface, cornerRadius: Radius.card)
            .overlay {
                RoundedRectangle(cornerRadius: Radius.card, style: .continuous)
                    .strokeBorder(hovering ? theme.borderStrong : theme.borderSubtle, lineWidth: Space.hairline)
            }
        }
        .buttonStyle(.plain)
        .onHover { hovering = $0 }
        .help("Show \(status.label.lowercased()) terminals")
        .accessibilityLabel("\(status.label): \(count). Show these terminals.")
    }
}

// MARK: - Timeline row

private struct TimelineRow: View {
    let event: TerminalTimelineEvent
    let theme: Theme

    var body: some View {
        HStack(spacing: Space.sm) {
            Image(systemName: event.kind == .spawned ? "arrow.up.circle" : "checkmark.circle")
                .font(.system(size: IconSize.inline, weight: .regular))
                .foregroundStyle(theme.iconSecondary)
            Text(event.at, style: .time)
                .archonText(.monoSm)
                .foregroundStyle(theme.textSecondary)
                .monospacedDigit()
            Text("#\(event.index) \(event.kind == .spawned ? "spawned" : "ended")")
                .archonText(.caption)
                .foregroundStyle(theme.textPrimary)
            Spacer(minLength: 0)
        }
        .accessibilityElement(children: .combine)
    }
}
