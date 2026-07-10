import SwiftUI

/// Renders a Conductor plan for explicit confirmation (REQ-ARCH-041/042,
/// REQ-UX-032/033/034): the action list (spawns / kanban ops / memory
/// proposals), the dry-run estimate line, an inline terminal-cap spinner, a
/// cap-exceeded warning, and Confirm (⏎) / Cancel (Esc). Nothing is applied
/// until Confirm.
struct PlanView: View {
    let plan: Plan
    let dryRun: DryRun?
    @Bindable var conductor: ConductorStore
    @Environment(\.archonTheme) private var theme

    var body: some View {
        VStack(alignment: .leading, spacing: Space.sm) {
            header
            actionList
            dryRunLine
            if conductor.capWarning { capWarningLine }
            controls
        }
        .padding(Space.md)
        .archonMaterial(.flatElevated, cornerRadius: Radius.card)
        .overlay {
            RoundedRectangle(cornerRadius: Radius.card, style: .continuous)
                .strokeBorder(theme.borderSubtle, lineWidth: Space.hairline)
        }
        .accessibilityElement(children: .contain)
    }

    private var header: some View {
        HStack(spacing: Space.sm) {
            Image(systemName: "list.bullet.rectangle")
                .foregroundStyle(theme.iconSecondary)
            Text("Proposed plan")
                .archonText(.captionEmphasis)
                .foregroundStyle(theme.textPrimary)
            Spacer(minLength: 0)
            Text("\(plan.finalCount) action\(plan.finalCount == 1 ? "" : "s")")
                .archonText(.caption)
                .foregroundStyle(theme.textSecondary)
        }
    }

    private var actionList: some View {
        VStack(alignment: .leading, spacing: Space.xs) {
            ForEach(plan.actions) { action in
                PlanActionRow(action: action)
            }
        }
    }

    private var dryRunLine: some View {
        HStack(spacing: Space.xs) {
            Image(systemName: "gauge.with.dots.needle.33percent")
                .font(.system(size: IconSize.inline))
                .foregroundStyle(theme.iconSecondary)
            Text(DryRunFormat.summaryLine(dryRun))
                .archonText(.caption)
                .foregroundStyle(theme.textSecondary)
        }
        .accessibilityLabel("Estimate: \(DryRunFormat.summaryLine(dryRun))")
    }

    private var capWarningLine: some View {
        Text("Conductor estimates \(conductor.estimatedTerminalCount ?? 0) terminals; cap is \(conductor.cap) — work may be incomplete.")
            .archonText(.caption)
            .foregroundStyle(theme.textPrimary)
            .padding(Space.sm)
            .frame(maxWidth: .infinity, alignment: .leading)
            .archonMaterial(.flatSurface, cornerRadius: Radius.input)
            .overlay {
                RoundedRectangle(cornerRadius: Radius.input, style: .continuous)
                    .strokeBorder(theme.borderStrong, lineWidth: Space.hairline)
            }
    }

    private var controls: some View {
        VStack(spacing: Space.sm) {
            Stepper(value: $conductor.cap, in: 1...conductor.hardCeiling) {
                Text("Cap at \(conductor.cap) terminal\(conductor.cap == 1 ? "" : "s")")
                    .archonText(.caption)
                    .foregroundStyle(theme.textSecondary)
            }
            .accessibilityLabel("Terminal cap")
            .accessibilityValue("\(conductor.cap)")

            HStack(spacing: Space.sm) {
                Button("Cancel") { conductor.cancelCurrentPlan() }
                    .archonButtonStyle(.secondary)
                    .keyboardShortcut(.cancelAction)
                Button(conductor.isExecuting ? "Confirming…" : "Confirm") {
                    conductor.confirmCurrentPlan()
                }
                .archonButtonStyle(.primary)
                .keyboardShortcut(.defaultAction)
                .disabled(conductor.isExecuting)
            }
            .frame(maxWidth: .infinity, alignment: .trailing)
        }
    }
}

/// A single plan action row. Destructive actions and memory proposals are
/// visually distinguished (REQ-ARCH-042; Addendum §A3 review handoff).
struct PlanActionRow: View {
    let action: PlanAction
    @Environment(\.archonTheme) private var theme

    var body: some View {
        HStack(alignment: .top, spacing: Space.sm) {
            Image(systemName: action.kind.symbolName)
                .font(.system(size: IconSize.inline, weight: .medium))
                .foregroundStyle(action.isDestructive ? theme.textPrimary : theme.iconSecondary)
                .frame(width: IconSize.row)
            VStack(alignment: .leading, spacing: 1) {
                HStack(spacing: Space.xs) {
                    Text(action.kind.label)
                        .archonText(.captionEmphasis)
                        .foregroundStyle(theme.textPrimary)
                    if action.isDestructive {
                        tag("Destructive")
                    }
                    if action.isMemoryProposal {
                        tag("Review")
                    }
                }
                if let detail = action.detailLine, !detail.isEmpty {
                    Text(detail)
                        .archonText(.caption)
                        .foregroundStyle(theme.textSecondary)
                        .lineLimit(2)
                }
                if action.isMemoryProposal {
                    Text("Memory edits are never auto-applied — you review and save.")
                        .archonText(.caption)
                        .foregroundStyle(theme.textDisabled)
                }
            }
            Spacer(minLength: 0)
        }
        .padding(.vertical, Space.xs)
        .accessibilityElement(children: .combine)
    }

    private func tag(_ text: String) -> some View {
        Text(text.uppercased())
            .archonText(.caption)
            .foregroundStyle(theme.textSecondary)
            .padding(.horizontal, Space.xs)
            .padding(.vertical, 1)
            .overlay {
                RoundedRectangle(cornerRadius: Radius.badge, style: .continuous)
                    .strokeBorder(theme.borderStrong, lineWidth: Space.hairline)
            }
    }
}
