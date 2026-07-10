import SwiftUI

/// The conductor-edge drawer (`.conductorEdge`): a compact, single-column "Up
/// Next" agenda over the SAME `BoardStore` as the ⌘4 board — deliberately NOT a
/// second copy of the full five-column board (§5.10 visual economy). Actionable
/// cards (everything except Done) are listed vertically, grouped by column in
/// priority order, as 12-pt rows. Strictly black/white.
struct BoardDrawerView: View {
    let store: BoardStore
    @Environment(\.archonTheme) private var theme

    /// Columns shown, most-actionable first; Done is intentionally omitted.
    nonisolated static let agendaOrder: [BoardColumn] = [.inProgress, .blocked, .review, .queued]

    private var totalActionable: Int {
        Self.agendaOrder.reduce(0) { $0 + store.cards(in: $1).count }
    }

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider().overlay(theme.hairline)
            if store.isOffline { offlineBanner }
            content
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .archonMaterial(.flatSurface)
    }

    private var header: some View {
        HStack(spacing: Space.sm) {
            Text("Up Next")
                .archonText(.captionEmphasis)
                .foregroundStyle(theme.textPrimary)
                .lineLimit(1)
            Spacer(minLength: 0)
            Text("\(totalActionable)")
                .archonText(.monoSm)
                .foregroundStyle(theme.textSecondary)
                .monospacedDigit()
                .padding(.horizontal, Space.xs)
                .background {
                    RoundedRectangle(cornerRadius: Radius.badge, style: .continuous)
                        .fill(theme.surfaceRaised)
                }
        }
        .padding(.horizontal, Space.md)
        .padding(.vertical, Space.sm)
        .archonMaterial(.flatElevated)
    }

    private var offlineBanner: some View {
        DisconnectedBanner(message: "Offline — showing the last known agenda.")
            .padding(.horizontal, Space.sm)
            .padding(.top, Space.sm)
    }

    @ViewBuilder
    private var content: some View {
        if !store.isLoaded && store.cards.isEmpty && !store.isOffline {
            SkeletonList(rows: 5)
        } else if totalActionable == 0 {
            EmptyStateView(
                systemImage: "checkmark.circle",
                title: "All clear",
                message: "No active cards. Ask the Conductor to plan work."
            )
        } else {
            ScrollView(.vertical) {
                LazyVStack(alignment: .leading, spacing: Space.md) {
                    ForEach(Self.agendaOrder) { column in
                        let cards = store.cards(in: column)
                        if !cards.isEmpty {
                            section(column: column, cards: cards)
                        }
                    }
                }
                .padding(Space.sm)
            }
        }
    }

    private func section(column: BoardColumn, cards: [Card]) -> some View {
        VStack(alignment: .leading, spacing: Space.xs) {
            HStack(spacing: Space.xs) {
                Text(column.title)
                    .archonText(.monoSm)
                    .foregroundStyle(theme.textSecondary)
                    .lineLimit(1)
                Text("\(cards.count)")
                    .archonText(.monoSm)
                    .foregroundStyle(theme.textDisabled)
                    .monospacedDigit()
                Spacer(minLength: 0)
            }
            .padding(.horizontal, Space.xs)
            ForEach(cards) { card in
                AgendaRow(card: card)
            }
        }
    }
}

/// One compact agenda row: status glyph, clamped title, and a provenance/priority
/// hint — shape/weight only, never color.
private struct AgendaRow: View {
    let card: Card
    @Environment(\.archonTheme) private var theme

    var body: some View {
        HStack(alignment: .top, spacing: Space.sm) {
            Image(systemName: card.status.systemImageName)
                .font(.system(size: IconSize.caption, weight: .medium))
                .foregroundStyle(theme.iconSecondary)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 2) {
                Text(BoardFormat.clampTitle(card.title, max: 60))
                    .archonText(.caption)
                    .foregroundStyle(theme.textPrimary)
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
                HStack(spacing: Space.xs) {
                    if card.priority == .high {
                        Image(systemName: "chevron.up.2")
                            .font(.system(size: IconSize.caption, weight: .semibold))
                            .foregroundStyle(theme.iconSecondary)
                            .accessibilityLabel("High priority")
                    }
                    Text(card.provenance == .conductor ? "Conductor" : "You")
                        .archonText(.monoSm)
                        .foregroundStyle(theme.textSecondary)
                }
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, Space.sm)
        .padding(.vertical, Space.xs)
        .frame(maxWidth: .infinity, alignment: .leading)
        .archonMaterial(.flatElevated, cornerRadius: Radius.input)
        .overlay {
            RoundedRectangle(cornerRadius: Radius.input, style: .continuous)
                .strokeBorder(theme.borderSubtle, lineWidth: Space.hairline)
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(card.title), \(card.status.label), \(card.column.title)")
    }
}
