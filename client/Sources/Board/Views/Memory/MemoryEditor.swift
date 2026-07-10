import SwiftUI

/// The central memory surface for the selected file (REQ-UX-081): a monospaced
/// editor with a Markdown-render toggle. Saving is an EXPLICIT user action
/// (addendum §A3 — never auto-write); a dirty indicator shows unsaved edits.
/// Any pending Conductor proposals for this file appear as review cards above.
struct MemoryEditor: View {
    @Bindable var store: MemoryStore
    let file: MemoryFile
    @State private var rendered = false
    @Environment(\.archonTheme) private var theme

    private var proposals: [MemoryProposal] { store.proposals(for: file) }

    var body: some View {
        VStack(spacing: 0) {
            toolbar
            Divider().overlay(theme.hairline)
            ScrollView(.vertical) {
                VStack(alignment: .leading, spacing: Space.md) {
                    ForEach(proposals) { proposal in
                        ProposalReviewCard(
                            proposal: proposal,
                            onAccept: { Task { await store.acceptProposal(proposal) } },
                            onReject: { store.rejectProposal(proposal) }
                        )
                    }
                    editorSurface
                }
                .padding(Space.md)
            }
        }
        .background(theme.background)
    }

    private var toolbar: some View {
        HStack(spacing: Space.sm) {
            VStack(alignment: .leading, spacing: 0) {
                HStack(spacing: Space.xs) {
                    Text(file.filename)
                        .archonText(.bodyEmphasis)
                        .foregroundStyle(theme.textPrimary)
                    if store.isDirty {
                        Circle()
                            .fill(theme.textPrimary)
                            .frame(width: 6, height: 6)
                            .accessibilityLabel("Unsaved changes")
                    }
                }
                Text(file.scopeDir)
                    .archonText(.monoSm)
                    .foregroundStyle(theme.textSecondary)
                    .lineLimit(1)
                    .truncationMode(.middle)
            }
            Spacer(minLength: 0)

            Toggle(isOn: $rendered) {
                Image(systemName: rendered ? "doc.richtext" : "chevron.left.forwardslash.chevron.right")
            }
            .toggleStyle(.button)
            .buttonStyle(.plain)
            .foregroundStyle(theme.iconSecondary)
            .help(rendered ? "Show source" : "Render Markdown")
            .accessibilityLabel(rendered ? "Show plain source" : "Render Markdown")

            if store.isDirty {
                Button("Revert") { store.revertEdits() }
                    .archonButtonStyle(.ghost)
            }
            Button {
                Task { await store.save() }
            } label: {
                if store.isSaving {
                    Text("Saving…")
                } else {
                    Text("Save")
                }
            }
            .archonButtonStyle(.primary)
            .disabled(!store.isDirty || store.isOffline || store.isSaving || !file.editable)
            .keyboardShortcut("s", modifiers: .command)
        }
        .padding(Space.md)
        .archonMaterial(.flatElevated)
    }

    @ViewBuilder
    private var editorSurface: some View {
        if rendered {
            MemoryMarkdownView(text: store.editorText)
                .padding(Space.md)
                .frame(maxWidth: .infinity, alignment: .leading)
                .archonMaterial(.flatSurface, cornerRadius: Radius.card)
                .overlay {
                    RoundedRectangle(cornerRadius: Radius.card, style: .continuous)
                        .strokeBorder(theme.borderSubtle, lineWidth: Space.hairline)
                }
        } else {
            TextEditor(text: $store.editorText)
                .scrollContentBackground(.hidden)
                .archonText(.monoBody)
                .foregroundStyle(theme.textPrimary)
                .frame(minHeight: 320)
                .padding(Space.sm)
                .archonMaterial(.flatSurface, cornerRadius: Radius.card)
                .overlay {
                    RoundedRectangle(cornerRadius: Radius.card, style: .continuous)
                        .strokeBorder(theme.borderSubtle, lineWidth: Space.hairline)
                }
                .disabled(!file.editable)
        }
    }
}
