import SwiftUI

/// The Memory main pane (`.main(.memory)`): a per-directory list of discovered
/// `CLAUDE.md`/`AGENTS.md` + overlay files (contract §2.6, REQ-UX-080) on the
/// left, and the read/edit surface on the right (REQ-UX-081/082). Writes are
/// user-initiated only (addendum §A3). Self-contained; strictly B/W.
struct MemoryView: View {
    @Bindable var store: MemoryStore
    @State private var creating = false
    @State private var newFilename = ""
    @State private var newScope = ""
    @Environment(\.archonTheme) private var theme

    init(store: MemoryStore) {
        self.store = store
    }

    var body: some View {
        HSplitView {
            sidebar
                .frame(minWidth: 220, idealWidth: 260, maxWidth: 340)
            detail
                .frame(minWidth: 420, maxWidth: .infinity)
        }
        .background(theme.background)
    }

    // MARK: - Left: file list

    private var sidebar: some View {
        VStack(spacing: 0) {
            HStack(spacing: Space.sm) {
                Text("Memory")
                    .archonText(.captionEmphasis)
                    .foregroundStyle(theme.textPrimary)
                Spacer(minLength: 0)
                Button {
                    newScope = store.defaultScopeDir ?? ""
                    newFilename = ""
                    creating = true
                } label: {
                    Image(systemName: "plus").font(.system(size: 12, weight: .semibold))
                }
                .buttonStyle(.plain)
                .foregroundStyle(theme.iconSecondary)
                .disabled(store.isOffline)
                .accessibilityLabel("New memory file")
                .popover(isPresented: $creating, arrowEdge: .bottom) { createPopover }
            }
            .padding(.horizontal, Space.md)
            .padding(.vertical, Space.sm)
            .archonMaterial(.flatElevated)
            Divider().overlay(theme.hairline)
            list
        }
        .archonMaterial(.glassSidebar)
    }

    @ViewBuilder
    private var list: some View {
        if !store.isLoaded {
            SkeletonList(rows: 6)
        } else if store.scopes.allSatisfy({ $0.files.isEmpty }) {
            EmptyStateView(
                systemImage: "doc.text",
                title: "No memory files",
                message: "Create a CLAUDE.md or AGENTS.md to guide the agents in this project."
            )
        } else {
            ScrollView(.vertical) {
                LazyVStack(alignment: .leading, spacing: Space.md) {
                    ForEach(store.scopes) { scope in
                        if !scope.files.isEmpty {
                            scopeSection(scope)
                        }
                    }
                }
                .padding(Space.sm)
            }
        }
    }

    private func scopeSection(_ scope: MemoryScope) -> some View {
        VStack(alignment: .leading, spacing: Space.xs) {
            Text(scopeTitle(scope.scopeDir))
                .archonText(.monoSm)
                .foregroundStyle(theme.textSecondary)
                .lineLimit(1)
                .truncationMode(.head)
                .padding(.horizontal, Space.sm)
            ForEach(scope.files) { file in
                fileRow(file)
            }
        }
    }

    private func fileRow(_ file: MemoryFile) -> some View {
        Button {
            Task { await store.select(file) }
        } label: {
            ArchonListRow(isSelected: store.selectedFile?.id == file.id) {
                Image(systemName: kindGlyph(file.kind))
                    .font(.system(size: IconSize.inline, weight: .regular))
                    .foregroundStyle(theme.iconSecondary)
            } content: {
                HStack(spacing: Space.xs) {
                    Text(file.filename)
                        .archonText(.body)
                        .foregroundStyle(theme.textPrimary)
                        .lineLimit(1)
                    if !store.proposals(for: file).isEmpty {
                        Image(systemName: "sparkles")
                            .font(.system(size: 9, weight: .regular))
                            .foregroundStyle(theme.iconSecondary)
                            .accessibilityLabel("Has a Conductor proposal")
                    }
                    if file.location == .overlay {
                        Text("overlay")
                            .archonText(.monoSm)
                            .foregroundStyle(theme.textDisabled)
                    }
                }
            }
        }
        .buttonStyle(.plain)
    }

    // MARK: - Right: editor

    @ViewBuilder
    private var detail: some View {
        if let file = store.selectedFile {
            VStack(spacing: 0) {
                if store.isOffline {
                    DisconnectedBanner(message: "Offline — this file is read-only until reconnect.")
                        .padding(Space.md)
                }
                if let note = errorNote {
                    inlineError(note)
                }
                MemoryEditor(store: store, file: file)
            }
        } else {
            EmptyStateView(
                systemImage: "doc.text.magnifyingglass",
                title: "Select a memory file",
                message: "Pick a file on the left to read or edit it. Nothing is written until you press Save."
            )
        }
    }

    private func inlineError(_ message: String) -> some View {
        HStack(spacing: Space.sm) {
            Image(systemName: "exclamationmark.circle")
                .font(.system(size: IconSize.inline, weight: .medium))
                .foregroundStyle(theme.iconSecondary)
            Text(message)
                .archonText(.caption)
                .foregroundStyle(theme.textSecondary)
            Spacer(minLength: 0)
            Button { store.clearError() } label: {
                Image(systemName: "xmark").font(.system(size: 10, weight: .semibold))
            }
            .buttonStyle(.plain)
            .foregroundStyle(theme.iconSecondary)
        }
        .padding(.horizontal, Space.md)
        .padding(.vertical, Space.sm)
        .archonMaterial(.flatElevated, cornerRadius: Radius.input)
        .padding(.horizontal, Space.md)
        .padding(.top, Space.sm)
    }

    private var errorNote: String? {
        switch store.lastError {
        case .conflict: return "The file changed elsewhere — reloaded the latest revision. Re-apply your edits and Save."
        case .conductorForbidden: return "That write was blocked: only you can save memory files."
        case .writeDenied: return "This file can't be written (access class)."
        case .tooLarge: return "That file is too large to save."
        case .quota: return "This directory's memory quota is full."
        case .pathEscape: return "That path is outside the project."
        case .offline: return "You're offline — the change wasn't saved."
        case .message(let text): return text
        case nil: return nil
        }
    }

    // MARK: - Create popover

    private var createPopover: some View {
        VStack(alignment: .leading, spacing: Space.sm) {
            Text("New Memory File")
                .archonText(.captionEmphasis)
                .foregroundStyle(theme.textSecondary)
            if !store.scopes.isEmpty {
                Picker("Directory", selection: $newScope) {
                    ForEach(store.scopes) { scope in
                        Text(scopeTitle(scope.scopeDir)).tag(scope.scopeDir)
                    }
                }
                .labelsHidden()
            }
            TextField("Filename (e.g. CLAUDE.md)", text: $newFilename)
                .textFieldStyle(.plain)
                .archonText(.body)
                .padding(Space.sm)
                .archonMaterial(.flatSurface, cornerRadius: Radius.input)
                .overlay {
                    RoundedRectangle(cornerRadius: Radius.input, style: .continuous)
                        .strokeBorder(theme.borderSubtle, lineWidth: Space.hairline)
                }
            HStack {
                Spacer()
                Button("Cancel") { creating = false }
                    .archonButtonStyle(.ghost)
                Button("Create") {
                    let filename = newFilename.trimmingCharacters(in: .whitespacesAndNewlines)
                    let scope = newScope.isEmpty ? (store.defaultScopeDir ?? "") : newScope
                    guard !filename.isEmpty, !scope.isEmpty else { return }
                    creating = false
                    Task { await store.createFile(scopeDir: scope, filename: filename) }
                }
                .archonButtonStyle(.primary)
                .disabled(newFilename.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
        }
        .padding(Space.md)
        .frame(width: 300)
    }

    // MARK: - Helpers

    private func kindGlyph(_ kind: MemoryKind) -> String {
        switch kind {
        case .claude: return "brain"
        case .agents: return "person.2"
        case .overlay: return "square.stack.3d.up"
        case .unknown: return "doc"
        }
    }

    private func scopeTitle(_ path: String) -> String {
        let name = (path as NSString).lastPathComponent
        return name.isEmpty ? path : name
    }
}
