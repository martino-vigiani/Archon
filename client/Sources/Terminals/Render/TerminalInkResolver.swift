import SwiftUI
import AppKit

// ============================================================================
// Terminals · Render · TerminalInkResolver
//
// The ONE place terminal styles cross into AppKit colors. It resolves the
// achromatic `TerminalInkLevel` ramp to the DesignSystem `Ink` tokens (it
// CONSUMES named ramp steps — it never invents grey literals), so the terminal
// stays strictly B/W (REQUIREMENTS §5.1-5.2). Bold/dim shift intensity + weight;
// inverse swaps ink↔paper; underline/italic map to text attributes.
// ============================================================================

enum TerminalInkResolver {

    /// The paper (background) color a terminal pane draws over — used to swap
    /// foreground on `inverse` runs.
    static func paperNSColor(mode: ThemeMode) -> NSColor {
        NSColor(Theme(mode: mode).background)
    }

    /// Resolves an intensity level to a concrete achromatic color for the mode.
    private static func color(_ level: TerminalInkLevel, mode: ThemeMode) -> Color {
        switch mode {
        case .dark:
            switch level {
            case .faint:     return Ink.ink40
            case .secondary: return Ink.ink60
            case .normal:    return Ink.ink90
            case .strong:    return Ink.ink95
            case .max:       return Ink.ink100
            }
        case .light:
            switch level {
            case .faint:     return Ink.ink60
            case .secondary: return Ink.ink40
            case .normal:    return Ink.ink10
            case .strong:    return Ink.ink5
            case .max:       return Ink.ink0
            }
        }
    }

    static func nsColor(_ level: TerminalInkLevel, mode: ThemeMode) -> NSColor {
        NSColor(color(level, mode: mode))
    }

    /// Monospaced terminal font (SF Mono), honouring bold/italic.
    static func font(size: CGFloat, bold: Bool, italic: Bool) -> NSFont {
        var font = NSFont.monospacedSystemFont(ofSize: size, weight: bold ? .semibold : .regular)
        if italic {
            let descriptor = font.fontDescriptor.withSymbolicTraits(.italic)
            if let italicFont = NSFont(descriptor: descriptor, size: size) {
                font = italicFont
            }
        }
        return font
    }

    /// Builds the attributed representation of one terminal line for CoreText/
    /// NSString drawing. Convenience wrapper over `TerminalInkPalette` (the hot
    /// render path caches a palette instead of building one per call). `paper` is
    /// accepted for source compatibility but is derived from `mode`.
    static func attributedString(
        for line: TerminalLine,
        mode: ThemeMode,
        fontSize: CGFloat,
        paper: NSColor
    ) -> NSAttributedString {
        TerminalInkPalette(mode: mode, fontSize: fontSize).attributed(for: line)
    }
}
