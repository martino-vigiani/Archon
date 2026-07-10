import SwiftUI

/// The kanban board main pane (`.main(.kanban)`): five fixed columns
/// (REQ-UX-050), live-folding `kanban_updated` deltas, optimistic user edits,
/// and calm offline behaviour (addendum §A4 — stale data stays visible with a
/// subtle offline banner). Strictly black/white.
struct KanbanBoardView: View {
    @State private var selectedCardId: String?
    let store: BoardStore
    @Environment(\.archonTheme) private var theme

    init(store: BoardStore) {
        self.store = store
    }

    var body: some View {
        VStack(spacing: 0) {
            if store.isOffline { offlineBanner }
            if let note = errorNote { errorBanner(note) }
            content
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(theme.background)
        .onDeleteCommand(perform: deleteSelected)
    }

    @ViewBuilder
    private var content: some View {
        if !store.isLoaded && store.cards.isEmpty && !store.isOffline {
            SkeletonBoard()
        } else if store.cards.isEmpty {
            EmptyStateView(
                systemImage: "rectangle.split.3x1",
                title: "No cards yet",
                message: "Add a card to any column, or ask the Conductor to plan work."
            )
        } else {
            HStack(alignment: .top, spacing: Space.sm) {
                ForEach(BoardColumn.allCases) { column in
                    KanbanColumnView(
                        store: store,
                        column: column,
                        selectedCardId: $selectedCardId
                    )
                }
            }
            .padding(Space.md)
        }
    }

    private var offlineBanner: some View {
        DisconnectedBanner(message: "Offline — showing the last board state (read-only).")
            .padding(.horizontal, Space.md)
            .padding(.top, Space.sm)
    }

    private func errorBanner(_ message: String) -> some View {
        HStack(spacing: Space.sm) {
            Image(systemName: "arrow.triangle.2.circlepath")
                .font(.system(size: IconSize.inline, weight: .medium))
                .foregroundStyle(theme.iconSecondary)
            Text(message)
                .archonText(.caption)
                .foregroundStyle(theme.textSecondary)
            Spacer(minLength: 0)
        }
        .padding(.horizontal, Space.md)
        .padding(.vertical, Space.sm)
        .archonMaterial(.flatElevated, cornerRadius: Radius.input)
        .padding(.horizontal, Space.md)
        .padding(.top, Space.sm)
        .transition(.opacity)
    }

    private var errorNote: String? {
        switch store.lastError {
        case .conflictReconciled: return "The board changed elsewhere — reloaded to the latest."
        case .illegalMove: return "That move isn't allowed for this column."
        case .offline: return "You're offline — that change wasn't applied."
        case .message(let text): return text
        case nil: return nil
        }
    }

    private func deleteSelected() {
        guard let cardId = selectedCardId else { return }
        Task { await store.delete(cardId: cardId) }
        selectedCardId = nil
    }
}

/// Achromatic skeleton for the board's initial load (REQ-UX-091). No spinner.
private struct SkeletonBoard: View {
    var body: some View {
        HStack(alignment: .top, spacing: Space.sm) {
            ForEach(BoardColumn.allCases) { _ in
                VStack(spacing: Space.sm) {
                    SkeletonView().frame(height: 28)
                    ForEach(0..<3, id: \.self) { _ in
                        SkeletonView(cornerRadius: Radius.card).frame(height: 84)
                    }
                    Spacer(minLength: 0)
                }
                .frame(maxWidth: .infinity)
            }
        }
        .padding(Space.md)
    }
}
