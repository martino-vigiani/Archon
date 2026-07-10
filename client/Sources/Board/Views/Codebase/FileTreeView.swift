import SwiftUI

/// A VS Code-like, lazily-loaded directory tree (REQ-UX-070). Read-only: no
/// rename/create/delete affordances. `.gitignore`-ignored nodes are dimmed
/// (never colored); files changed during the current run carry a "•" indicator
/// (REQ-UX-071). Arrow keys traverse; →/← expand/collapse; Return opens a file
/// in the singular central preview.
struct FileTreeView: View {
    let store: CodebaseStore
    @State private var focusedId: String?
    @FocusState private var treeFocused: Bool
    @Environment(\.archonTheme) private var theme

    private struct Row: Identifiable {
        let node: FileNode
        let depth: Int
        var id: String { node.id }
    }

    private var visibleRows: [Row] {
        guard let root = store.root else { return [] }
        var rows: [Row] = []
        func walk(_ node: FileNode, depth: Int) {
            rows.append(Row(node: node, depth: depth))
            if node.isDirectory, node.isExpanded, let children = node.children {
                for child in children { walk(child, depth: depth + 1) }
            }
        }
        // The root itself is shown as depth 0; its children indent from there.
        if let children = root.children {
            for child in children { walk(child, depth: 0) }
        }
        return rows
    }

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider().overlay(theme.hairline)
            content
        }
        .archonMaterial(.glassSidebar)
    }

    private var header: some View {
        HStack(spacing: Space.sm) {
            Image(systemName: "folder")
                .font(.system(size: IconSize.inline, weight: .regular))
                .foregroundStyle(theme.iconSecondary)
            Text(store.root?.name ?? store.overview.name)
                .archonText(.captionEmphasis)
                .foregroundStyle(theme.textPrimary)
                .lineLimit(1)
                .truncationMode(.middle)
            Spacer(minLength: 0)
        }
        .padding(.horizontal, Space.md)
        .padding(.vertical, Space.sm)
        .archonMaterial(.flatElevated)
    }

    @ViewBuilder
    private var content: some View {
        if store.isLoading && store.root == nil {
            SkeletonList(rows: 8)
        } else if store.root == nil {
            EmptyStateView(
                systemImage: "folder",
                title: "No project open",
                message: "Open a project directory to browse its files."
            )
        } else if visibleRows.isEmpty {
            EmptyStateView(systemImage: "folder", title: "Empty directory", message: nil)
        } else {
            ScrollViewReader { proxy in
                ScrollView(.vertical) {
                    LazyVStack(spacing: 0) {
                        ForEach(visibleRows) { row in
                            FileTreeRow(
                                node: row.node,
                                depth: row.depth,
                                isFocused: focusedId == row.node.id,
                                isSelected: store.selection?.id == row.node.id,
                                onActivate: { activate(row.node) }
                            )
                            .id(row.node.id)
                        }
                    }
                    .padding(.vertical, Space.xs)
                }
                .focusable()
                .focused($treeFocused)
                .onMoveCommand { direction in
                    handleMove(direction, proxy: proxy)
                }
            }
        }
    }

    private func activate(_ node: FileNode) {
        focusedId = node.id
        Task { await store.select(node) }
    }

    private func handleMove(_ direction: MoveCommandDirection, proxy: ScrollViewProxy) {
        let rows = visibleRows
        guard !rows.isEmpty else { return }
        let currentIndex = rows.firstIndex { $0.node.id == focusedId } ?? 0
        switch direction {
        case .up:
            let next = max(0, currentIndex - 1)
            focusedId = rows[next].node.id
            proxy.scrollTo(rows[next].node.id)
        case .down:
            let next = min(rows.count - 1, currentIndex + 1)
            focusedId = rows[next].node.id
            proxy.scrollTo(rows[next].node.id)
        case .right:
            let node = rows[currentIndex].node
            if node.isDirectory && !node.isExpanded {
                Task { await store.toggleExpand(node) }
            }
        case .left:
            let node = rows[currentIndex].node
            if node.isDirectory && node.isExpanded {
                Task { await store.toggleExpand(node) }
            }
        @unknown default:
            break
        }
    }
}

/// A single tree row. Selection uses the achromatic selection fill; gitignored
/// nodes dim; changed files show a "•".
private struct FileTreeRow: View {
    let node: FileNode
    let depth: Int
    let isFocused: Bool
    let isSelected: Bool
    let onActivate: () -> Void
    @Environment(\.archonTheme) private var theme

    private var glyph: String {
        if node.isDirectory { return node.isExpanded ? "folder" : "folder.fill" }
        return "doc"
    }

    var body: some View {
        Button(action: onActivate) {
            HStack(spacing: Space.xs) {
                if node.isDirectory {
                    Image(systemName: "chevron.right")
                        .font(.system(size: 9, weight: .semibold))
                        .foregroundStyle(theme.iconSecondary)
                        .rotationEffect(.degrees(node.isExpanded ? 90 : 0))
                        .frame(width: 10)
                } else {
                    Color.clear.frame(width: 10)
                }
                Image(systemName: glyph)
                    .font(.system(size: IconSize.inline, weight: .regular))
                    .foregroundStyle(theme.iconSecondary)
                Text(node.name)
                    .archonText(.caption)
                    .foregroundStyle(theme.textPrimary)
                    .lineLimit(1)
                    .truncationMode(.middle)
                if node.isChangedThisRun {
                    Text("•")
                        .archonText(.captionEmphasis)
                        .foregroundStyle(theme.textPrimary)
                        .accessibilityLabel("Changed this run")
                }
                Spacer(minLength: 0)
            }
            .padding(.leading, CGFloat(depth) * 14 + Space.sm)
            .padding(.trailing, Space.sm)
            .padding(.vertical, 3)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background {
                RoundedRectangle(cornerRadius: Radius.input, style: .continuous)
                    .fill(isSelected ? theme.selectionFill : Color.clear)
            }
            .overlay {
                if isFocused && !isSelected {
                    RoundedRectangle(cornerRadius: Radius.input, style: .continuous)
                        .strokeBorder(theme.borderSubtle, lineWidth: Space.hairline)
                }
            }
            .contentShape(Rectangle())
            .opacity(node.isGitignored ? 0.45 : 1.0)
        }
        .buttonStyle(.plain)
        .accessibilityLabel("\(node.name)\(node.isDirectory ? ", folder" : "")\(node.isChangedThisRun ? ", changed" : "")\(node.isGitignored ? ", ignored" : "")")
    }
}
