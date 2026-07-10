import Foundation

// ============================================================================
// Terminals · Model · TerminalStyle
//
// The B/W terminal cell model. Per REQUIREMENTS §5.1-5.2 the terminal renders
// with ZERO chromatic color: every ANSI SGR color is folded onto a small
// achromatic intensity ramp (`TerminalInkLevel`) that the render layer resolves
// to the DesignSystem `Ink` tokens. This file names NO color literals — it only
// carries a compact intensity index; the single place ink→NSColor happens is
// `TerminalInkResolver` (Render), which consumes existing `Ink` ramp steps.
// ============================================================================

/// A compact achromatic intensity level for terminal text (5-step ramp). ANSI
/// foreground colors and 256/truecolor are mapped here by luminance so the
/// terminal stays strictly greyscale.
enum TerminalInkLevel: UInt8, Sendable, Equatable, CaseIterable {
    case faint       // dimmest legible text
    case secondary
    case normal      // default foreground
    case strong
    case max         // brightest (bold-white)

    /// One step brighter (used for `bold`), clamped.
    var brighter: TerminalInkLevel {
        TerminalInkLevel(rawValue: min(TerminalInkLevel.max.rawValue, rawValue + 1)) ?? .max
    }

    /// One step fainter (used for `dim`), clamped.
    var fainter: TerminalInkLevel {
        TerminalInkLevel(rawValue: rawValue == 0 ? 0 : rawValue - 1) ?? .faint
    }
}

/// The resolved graphic rendition of a run of characters (SGR state). Strictly
/// achromatic: color is represented only as an intensity level.
struct TerminalStyle: Sendable, Equatable {
    var ink: TerminalInkLevel = .normal
    var bold: Bool = false
    var dim: Bool = false
    var italic: Bool = false
    var underline: Bool = false
    var inverse: Bool = false

    static let `default` = TerminalStyle()

    /// The effective intensity after bold/dim adjustments.
    var effectiveInk: TerminalInkLevel {
        if bold { return ink.brighter }
        if dim { return ink.fainter }
        return ink
    }
}

/// A contiguous run of characters sharing one style (the render unit).
struct TerminalRun: Sendable, Equatable {
    var text: String
    var style: TerminalStyle

    init(text: String, style: TerminalStyle) {
        self.text = text
        self.style = style
    }
}

/// One committed terminal line: an ordered set of styled runs, plus a stable,
/// monotonic identity for `ForEach`/virtualization. `isMarker` lines are the
/// unobtrusive "output trimmed" breaks inserted on drop/gap (contract §3.4).
struct TerminalLine: Sendable, Equatable, Identifiable {
    let id: Int
    var runs: [TerminalRun]
    var isMarker: Bool

    init(id: Int, runs: [TerminalRun], isMarker: Bool = false) {
        self.id = id
        self.runs = runs
        self.isMarker = isMarker
    }

    /// The concatenated plain text (used for activity summaries / error scans).
    var plainText: String {
        runs.reduce(into: "") { $0 += $1.text }
    }

    /// A blank/empty line has no visible content.
    var isEmpty: Bool {
        isMarker ? false : plainText.isEmpty
    }
}
