import SwiftUI

/// A Conductor memory-edit proposal rendered as a diff-style review card
/// (addendum §A3): Accept becomes a user-initiated write, Reject discards it.
/// The card makes crystal-clear the Conductor did NOT write anything yet.
/// Strictly achromatic: +/− differ by prefix glyph, weight, and strikethrough.
struct ProposalReviewCard: View {
    let proposal: MemoryProposal
    let onAccept: () -> Void
    let onReject: () -> Void
    @Environment(\.archonTheme) private var theme

    private var diff: [LineDiff.Line] {
        LineDiff.diff(old: proposal.originalContent, new: proposal.proposedContent)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: Space.sm) {
            header
            if let rationale = proposal.rationale, !rationale.isEmpty {
                Text(rationale)
                    .archonText(.caption)
                    .foregroundStyle(theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            diffBody
            actions
        }
        .padding(Space.md)
        .archonMaterial(.flatElevated, cornerRadius: Radius.card)
        .overlay {
            RoundedRectangle(cornerRadius: Radius.card, style: .continuous)
                .strokeBorder(
                    theme.borderStrong,
                    style: StrokeStyle(lineWidth: Space.hairline, dash: [4, 3])   // dashed = proposed, not applied
                )
        }
        .accessibilityElement(children: .contain)
    }

    private var header: some View {
        let counts = LineDiff.counts(diff)
        return HStack(spacing: Space.sm) {
            Image(systemName: "sparkles")
                .font(.system(size: IconSize.inline, weight: .regular))
                .foregroundStyle(theme.iconSecondary)
            VStack(alignment: .leading, spacing: 0) {
                Text("Conductor proposes an edit")
                    .archonText(.captionEmphasis)
                    .foregroundStyle(theme.textPrimary)
                Text(proposal.filename)
                    .archonText(.monoSm)
                    .foregroundStyle(theme.textSecondary)
            }
            Spacer(minLength: 0)
            Text("+\(counts.added) −\(counts.removed)")
                .archonText(.monoSm)
                .foregroundStyle(theme.textSecondary)
        }
    }

    private var diffBody: some View {
        ScrollView(.vertical) {
            VStack(alignment: .leading, spacing: 0) {
                ForEach(diff) { line in
                    HStack(alignment: .top, spacing: Space.sm) {
                        Text(prefix(line.kind))
                            .archonText(.monoSm)
                            .foregroundStyle(theme.textSecondary)
                            .frame(width: 10, alignment: .leading)
                        Text(line.text.isEmpty ? " " : line.text)
                            .archonText(.monoSm)
                            .foregroundStyle(color(line.kind))
                            .fontWeight(line.kind == .added ? .semibold : .regular)
                            .strikethrough(line.kind == .removed, color: theme.textDisabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .padding(.vertical, 1)
                }
            }
            .padding(Space.sm)
        }
        .frame(maxHeight: 220)
        .archonMaterial(.flatSurface, cornerRadius: Radius.input)
        .overlay {
            RoundedRectangle(cornerRadius: Radius.input, style: .continuous)
                .strokeBorder(theme.borderSubtle, lineWidth: Space.hairline)
        }
    }

    private var actions: some View {
        HStack(spacing: Space.sm) {
            Spacer(minLength: 0)
            Button("Reject", action: onReject)
                .archonButtonStyle(.ghost)
            Button("Accept & Save", action: onAccept)
                .archonButtonStyle(.primary)
        }
    }

    private func prefix(_ kind: LineDiff.Line.Kind) -> String {
        switch kind {
        case .added: return "+"
        case .removed: return "−"
        case .context: return ""
        }
    }

    private func color(_ kind: LineDiff.Line.Kind) -> Color {
        switch kind {
        case .added: return theme.textPrimary
        case .removed: return theme.textDisabled
        case .context: return theme.textSecondary
        }
    }
}
