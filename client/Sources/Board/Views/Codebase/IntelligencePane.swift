import SwiftUI

/// The singular "personal intelligence" surface (§4.8 / REQ-UX-073): exactly one
/// pane. With a file selected it shows a read-only, monospaced, line-numbered
/// preview (REQ-UX-072); with nothing selected it shows a calm project overview.
/// No editing affordances anywhere.
struct IntelligencePane: View {
    let store: CodebaseStore
    @Environment(\.archonTheme) private var theme

    var body: some View {
        Group {
            if let node = store.selection, !node.isDirectory {
                preview(node)
            } else {
                overview
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(theme.background)
    }

    // MARK: - File preview (read-only)

    private func preview(_ node: FileNode) -> some View {
        VStack(spacing: 0) {
            previewHeader(node)
            Divider().overlay(theme.hairline)
            previewBody
        }
    }

    private func previewHeader(_ node: FileNode) -> some View {
        HStack(spacing: Space.sm) {
            Image(systemName: "doc.text")
                .font(.system(size: IconSize.inline, weight: .regular))
                .foregroundStyle(theme.iconSecondary)
            VStack(alignment: .leading, spacing: 0) {
                Text(node.name)
                    .archonText(.bodyEmphasis)
                    .foregroundStyle(theme.textPrimary)
                Text(node.relativePath)
                    .archonText(.monoSm)
                    .foregroundStyle(theme.textSecondary)
                    .lineLimit(1)
                    .truncationMode(.middle)
            }
            Spacer(minLength: 0)
            Label("Read-only", systemImage: "lock")
                .labelStyle(.titleAndIcon)
                .archonText(.monoSm)
                .foregroundStyle(theme.textSecondary)
        }
        .padding(Space.md)
        .archonMaterial(.flatElevated)
    }

    @ViewBuilder
    private var previewBody: some View {
        if let preview = store.preview {
            if preview.isBinary {
                EmptyStateView(
                    systemImage: "cube.box",
                    title: "Binary file",
                    message: "This file isn't text, so there's nothing to preview."
                )
            } else if let text = preview.text {
                CodePreview(text: text, truncated: preview.truncated)
            } else {
                EmptyStateView(systemImage: "doc", title: "Empty file", message: nil)
            }
        } else {
            SkeletonList(rows: 10)
        }
    }

    // MARK: - Project overview

    private var overview: some View {
        let summary = store.overview
        return VStack(alignment: .leading, spacing: Space.lg) {
            VStack(alignment: .leading, spacing: Space.xs) {
                Text(summary.name)
                    .archonText(.title1)
                    .foregroundStyle(theme.textPrimary)
                Text(summary.path)
                    .archonText(.monoSm)
                    .foregroundStyle(theme.textSecondary)
                    .lineLimit(1)
                    .truncationMode(.middle)
            }

            HStack(spacing: Space.md) {
                overviewStat(title: "Active", value: "\(summary.liveSessionCount)", glyph: "play.circle")
                overviewStat(title: "Sessions", value: "\(summary.totalSessions)", glyph: "square.grid.2x2")
                if let branch = summary.branch {
                    overviewStat(title: "Branch", value: branch, glyph: "arrow.triangle.branch")
                }
            }

            if let last = summary.lastActivityAt {
                HStack(spacing: Space.sm) {
                    Image(systemName: "clock")
                        .font(.system(size: IconSize.inline, weight: .regular))
                        .foregroundStyle(theme.iconSecondary)
                    Text("Last activity \(BoardFormat.shortTime(last))")
                        .archonText(.caption)
                        .foregroundStyle(theme.textSecondary)
                }
            }

            Text("Select a file on the left to preview it here.")
                .archonText(.body)
                .foregroundStyle(theme.textSecondary)

            Spacer(minLength: 0)
        }
        .padding(Space.xl)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }

    private func overviewStat(title: String, value: String, glyph: String) -> some View {
        VStack(alignment: .leading, spacing: Space.xs) {
            HStack(spacing: Space.xs) {
                Image(systemName: glyph)
                    .font(.system(size: IconSize.inline, weight: .regular))
                    .foregroundStyle(theme.iconSecondary)
                Text(title)
                    .archonText(.caption)
                    .foregroundStyle(theme.textSecondary)
            }
            Text(value)
                .archonText(.title2)
                .foregroundStyle(theme.textPrimary)
                .lineLimit(1)
        }
        .padding(Space.md)
        .frame(minWidth: 96, alignment: .leading)
        .archonMaterial(.flatElevated, cornerRadius: Radius.card)
        .overlay {
            RoundedRectangle(cornerRadius: Radius.card, style: .continuous)
                .strokeBorder(theme.borderSubtle, lineWidth: Space.hairline)
        }
    }
}

/// Monospaced, line-numbered, read-only code preview (REQ-UX-072).
private struct CodePreview: View {
    let text: String
    let truncated: Bool
    @Environment(\.archonTheme) private var theme

    private var lines: [String] { text.components(separatedBy: "\n") }
    private var gutterWidth: CGFloat {
        let digits = max(2, String(lines.count).count)
        return CGFloat(digits) * 8 + Space.sm
    }

    var body: some View {
        ScrollView([.vertical, .horizontal]) {
            VStack(alignment: .leading, spacing: 0) {
                ForEach(Array(lines.enumerated()), id: \.offset) { index, line in
                    HStack(alignment: .top, spacing: Space.sm) {
                        Text("\(index + 1)")
                            .archonText(.monoSm)
                            .foregroundStyle(theme.textDisabled)
                            .frame(width: gutterWidth, alignment: .trailing)
                        Text(line.isEmpty ? " " : line)
                            .archonText(.monoBody)
                            .foregroundStyle(theme.textPrimary)
                            .textSelection(.enabled)
                            .fixedSize(horizontal: true, vertical: false)
                        Spacer(minLength: 0)
                    }
                    .padding(.vertical, 1)
                }
                if truncated {
                    Text("… preview truncated (large file)")
                        .archonText(.monoSm)
                        .foregroundStyle(theme.textDisabled)
                        .padding(.vertical, Space.sm)
                        .padding(.leading, gutterWidth + Space.sm)
                }
            }
            .padding(Space.md)
        }
    }
}
