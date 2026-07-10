import Testing
import Foundation
@testable import Archon

@Suite("ANSI/VT terminal emulator")
struct TerminalEmulatorTests {

    private func emulator(_ text: String, capacity: Int = 10_000) -> TerminalEmulator {
        let e = TerminalEmulator(scrollbackCapacity: capacity)
        e.feed(Array(text.utf8))
        return e
    }

    private func currentLine(_ e: TerminalEmulator) -> TerminalLine {
        e.line(at: e.lineCount - 1)
    }

    // MARK: - Plain text + line commits

    @Test("plain text commits lines on LF")
    func plainLines() {
        let e = emulator("hello\nworld")
        #expect(e.scrollbackCount == 1)
        #expect(e.line(at: 0).plainText == "hello")
        #expect(currentLine(e).plainText == "world")
    }

    // MARK: - Cursor controls

    @Test("CR returns to column 0 and overwrites")
    func carriageReturnOverwrites() {
        let e = emulator("abc\rX")
        #expect(currentLine(e).plainText == "Xbc")
    }

    @Test("backspace moves the cursor back")
    func backspace() {
        let e = emulator("abc\u{08}\u{08}Z")
        #expect(currentLine(e).plainText == "aZc")
    }

    @Test("tab advances to the next multiple of 8")
    func tab() {
        let e = emulator("ab\tX")
        // "ab" → col 2, TAB → col 8 (6 blanks), then "X" at col 8.
        let expected = "ab" + String(repeating: " ", count: 6) + "X"
        #expect(currentLine(e).plainText == expected)
    }

    @Test("erase-in-line (CSI 0K) clears from the cursor to end of line")
    func eraseInLine() {
        let e = emulator("abcdef\r\u{1B}[0KX")
        #expect(currentLine(e).plainText == "X")
    }

    @Test("CSI G sets the absolute column")
    func cursorHorizontalAbsolute() {
        let e = emulator("abcdef\u{1B}[3GZ")   // col → 2 (1-based 3), overwrite 'c'
        #expect(currentLine(e).plainText == "abZdef")
    }

    // MARK: - SGR attributes

    @Test("SGR bold / italic / underline / dim / inverse set style flags")
    func sgrAttributes() {
        #expect(emulator("\u{1B}[1mX").line(at: 0).runs.first?.style.bold == true)
        #expect(emulator("\u{1B}[3mX").line(at: 0).runs.first?.style.italic == true)
        #expect(emulator("\u{1B}[4mX").line(at: 0).runs.first?.style.underline == true)
        #expect(emulator("\u{1B}[2mX").line(at: 0).runs.first?.style.dim == true)
        #expect(emulator("\u{1B}[7mX").line(at: 0).runs.first?.style.inverse == true)
    }

    @Test("SGR reset (0m) clears attributes")
    func sgrReset() {
        let e = emulator("\u{1B}[1mA\u{1B}[0mB")
        let runs = e.line(at: 0).runs
        #expect(runs.count == 2)
        #expect(runs[0].style.bold == true)
        #expect(runs[1].style.bold == false)
    }

    @Test("SGR colors fold onto the achromatic ink ramp (no chroma)")
    func sgrColorToGreyscale() {
        #expect(emulator("\u{1B}[30mX").line(at: 0).runs.first?.style.ink == .faint)      // black
        #expect(emulator("\u{1B}[31mX").line(at: 0).runs.first?.style.ink == .normal)     // red
        #expect(emulator("\u{1B}[37mX").line(at: 0).runs.first?.style.ink == .strong)     // white
        #expect(emulator("\u{1B}[90mX").line(at: 0).runs.first?.style.ink == .secondary)  // bright black
        #expect(emulator("\u{1B}[97mX").line(at: 0).runs.first?.style.ink == .max)        // bright white
    }

    @Test("256-color and truecolor SGR are consumed and mapped, not leaked")
    func extendedColor() {
        // 38;5;255 (bright grey) → high intensity; sub-params must not leak as text.
        let e = emulator("\u{1B}[38;5;255mX\u{1B}[38;2;10;10;10mY")
        let runs = e.line(at: 0).runs
        #expect(runs.map(\.text).joined() == "XY")
        #expect(runs.first?.style.ink == .max)
    }

    // MARK: - Tolerant skipping

    @Test("private CSI (?25l) is tolerantly skipped")
    func tolerantPrivateCSI() {
        let e = emulator("\u{1B}[?25lVISIBLE")
        #expect(currentLine(e).plainText == "VISIBLE")
    }

    @Test("OSC sequences are skipped until BEL")
    func tolerantOSC() {
        let e = emulator("\u{1B}]0;window title\u{07}TEXT")
        #expect(currentLine(e).plainText == "TEXT")
    }

    @Test("OSC terminated by ST (ESC backslash) is skipped")
    func tolerantOSCST() {
        let e = emulator("\u{1B}]2;title\u{1B}\\AFTER")
        #expect(currentLine(e).plainText == "AFTER")
    }

    // MARK: - UTF-8 across chunk boundaries

    @Test("multi-byte UTF-8 renders correctly")
    func utf8Multibyte() {
        let e = emulator("café ☕")
        #expect(currentLine(e).plainText == "café ☕")
    }

    @Test("a UTF-8 scalar split across feeds is buffered, not corrupted")
    func utf8SplitAcrossFeeds() {
        let e = TerminalEmulator()
        e.feed([0xC3])        // first byte of 'é'
        e.feed([0xA9])        // continuation byte
        #expect(e.line(at: e.lineCount - 1).plainText == "é")
    }

    // MARK: - Scrollback eviction through the emulator

    @Test("scrollback evicts oldest beyond capacity (REQ-PERF-022)")
    func scrollbackEviction() {
        let e = TerminalEmulator(scrollbackCapacity: 3)
        e.feed(Array("l0\nl1\nl2\nl3\nl4\n".utf8))
        #expect(e.scrollbackCount == 3)
        #expect(e.line(at: 0).plainText == "l2")   // l0, l1 evicted
        #expect(e.line(at: 2).plainText == "l4")
    }

    // MARK: - Markers

    @Test("insertMarker adds an unobtrusive marker line and commits pending text")
    func insertMarker() {
        let e = TerminalEmulator()
        e.feed(Array("partial".utf8))
        e.insertMarker("── output trimmed ──")
        #expect(e.line(at: 0).plainText == "partial")
        #expect(e.line(at: 1).isMarker == true)
        #expect(e.line(at: 1).plainText == "── output trimmed ──")
    }
}
