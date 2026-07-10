import SwiftUI

/// One of the five fixed columns (REQ-UX-050). Vertically scrolls its cards
/// (0–100+/column without horizontal overflow, REQ-UX-056), accepts drag-drop
/// moves/reorders, and offers an inline "add card" field.
struct KanbanColumnView: View {
    let store: BoardStore
    let column: BoardColumn
    @Binding var selectedCardId: String?

    @State private var newTitle: String = ""
    @State private var isDropTargeted = false
    @Environment(\.archonTheme) private var theme

    private var columnCards: [Card] { store.cards(in: column) }

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider().overlay(theme.hairline)
            cardList
            addRow
        }
        .frame(minWidth: 240, maxWidth: .infinity)
        .background {
            RoundedRectangle(cornerRadius: Radius.card, style: .continuous)
                .fill(isDropTargeted ? theme.selectionFill : Color.clear)
        }
        .overlay {
            RoundedRectangle(cornerRadius: Radius.card, style: .continuous)
                .strokeBorder(theme.borderSubtle, lineWidth: Space.hairline)
        }
        // Column-level drop = append to the end (covers gaps / empty column).
        .dropDestination(for: String.self) { ids, _ in
            guard let cardId = ids.first else { return false }
            move(cardId, toOrdinal: columnCards.count)
            return true
        } isTargeted: { isDropTargeted = $0 }
    }

    private var header: some View {
        HStack(spacing: Space.sm) {
            Text(column.title)
                .archonText(.captionEmphasis)
                .foregroundStyle(theme.textPrimary)
            Text("\(columnCards.count)")
                .archonText(.monoSm)
                .foregroundStyle(theme.textSecondary)
                .padding(.horizontal, Space.xs)
                .background {
                    RoundedRectangle(cornerRadius: Radius.badge, style: .continuous)
                        .fill(theme.surfaceRaised)
                }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, Space.md)
        .padding(.vertical, Space.sm)
        .archonMaterial(.flatElevated)
    }

    @ViewBuilder
    private var cardList: some View {
        if columnCards.isEmpty {
            VStack {
                Spacer(minLength: 0)
                Text("No cards")
                    .archonText(.caption)
                    .foregroundStyle(theme.textDisabled)
                Spacer(minLength: 0)
            }
            .frame(maxWidth: .infinity, minHeight: 80)
            .contentShape(Rectangle())
        } else {
            ScrollView(.vertical) {
                LazyVStack(spacing: Space.sm) {
                    ForEach(columnCards) { card in
                        CardView(
                            card: card,
                            isAnimating: store.animatingCardIds.contains(card.cardId),
                            isSelected: selectedCardId == card.cardId,
                            onSelect: { selectedCardId = card.cardId },
                            onCommitEdit: { title, body, priority in
                                Task { await store.editCard(card.cardId, title: title, body: body, priority: priority) }
                            },
                            onDelete: { Task { await store.delete(cardId: card.cardId) } }
                        )
                        .draggable(card.cardId)
                        // Card-level drop = insert before this card.
                        .dropDestination(for: String.self) { ids, _ in
                            guard let draggedId = ids.first, draggedId != card.cardId else { return false }
                            move(draggedId, toOrdinal: card.ordinal)
                            return true
                        }
                    }
                }
                .padding(Space.sm)
            }
        }
    }

    private var addRow: some View {
        HStack(spacing: Space.sm) {
            Image(systemName: "plus")
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(theme.iconSecondary)
            TextField("Add card", text: $newTitle)
                .textFieldStyle(.plain)
                .archonText(.caption)
                .foregroundStyle(theme.textPrimary)
                .onSubmit(submitNewCard)
                .disabled(store.isOffline)
        }
        .padding(.horizontal, Space.md)
        .padding(.vertical, Space.sm)
        .archonMaterial(.flatElevated)
        .accessibilityLabel("Add a card to \(column.title)")
    }

    private func submitNewCard() {
        let trimmed = newTitle.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        newTitle = ""
        Task { await store.createCard(title: trimmed, column: column) }
    }

    private func move(_ cardId: String, toOrdinal: Int) {
        Task { await store.move(cardId: cardId, toColumn: column, toOrdinal: toOrdinal) }
    }
}
