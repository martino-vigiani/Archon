import SwiftUI

/// A single kanban card (contract §2.5 / REQ-UX-051): title, body preview,
/// provenance badge, status badge, session link, timestamps. Strictly B/W —
/// status/provenance/priority differ by shape/weight/pattern only. Conductor
/// changes arrive with a subtle spring emphasis (`isAnimating`, §5.7).
struct CardView: View {
    let card: Card
    var isAnimating: Bool = false
    var isSelected: Bool = false
    let onSelect: () -> Void
    let onCommitEdit: (String, String, CardPriority) -> Void
    let onDelete: () -> Void

    @State private var isEditing = false
    @State private var confirmingDelete = false
    @FocusState private var isFocused: Bool
    @Environment(\.archonTheme) private var theme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var priorityGlyph: String? {
        switch card.priority {
        case .high: return "chevron.up.2"
        case .low: return "chevron.down"
        case .normal, .unknown: return nil
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: Space.sm) {
            header
            if let body = card.body, !body.isEmpty {
                Text(body)
                    .archonText(.caption)
                    .foregroundStyle(theme.textSecondary)
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
            }
            HStack(spacing: Space.sm) {
                ProvenanceBadge(provenance: card.provenance)
                Spacer(minLength: 0)
                Text(BoardFormat.sessionLabel(card.sessionId))
                    .archonText(.monoSm)
                    .foregroundStyle(theme.textSecondary)
                    .lineLimit(1)
            }
            footer
            if confirmingDelete { deleteConfirmRow }
        }
        .padding(Space.md)
        .archonMaterial(.flatElevated, cornerRadius: Radius.card)
        .overlay {
            RoundedRectangle(cornerRadius: Radius.card, style: .continuous)
                .strokeBorder(borderColor, lineWidth: borderWidth)
        }
        .scaleEffect(isAnimating && !reduceMotion ? 1.015 : 1.0)
        .archonMotion(.kanbanDragRelease, value: isAnimating)
        .contentShape(Rectangle())
        .focusable()
        .focusEffectDisabled()
        .focused($isFocused)
        .onTapGesture(count: 2) { isEditing = true }
        .onTapGesture { onSelect() }
        .onKeyPress(.return) { isEditing = true; return .handled }
        .onKeyPress(.space) { onSelect(); return .handled }
        .popover(isPresented: $isEditing, arrowEdge: .trailing) {
            CardEditor(
                title: card.title,
                body: card.body ?? "",
                priority: card.priority,
                onSave: { title, body, priority in
                    isEditing = false
                    onCommitEdit(title, body, priority)
                },
                onCancel: { isEditing = false }
            )
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(accessibilityLabel)
        .accessibilityHint("Double-tap to edit.")
    }

    private var borderColor: Color {
        if isFocused || isSelected { return theme.selectionBorder }
        return isAnimating ? theme.borderStrong : theme.borderSubtle
    }

    private var borderWidth: CGFloat {
        if isFocused || isSelected { return 2 }
        return isAnimating ? 1.5 : Space.hairline
    }

    private var header: some View {
        HStack(alignment: .top, spacing: Space.sm) {
            if let priorityGlyph {
                Image(systemName: priorityGlyph)
                    .font(.system(size: IconSize.caption, weight: .semibold))
                    .foregroundStyle(theme.iconSecondary)
                    .accessibilityLabel(card.priority == .high ? "High priority" : "Low priority")
            }
            Text(BoardFormat.clampTitle(card.title))
                .archonText(.bodyEmphasis)
                .foregroundStyle(theme.textPrimary)
                .lineLimit(2)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
            StatusBadge(status: card.status)
        }
    }

    private var footer: some View {
        HStack(spacing: Space.sm) {
            Image(systemName: "clock")
                .font(.system(size: IconSize.caption, weight: .regular))
                .foregroundStyle(theme.iconSecondary)
            Text(BoardFormat.shortTime(card.createdAt))
                .archonText(.monoSm)
                .foregroundStyle(theme.textSecondary)
            Spacer(minLength: 0)
            Button { isEditing = true } label: {
                Image(systemName: "pencil").font(.system(size: IconSize.caption, weight: .medium))
            }
            .buttonStyle(.plain)
            .foregroundStyle(theme.iconSecondary)
            .accessibilityLabel("Edit card")

            Button { confirmingDelete = true } label: {
                Image(systemName: "trash").font(.system(size: IconSize.caption, weight: .medium))
            }
            .buttonStyle(.plain)
            .foregroundStyle(theme.iconSecondary)
            .accessibilityLabel("Delete card")
        }
    }

    private var deleteConfirmRow: some View {
        HStack(spacing: Space.sm) {
            Text("Delete this card?")
                .archonText(.caption)
                .foregroundStyle(theme.textPrimary)
            Spacer(minLength: 0)
            Button("Cancel") { confirmingDelete = false }
                .archonButtonStyle(.ghost)
            Button("Delete") {
                confirmingDelete = false
                onDelete()
            }
            .archonButtonStyle(.secondary)
            .keyboardShortcut(.delete, modifiers: [])
        }
        .padding(.top, Space.xs)
    }

    private var accessibilityLabel: String {
        "\(card.title). Status \(card.status.label). \(card.column.title). Created by \(card.provenance == .conductor ? "Conductor" : "you")."
    }
}
