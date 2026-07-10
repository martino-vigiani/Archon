import SwiftUI

/// The normative type scale (REQ-DSN-031/032). SF Pro for UI text, SF Mono for
/// terminal/code content. No size/weight/tracking outside this table.
enum TextStyle: Sendable, CaseIterable {
    case display          // SF Pro Display 28 Semibold, tracking -0.5
    case title1           // SF Pro Display 22 Semibold, tracking -0.3
    case title2           // SF Pro 17 Semibold, tracking -0.2
    case body             // SF Pro 15 Regular, line 22
    case bodyEmphasis     // SF Pro 15 Medium, line 22
    case caption          // SF Pro 12 Regular, line 16, tracking +0.1
    case captionEmphasis  // SF Pro 12 Medium, line 16
    case monoBody         // SF Mono 13 Regular, line 19
    case monoSm           // SF Mono 11 Regular, line 16

    var size: CGFloat {
        switch self {
        case .display: return 28
        case .title1: return 22
        case .title2: return 17
        case .body, .bodyEmphasis: return 15
        case .caption, .captionEmphasis: return 12
        case .monoBody: return 13
        case .monoSm: return 11
        }
    }

    var weight: Font.Weight {
        switch self {
        case .display, .title1, .title2: return .semibold
        case .body: return .regular
        case .bodyEmphasis: return .medium
        case .caption: return .regular
        case .captionEmphasis: return .medium
        case .monoBody, .monoSm: return .regular
        }
    }

    var tracking: CGFloat {
        switch self {
        case .display: return -0.5
        case .title1: return -0.3
        case .title2: return -0.2
        case .body, .bodyEmphasis: return 0
        case .caption: return 0.1
        case .captionEmphasis: return 0
        case .monoBody, .monoSm: return 0
        }
    }

    /// Explicit line height (0 = automatic).
    var lineHeight: CGFloat {
        switch self {
        case .display, .title1, .title2: return 0
        case .body, .bodyEmphasis: return 22
        case .caption, .captionEmphasis: return 16
        case .monoBody: return 19
        case .monoSm: return 16
        }
    }

    private var design: Font.Design {
        switch self {
        case .monoBody, .monoSm: return .monospaced
        default: return .default
        }
    }

    /// Whether this role scales with Dynamic Type (terminal/mono fixed cells do
    /// not, per REQ-DSN-033).
    var scalesWithDynamicType: Bool {
        switch self {
        case .monoBody, .monoSm: return false
        default: return true
        }
    }

    var font: Font {
        .system(size: size, weight: weight, design: design)
    }
}

private struct ArchonTextModifier: ViewModifier {
    let style: TextStyle

    func body(content: Content) -> some View {
        let lineSpacing = style.lineHeight > 0 ? max(0, style.lineHeight - style.size) : 0
        return content
            .font(style.font)
            .tracking(style.tracking)
            .lineSpacing(lineSpacing)
    }
}

extension View {
    /// Applies a semantic type role (font + tracking + line spacing).
    func archonText(_ style: TextStyle) -> some View {
        modifier(ArchonTextModifier(style: style))
    }
}

extension Text {
    /// Convenience for `Text` that also sets the font.
    func archonTextStyle(_ style: TextStyle) -> some View {
        self.archonText(style)
    }
}
