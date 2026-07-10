import AppKit

// ============================================================================
// Terminals · Render · TerminalLineRaster
//
// Two cooperating pieces that satisfy REQ-PERF-002's "attributed-string cache
// for visible rows":
//
//   • TerminalInkPalette — the achromatic ink ramp resolved to NSColors, the
//     four monospaced font variants, and the paper colour, all built ONCE per
//     (mode, fontSize). This removes the per-run SwiftUI Color→NSColor bridging
//     and NSFont lookup that previously ran for every styled run of every
//     visible row on every render tick.
//
//   • TerminalLineRasterCache — an id-keyed NSAttributedString cache. Committed
//     terminal lines are immutable (their `id` never changes once they leave the
//     cursor), so their raster is built once and reused; only the live,
//     in-progress line is rebuilt each tick. The cache is bounded so a long
//     session cannot grow it without limit.
// ============================================================================

/// Immutable, pre-resolved rendering resources for one `(mode, fontSize)`.
struct TerminalInkPalette {
    let mode: ThemeMode
    let fontSize: CGFloat
    let paper: NSColor

    private let inks: [NSColor]           // indexed by TerminalInkLevel.rawValue
    private let plainFont: NSFont
    private let boldFont: NSFont
    private let italicFont: NSFont
    private let boldItalicFont: NSFont

    init(mode: ThemeMode, fontSize: CGFloat) {
        self.mode = mode
        self.fontSize = fontSize
        self.paper = TerminalInkResolver.paperNSColor(mode: mode)
        self.inks = TerminalInkLevel.allCases.map { TerminalInkResolver.nsColor($0, mode: mode) }
        self.plainFont = TerminalInkResolver.font(size: fontSize, bold: false, italic: false)
        self.boldFont = TerminalInkResolver.font(size: fontSize, bold: true, italic: false)
        self.italicFont = TerminalInkResolver.font(size: fontSize, bold: false, italic: true)
        self.boldItalicFont = TerminalInkResolver.font(size: fontSize, bold: true, italic: true)
    }

    func ink(_ level: TerminalInkLevel) -> NSColor { inks[Int(level.rawValue)] }

    func font(bold: Bool, italic: Bool) -> NSFont {
        switch (bold, italic) {
        case (false, false): return plainFont
        case (true, false):  return boldFont
        case (false, true):  return italicFont
        case (true, true):   return boldItalicFont
        }
    }

    /// Builds the attributed representation of one terminal line using the
    /// pre-resolved colours/fonts (no per-run resource allocation).
    func attributed(for line: TerminalLine) -> NSAttributedString {
        let result = NSMutableAttributedString()
        if line.isMarker {
            result.append(NSAttributedString(
                string: line.plainText,
                attributes: [.foregroundColor: ink(.faint), .font: font(bold: false, italic: true)]
            ))
            return result
        }
        for run in line.runs {
            let style = run.style
            let inkColor = ink(style.effectiveInk)
            var attributes: [NSAttributedString.Key: Any] = [
                .font: font(bold: style.bold, italic: style.italic)
            ]
            if style.inverse {
                attributes[.foregroundColor] = paper
                attributes[.backgroundColor] = inkColor
            } else {
                attributes[.foregroundColor] = inkColor
            }
            if style.underline {
                attributes[.underlineStyle] = NSUnderlineStyle.single.rawValue
            }
            result.append(NSAttributedString(string: run.text, attributes: attributes))
        }
        return result
    }
}

/// Per-view cache of rasterised terminal lines keyed by immutable `TerminalLine.id`.
@MainActor
final class TerminalLineRasterCache {

    private(set) var palette: TerminalInkPalette
    private var cache: [Int: NSAttributedString] = [:]
    private let softCap: Int

    /// Number of attributed strings actually built (cache misses + live-line
    /// rebuilds). Exposed so tests can lock the "build once per committed line"
    /// invariant without timing flakiness (REQ-PERF-002 regression guard).
    private(set) var rasterizations: Int = 0

    init(mode: ThemeMode, fontSize: CGFloat, softCap: Int = 4000) {
        self.palette = TerminalInkPalette(mode: mode, fontSize: fontSize)
        self.softCap = Swift.max(256, softCap)
    }

    /// Number of cached committed lines (visible for tests/diagnostics).
    var cachedCount: Int { cache.count }

    /// Rebuilds the palette and drops every raster when `(mode, fontSize)` change
    /// (a theme or font-size switch invalidates all cached strings). A no-op when
    /// the configuration is unchanged — the common per-tick path.
    func reconfigure(mode: ThemeMode, fontSize: CGFloat) {
        guard mode != palette.mode || fontSize != palette.fontSize else { return }
        palette = TerminalInkPalette(mode: mode, fontSize: fontSize)
        cache.removeAll(keepingCapacity: true)
    }

    /// The attributed raster for a line. The `live` (in-progress) line mutates
    /// under a stable id, so it is always rebuilt and never cached; every other
    /// line is immutable and cached by id.
    func attributed(for line: TerminalLine, live: Bool) -> NSAttributedString {
        if live {
            rasterizations += 1
            return palette.attributed(for: line)
        }
        if let hit = cache[line.id] { return hit }
        rasterizations += 1
        let raster = palette.attributed(for: line)
        cache[line.id] = raster
        if cache.count > softCap { prune() }
        return raster
    }

    /// Evicts the oldest entries (lowest ids — lines already gone from the
    /// bounded scrollback) when the soft cap is exceeded, keeping the cache O(1)
    /// in memory over an unbounded session.
    private func prune() {
        let keep = softCap / 2
        let survivors = Set(cache.keys.sorted().suffix(keep))
        cache = cache.filter { survivors.contains($0.key) }
    }
}
