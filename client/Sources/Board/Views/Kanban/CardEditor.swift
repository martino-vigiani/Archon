import SwiftUI

/// Inline, non-modal card editor (REQ-UX-053: create/edit without a modal
/// sheet). Presented in a popover anchored to the card; strictly achromatic.
struct CardEditor: View {
    @State private var title: String
    @State private var bodyText: String
    @State private var priority: CardPriority
    let onSave: (String, String, CardPriority) -> Void
    let onCancel: () -> Void
    @Environment(\.archonTheme) private var theme
    @FocusState private var titleFocused: Bool

    init(
        title: String,
        body: String,
        priority: CardPriority,
        onSave: @escaping (String, String, CardPriority) -> Void,
        onCancel: @escaping () -> Void
    ) {
        _title = State(initialValue: title)
        _bodyText = State(initialValue: body)
        _priority = State(initialValue: priority == .unknown ? .normal : priority)
        self.onSave = onSave
        self.onCancel = onCancel
    }

    var body: some View {
        VStack(alignment: .leading, spacing: Space.sm) {
            Text("Edit Card")
                .archonText(.captionEmphasis)
                .foregroundStyle(theme.textSecondary)

            TextField("Title", text: $title)
                .textFieldStyle(.plain)
                .archonText(.bodyEmphasis)
                .foregroundStyle(theme.textPrimary)
                .focused($titleFocused)
                .padding(Space.sm)
                .archonMaterial(.flatSurface, cornerRadius: Radius.input)
                .overlay {
                    RoundedRectangle(cornerRadius: Radius.input, style: .continuous)
                        .strokeBorder(theme.borderSubtle, lineWidth: Space.hairline)
                }

            TextEditor(text: $bodyText)
                .scrollContentBackground(.hidden)
                .archonText(.body)
                .foregroundStyle(theme.textPrimary)
                .frame(minHeight: 64, maxHeight: 120)
                .padding(Space.xs)
                .archonMaterial(.flatSurface, cornerRadius: Radius.input)
                .overlay {
                    RoundedRectangle(cornerRadius: Radius.input, style: .continuous)
                        .strokeBorder(theme.borderSubtle, lineWidth: Space.hairline)
                }

            Picker("Priority", selection: $priority) {
                Text("Low").tag(CardPriority.low)
                Text("Normal").tag(CardPriority.normal)
                Text("High").tag(CardPriority.high)
            }
            .pickerStyle(.segmented)
            .labelsHidden()

            HStack(spacing: Space.sm) {
                Spacer()
                Button("Cancel", action: onCancel)
                    .archonButtonStyle(.ghost)
                    .keyboardShortcut(.cancelAction)
                Button("Save") {
                    let trimmed = title.trimmingCharacters(in: .whitespacesAndNewlines)
                    guard !trimmed.isEmpty else { return }
                    onSave(trimmed, bodyText, priority)
                }
                .archonButtonStyle(.primary)
                .keyboardShortcut(.defaultAction)
                .disabled(title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
        }
        .padding(Space.md)
        .frame(width: 300)
        .onAppear { titleFocused = true }
    }
}
