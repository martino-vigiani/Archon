import SwiftUI

/// A lightweight, strictly-achromatic Markdown renderer for the memory viewer's
/// "rendered" mode. Headings map onto the design type scale; inline emphasis is
/// rendered via `AttributedString(markdown:)`. No chroma, no external deps.
struct MemoryMarkdownView: View {
    let text: String
    @Environment(\.archonTheme) private var theme

    private var blocks: [Block] { Block.parse(text) }

    var body: some View {
        VStack(alignment: .leading, spacing: Space.sm) {
            ForEach(blocks) { block in
                switch block.kind {
                case .heading(let level):
                    Text(inline(block.text))
                        .archonText(headingStyle(level))
                        .foregroundStyle(theme.textPrimary)
                        .padding(.top, level <= 2 ? Space.sm : 0)
                case .bullet:
                    HStack(alignment: .top, spacing: Space.sm) {
                        Text("•").archonText(.body).foregroundStyle(theme.textSecondary)
                        Text(inline(block.text)).archonText(.body).foregroundStyle(theme.textPrimary)
                    }
                case .code:
                    Text(block.text)
                        .archonText(.monoBody)
                        .foregroundStyle(theme.textPrimary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(Space.sm)
                        .archonMaterial(.flatElevated, cornerRadius: Radius.input)
                case .paragraph:
                    Text(inline(block.text))
                        .archonText(.body)
                        .foregroundStyle(theme.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                case .blank:
                    Color.clear.frame(height: Space.xs)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func headingStyle(_ level: Int) -> TextStyle {
        switch level {
        case 1: return .title1
        case 2: return .title2
        default: return .bodyEmphasis
        }
    }

    private func inline(_ source: String) -> AttributedString {
        (try? AttributedString(
            markdown: source,
            options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)
        )) ?? AttributedString(source)
    }

    struct Block: Identifiable {
        enum Kind: Equatable { case heading(Int), bullet, code, paragraph, blank }
        let id: Int
        let kind: Kind
        let text: String

        static func parse(_ text: String) -> [Block] {
            var blocks: [Block] = []
            var inFence = false
            var codeBuffer: [String] = []
            var index = 0
            for rawLine in text.components(separatedBy: "\n") {
                let line = rawLine
                if line.trimmingCharacters(in: .whitespaces).hasPrefix("```") {
                    if inFence {
                        blocks.append(Block(id: index, kind: .code, text: codeBuffer.joined(separator: "\n")))
                        codeBuffer.removeAll()
                        inFence = false
                    } else {
                        inFence = true
                    }
                    index += 1
                    continue
                }
                if inFence {
                    codeBuffer.append(line)
                    continue
                }
                let trimmed = line.trimmingCharacters(in: .whitespaces)
                if trimmed.isEmpty {
                    blocks.append(Block(id: index, kind: .blank, text: ""))
                } else if trimmed.hasPrefix("### ") {
                    blocks.append(Block(id: index, kind: .heading(3), text: String(trimmed.dropFirst(4))))
                } else if trimmed.hasPrefix("## ") {
                    blocks.append(Block(id: index, kind: .heading(2), text: String(trimmed.dropFirst(3))))
                } else if trimmed.hasPrefix("# ") {
                    blocks.append(Block(id: index, kind: .heading(1), text: String(trimmed.dropFirst(2))))
                } else if trimmed.hasPrefix("- ") || trimmed.hasPrefix("* ") {
                    blocks.append(Block(id: index, kind: .bullet, text: String(trimmed.dropFirst(2))))
                } else {
                    blocks.append(Block(id: index, kind: .paragraph, text: line))
                }
                index += 1
            }
            if inFence && !codeBuffer.isEmpty {
                blocks.append(Block(id: index, kind: .code, text: codeBuffer.joined(separator: "\n")))
            }
            return blocks
        }
    }
}
