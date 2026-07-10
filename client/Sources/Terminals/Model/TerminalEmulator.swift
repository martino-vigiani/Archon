import Foundation

// ============================================================================
// Terminals · Model · TerminalEmulator
//
// A streaming ANSI/VT line emulator sized for typical CLI output (Claude Code
// sessions): SGR graphic rendition (bold/dim/italic/underline/inverse + colors
// folded to the achromatic ink ramp), C0 controls (CR/LF/BS/TAB), single-line
// CSI cursor moves + erase-line, and tolerant-skip of everything else (OSC/DCS/
// vertical addressing) so no stray bytes leak into the transcript. Output lands
// in a 10,000-line virtualized `ScrollbackBuffer` (REQ-PERF-021/022).
//
// Not `Sendable`: owned and driven exclusively on the `@MainActor` by
// `TerminalSession`. UTF-8 and escape state persist across `feed(_:)` calls so
// chunk boundaries never corrupt a scalar or a sequence.
// ============================================================================

final class TerminalEmulator {

    // MARK: - Configuration

    /// Soft-wrap width (bounds current-line cell arrays). Long CLI lines wrap
    /// here; the renderer clips horizontally within a pane.
    private let columns: Int

    // MARK: - Output

    private(set) var scrollback: ScrollbackBuffer

    /// Bumped on ANY content change so the render layer can invalidate cheaply.
    private(set) var revision: Int = 0

    // MARK: - Current (in-progress) line

    private struct Cell: Equatable {
        var char: Character
        var style: TerminalStyle
    }

    private var cells: [Cell] = []
    private var cursorCol: Int = 0
    private var pen: TerminalStyle = .default
    private var nextLineId: Int = 0

    // MARK: - Parser state

    private enum ParseState {
        case ground
        case escape          // saw ESC
        case csi             // saw ESC[
        case osc             // saw ESC] / DCS / PM / APC — skip until ST/BEL
        case oscEscape       // inside OSC, saw ESC (awaiting '\' for ST)
        case charset         // saw ESC( or ESC) etc. — consume one byte
    }

    private var state: ParseState = .ground
    /// Raw parameter+intermediate bytes accumulated for a CSI sequence.
    private var csiBuffer: [UInt8] = []
    /// Text bytes awaiting UTF-8 decode (may hold an incomplete tail across feeds).
    private var textBuffer: [UInt8] = []

    // MARK: - Init

    init(scrollbackCapacity: Int = 10_000, columns: Int = 500) {
        self.columns = Swift.max(20, columns)
        self.scrollback = ScrollbackBuffer(capacity: scrollbackCapacity)
    }

    // MARK: - Public read surface

    /// Retained committed lines (for eviction assertions / tests).
    var scrollbackCount: Int { scrollback.count }

    /// Total renderable lines = committed scrollback + the in-progress line.
    var lineCount: Int { scrollback.count + 1 }

    /// Committed lines evicted from scrollback over the session lifetime. The
    /// render layer watches this to detect that retained line *indices* shifted
    /// (an eviction moves every row up one), so it can repaint the whole visible
    /// band only then instead of on every tick (REQ-PERF-002).
    var evictedLineCount: Int { scrollback.totalAppended - scrollback.count }

    /// The line at render index `0..<lineCount`. The final index is the live,
    /// in-progress current line (rendered so partial output is visible).
    func line(at index: Int) -> TerminalLine {
        if index == scrollback.count {
            return currentLineSnapshot()
        }
        return scrollback.line(at: index) ?? TerminalLine(id: -1, runs: [])
    }

    /// The last `n` renderable lines (newest last).
    func recentLines(_ n: Int) -> [TerminalLine] {
        let total = lineCount
        let start = Swift.max(0, total - n)
        return (start..<total).map { line(at: $0) }
    }

    // MARK: - Feed

    func feed(_ data: Data) {
        feed([UInt8](data))
    }

    /// Ingests raw PTY bytes. All control/escape bytes are ASCII (< 0x80) and
    /// never collide with UTF-8 continuation bytes, so text can be buffered and
    /// drained around control handling without splitting scalars.
    func feed(_ bytes: [UInt8]) {
        guard !bytes.isEmpty else { return }
        for b in bytes {
            switch state {
            case .ground:
                if b == 0x1B {            // ESC
                    drainText()
                    state = .escape
                } else if b < 0x20 || b == 0x7F {
                    drainText()
                    handleC0(b)
                } else {
                    textBuffer.append(b)   // printable ASCII or UTF-8 byte
                }

            case .escape:
                handleEscape(b)

            case .csi:
                handleCSI(b)

            case .osc:
                handleOSC(b)

            case .oscEscape:
                // In OSC and saw ESC; '\' completes the ST terminator.
                state = (b == 0x5C) ? .ground : .osc

            case .charset:
                state = .ground            // consume the single designator byte
            }
        }
        // Keep an incomplete UTF-8 tail buffered; drain complete scalars so
        // partial output is visible within the coalescing window.
        drainText()
        revision &+= 1
    }

    // MARK: - Markers (drop/gap breaks)

    /// Inserts an unobtrusive marker line (e.g. "output trimmed") — commits any
    /// in-progress line first so the marker sits on its own row.
    func insertMarker(_ text: String) {
        if !cells.isEmpty { commitLine() }
        let line = TerminalLine(
            id: takeLineId(),
            runs: [TerminalRun(text: text, style: TerminalStyle(ink: .faint, dim: true))],
            isMarker: true
        )
        scrollback.append(line)
        revision &+= 1
    }

    // MARK: - Text drain (incremental UTF-8)

    private func drainText() {
        guard !textBuffer.isEmpty else { return }
        // Decode the whole complete prefix in ONE allocation instead of building
        // a String per scalar (the old hot path allocated one String per byte on
        // large feeds, dominating the synchronous parse cost — REQ-PERF-014).
        // Per-scalar cell semantics are preserved by iterating unicode scalars.
        let complete = completePrefixCount(textBuffer)
        guard complete > 0 else { return }   // only an incomplete tail is buffered
        let decoded = String(decoding: textBuffer[0..<complete], as: UTF8.self)
        for scalar in decoded.unicodeScalars { putChar(Character(scalar)) }
        if complete == textBuffer.count {
            textBuffer.removeAll(keepingCapacity: true)
        } else {
            textBuffer.removeFirst(complete)
        }
    }

    /// Number of leading bytes that form complete UTF-8 sequences; an incomplete
    /// trailing multi-byte sequence is excluded and kept for the next feed so a
    /// scalar split across chunk boundaries is never corrupted.
    private func completePrefixCount(_ bytes: [UInt8]) -> Int {
        var i = 0
        let n = bytes.count
        while i < n {
            let b = bytes[i]
            let len: Int
            if b < 0x80 { len = 1 }
            else if b & 0xE0 == 0xC0 { len = 2 }
            else if b & 0xF0 == 0xE0 { len = 3 }
            else if b & 0xF8 == 0xF0 { len = 4 }
            else { len = 1 }               // invalid lead → replacement, resync
            if i + len > n { break }        // incomplete tail: keep for next feed
            i += len
        }
        return i
    }

    // MARK: - Cell writing

    private func ensureColumn(_ col: Int) {
        if cells.count < col {
            let blank = Cell(char: " ", style: .default)
            cells.append(contentsOf: repeatElement(blank, count: col - cells.count))
        }
    }

    private func putChar(_ ch: Character) {
        if cursorCol >= columns {
            commitLine()                    // soft wrap
        }
        ensureColumn(cursorCol)
        let cell = Cell(char: ch, style: pen)
        if cursorCol < cells.count {
            cells[cursorCol] = cell
        } else {
            cells.append(cell)
        }
        cursorCol += 1
    }

    // MARK: - C0 controls

    private func handleC0(_ b: UInt8) {
        switch b {
        case 0x0A, 0x0B, 0x0C:              // LF / VT / FF → new line
            commitLine()
        case 0x0D:                          // CR → column 0 (overwrite mode)
            cursorCol = 0
        case 0x08:                          // BS
            cursorCol = Swift.max(0, cursorCol - 1)
        case 0x09:                          // TAB → next multiple of 8
            let next = ((cursorCol / 8) + 1) * 8
            cursorCol = Swift.min(next, columns - 1)
            ensureColumn(cursorCol)
        default:
            break                           // BEL and other C0 → ignore
        }
    }

    // MARK: - Escape dispatch

    private func handleEscape(_ b: UInt8) {
        switch b {
        case 0x5B:                          // '['  → CSI
            csiBuffer.removeAll(keepingCapacity: true)
            state = .csi
        case 0x5D, 0x50, 0x58, 0x5E, 0x5F:  // ']' OSC, 'P' DCS, 'X' SOS, '^' PM, '_' APC
            state = .osc
        case 0x28, 0x29, 0x2A, 0x2B, 0x2D, 0x2E, 0x2F:  // charset designators
            state = .charset
        case 0x63:                          // 'c' RIS full reset
            resetHard()
            state = .ground
        case 0x37, 0x38:                    // DECSC/DECRC save/restore cursor
            state = .ground
        default:
            state = .ground                 // tolerant: swallow single-byte ESC seqs
        }
    }

    // MARK: - CSI dispatch

    private func handleCSI(_ b: UInt8) {
        // Parameters 0x30-0x3F and intermediates 0x20-0x2F accumulate; a final
        // byte 0x40-0x7E dispatches the sequence.
        if b >= 0x40 && b <= 0x7E {
            dispatchCSI(final: b)
            csiBuffer.removeAll(keepingCapacity: true)
            state = .ground
        } else if (b >= 0x20 && b <= 0x3F) {
            if csiBuffer.count < 64 { csiBuffer.append(b) }  // bounded
        } else {
            // Malformed → abort the sequence tolerantly.
            csiBuffer.removeAll(keepingCapacity: true)
            state = .ground
        }
    }

    private func csiParams() -> [Int] {
        // Ignore a leading private marker like '?' (0x3F) or '>' (0x3E).
        var buf = csiBuffer
        if let first = buf.first, first == 0x3F || first == 0x3E || first == 0x3C || first == 0x3D {
            buf.removeFirst()
        }
        let text = String(decoding: buf, as: UTF8.self)
        if text.isEmpty { return [] }
        return text.split(separator: ";", omittingEmptySubsequences: false).map { Int($0) ?? 0 }
    }

    private func isPrivateCSI() -> Bool {
        if let first = csiBuffer.first { return first == 0x3F || first == 0x3E || first == 0x3C || first == 0x3D }
        return false
    }

    private func dispatchCSI(final: UInt8) {
        let params = csiParams()
        let p0 = params.first ?? 0
        switch final {
        case 0x6D:                          // 'm' SGR
            applySGR(params)
        case 0x43:                          // 'C' cursor forward
            cursorCol = Swift.min(columns - 1, cursorCol + Swift.max(1, p0))
        case 0x44:                          // 'D' cursor back
            cursorCol = Swift.max(0, cursorCol - Swift.max(1, p0))
        case 0x47:                          // 'G' cursor horizontal absolute
            cursorCol = Swift.max(0, Swift.min(columns - 1, p0 - 1))
        case 0x48, 0x66:                    // 'H'/'f' cursor position (row;col)
            let col = params.count >= 2 ? params[1] : 1
            cursorCol = Swift.max(0, Swift.min(columns - 1, col - 1))
        case 0x45:                          // 'E' cursor next line → col 0
            cursorCol = 0
        case 0x46:                          // 'F' cursor prev line → col 0
            cursorCol = 0
        case 0x4B:                          // 'K' erase in line
            eraseInLine(mode: p0)
        case 0x4A:                          // 'J' erase in display (tolerant)
            if !isPrivateCSI() && p0 == 2 { cells.removeAll(keepingCapacity: true); cursorCol = 0 }
        default:
            break                           // tolerant-skip (SM/RM/DECSET/etc.)
        }
    }

    private func eraseInLine(mode: Int) {
        switch mode {
        case 0:                             // cursor → end of line
            if cursorCol < cells.count { cells.removeLast(cells.count - cursorCol) }
        case 1:                             // start → cursor
            ensureColumn(cursorCol)
            let upper = Swift.min(cursorCol + 1, cells.count)
            for i in 0..<upper { cells[i] = Cell(char: " ", style: .default) }
        case 2:                             // whole line
            cells.removeAll(keepingCapacity: true)
        default:
            break
        }
    }

    // MARK: - OSC (skip until ST/BEL)

    private func handleOSC(_ b: UInt8) {
        if b == 0x07 {                      // BEL terminator
            state = .ground
        } else if b == 0x1B {               // ESC → maybe ST
            state = .oscEscape
        }
        // else: swallow OSC payload byte
    }

    // MARK: - SGR

    private func applySGR(_ params: [Int]) {
        if params.isEmpty { pen = .default; return }
        var i = 0
        while i < params.count {
            let code = params[i]
            switch code {
            case 0:  pen = .default
            case 1:  pen.bold = true
            case 2:  pen.dim = true
            case 3:  pen.italic = true
            case 4:  pen.underline = true
            case 7:  pen.inverse = true
            case 22: pen.bold = false; pen.dim = false
            case 23: pen.italic = false
            case 24: pen.underline = false
            case 27: pen.inverse = false
            case 30...37:  pen.ink = Self.inkForBasic(code - 30, bright: false)
            case 90...97:  pen.ink = Self.inkForBasic(code - 90, bright: true)
            case 39:       pen.ink = .normal
            case 38:                        // extended foreground
                if i + 1 < params.count, params[i + 1] == 5, i + 2 < params.count {
                    pen.ink = Self.inkFor256(params[i + 2]); i += 2
                } else if i + 1 < params.count, params[i + 1] == 2, i + 4 < params.count {
                    pen.ink = Self.inkForRGB(r: params[i + 2], g: params[i + 3], b: params[i + 4]); i += 4
                }
            case 48:                        // extended background → skip sub-params (B/W)
                if i + 1 < params.count, params[i + 1] == 5 { i += 2 }
                else if i + 1 < params.count, params[i + 1] == 2 { i += 4 }
            default:
                break                       // 40-47/49/100-107 bg and others → ignore
            }
            i += 1
        }
    }

    /// Maps the 8 basic ANSI colors to greyscale intensity by rough luminance.
    private static func inkForBasic(_ index: Int, bright: Bool) -> TerminalInkLevel {
        switch index {
        case 0:  return bright ? .secondary : .faint   // black / bright-black
        case 7:  return bright ? .max : .strong        // white / bright-white
        default: return bright ? .strong : .normal     // colored → mid/high intensity
        }
    }

    /// Maps an xterm-256 index to greyscale (16-231 color cube + 232-255 ramp).
    private static func inkFor256(_ index: Int) -> TerminalInkLevel {
        if index < 0 { return .normal }
        if index < 8  { return inkForBasic(index, bright: false) }
        if index < 16 { return inkForBasic(index - 8, bright: true) }
        if index >= 232 {                   // greyscale ramp 232(dark)…255(light)
            return bucket(Double(index - 232) / 23.0)
        }
        // 6×6×6 color cube → luminance
        let c = index - 16
        let r = (c / 36) % 6, g = (c / 6) % 6, b = c % 6
        let steps: [Double] = [0, 95, 135, 175, 215, 255]
        let lum = (0.299 * steps[r] + 0.587 * steps[g] + 0.114 * steps[b]) / 255.0
        return bucket(lum)
    }

    private static func inkForRGB(r: Int, g: Int, b: Int) -> TerminalInkLevel {
        let lum = (0.299 * Double(r) + 0.587 * Double(g) + 0.114 * Double(b)) / 255.0
        return bucket(lum)
    }

    private static func bucket(_ lum: Double) -> TerminalInkLevel {
        switch lum {
        case ..<0.2:  return .faint
        case ..<0.4:  return .secondary
        case ..<0.6:  return .normal
        case ..<0.8:  return .strong
        default:      return .max
        }
    }

    // MARK: - Line commit

    private func takeLineId() -> Int {
        defer { nextLineId += 1 }
        return nextLineId
    }

    private func currentLineSnapshot() -> TerminalLine {
        TerminalLine(id: nextLineId, runs: runs(from: cells))
    }

    private func commitLine() {
        let line = TerminalLine(id: takeLineId(), runs: runs(from: cells))
        scrollback.append(line)
        cells.removeAll(keepingCapacity: true)
        cursorCol = 0
    }

    /// Coalesces adjacent equal-style cells into runs; trims trailing blanks.
    private func runs(from cells: [Cell]) -> [TerminalRun] {
        var trimmed = cells
        while let last = trimmed.last, last.char == " ", last.style == .default {
            trimmed.removeLast()
        }
        guard !trimmed.isEmpty else { return [] }
        var out: [TerminalRun] = []
        var currentStyle = trimmed[0].style
        var current = ""
        for cell in trimmed {
            if cell.style == currentStyle {
                current.append(cell.char)
            } else {
                out.append(TerminalRun(text: current, style: currentStyle))
                currentStyle = cell.style
                current = String(cell.char)
            }
        }
        out.append(TerminalRun(text: current, style: currentStyle))
        return out
    }

    // MARK: - Reset

    private func resetHard() {
        cells.removeAll(keepingCapacity: true)
        cursorCol = 0
        pen = .default
        csiBuffer.removeAll(keepingCapacity: true)
    }
}
