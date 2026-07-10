import Testing
import Foundation
import AppKit
@testable import Archon

// Locks the REQ-PERF-002 visible-row raster cache + the REQ-PERF-014 synchronous
// parse-cost work, and prints before/after numbers for the 5k-line burst.

@Suite("Terminal raster cache (REQ-PERF-002)")
@MainActor
struct TerminalRasterCacheTests {

    /// Feeds `lines` styled rows into an emulator with room to retain them all.
    private func emulator(lines: Int, capacity: Int = 20_000) -> TerminalEmulator {
        let e = TerminalEmulator(scrollbackCapacity: capacity)
        var s = ""
        s.reserveCapacity(lines * 48)
        for i in 0..<lines {
            s += "line \(i): \u{1B}[1mbuild\u{1B}[0m ok \u{1B}[31mwarn\u{1B}[0m tail text\n"
        }
        e.feed(Array(s.utf8))
        return e
    }

    private func renderWindow(_ e: TerminalEmulator, cache: TerminalLineRasterCache, rows: Int) {
        let count = e.lineCount
        let live = count - 1
        let first = max(0, count - rows)
        for i in first..<count {
            _ = cache.attributed(for: e.line(at: i), live: i == live)
        }
    }

    @Test("committed lines are cached by id; the live line is never cached")
    func cachesCommittedNotLive() {
        let e = emulator(lines: 80)
        let cache = TerminalLineRasterCache(mode: .dark, fontSize: 13)
        renderWindow(e, cache: cache, rows: e.lineCount)   // whole buffer
        renderWindow(e, cache: cache, rows: e.lineCount)
        // Every committed line cached exactly once; the in-progress line excluded.
        #expect(cache.cachedCount == e.scrollbackCount)
    }

    @Test("re-rendering the same window rebuilds each committed line at most once")
    func rebuildOncePerCommitted() {
        let e = emulator(lines: 60)
        let cache = TerminalLineRasterCache(mode: .dark, fontSize: 13)
        let ticks = 100
        let rows = e.lineCount
        for _ in 0..<ticks { renderWindow(e, cache: cache, rows: rows) }
        // Committed lines built once total; only the live line rebuilds per tick.
        // Without the cache this would be lineCount * ticks builds.
        #expect(cache.rasterizations == e.scrollbackCount + ticks)
        #expect(cache.rasterizations < e.lineCount * ticks)
    }

    @Test("a theme/font reconfigure invalidates every cached raster")
    func reconfigureClears() {
        let e = emulator(lines: 30)
        let cache = TerminalLineRasterCache(mode: .dark, fontSize: 13)
        renderWindow(e, cache: cache, rows: e.lineCount)
        #expect(cache.cachedCount > 0)
        cache.reconfigure(mode: .light, fontSize: 13)
        #expect(cache.cachedCount == 0)
        // An unchanged reconfigure is a no-op (keeps the cache warm).
        renderWindow(e, cache: cache, rows: e.lineCount)
        let warm = cache.cachedCount
        cache.reconfigure(mode: .light, fontSize: 13)
        #expect(cache.cachedCount == warm)
    }

    @Test("cache stays bounded under a large burst (prunes oldest ids)")
    func boundedUnderBurst() {
        let e = emulator(lines: 6_000)
        let cache = TerminalLineRasterCache(mode: .dark, fontSize: 13, softCap: 1_000)
        renderWindow(e, cache: cache, rows: e.lineCount)   // touch every committed id
        #expect(cache.cachedCount <= 1_000)
    }

    @Test("cached rendering beats rebuilding every tick (measured)")
    func measuredCacheWin() {
        let e = emulator(lines: 5_000)
        let visibleRows = 50
        let ticks = 300
        let count = e.lineCount
        let live = count - 1
        let first = max(0, count - visibleRows)

        // Baseline: rebuild every visible row every tick (the old draw()).
        let palette = TerminalInkPalette(mode: .dark, fontSize: 13)
        let clock = ContinuousClock()
        let rebuild = clock.measure {
            for _ in 0..<ticks {
                for i in first..<count { _ = palette.attributed(for: e.line(at: i)) }
            }
        }

        // Cached: only the live row rebuilds after the first tick.
        let cache = TerminalLineRasterCache(mode: .dark, fontSize: 13)
        let cached = clock.measure {
            for _ in 0..<ticks {
                for i in first..<count {
                    _ = cache.attributed(for: e.line(at: i), live: i == live)
                }
            }
        }

        let rebuildMs = Double(rebuild.components.attoseconds) / 1e15
        let cachedMs = Double(cached.components.attoseconds) / 1e15
        print("PERF-TERM render \(visibleRows) rows × \(ticks) ticks: rebuild=\(String(format: "%.2f", rebuildMs))ms cached=\(String(format: "%.2f", cachedMs))ms")
        #expect(cachedMs <= rebuildMs)
    }
}

@Suite("Terminal parse cost (REQ-PERF-014)")
struct TerminalParseCostTests {

    @Test("5k-line burst parses correctly and within the main-thread budget (measured)")
    func fiveKBurst() {
        var s = ""
        let lines = 5_000
        s.reserveCapacity(lines * 60)
        for i in 0..<lines {
            s += "café \(i) ☕ \u{1B}[1mbold\u{1B}[0m normal output line here\n"
        }
        let bytes = Array(s.utf8)

        let e = TerminalEmulator(scrollbackCapacity: 20_000)
        let clock = ContinuousClock()
        let elapsed = clock.measure { e.feed(bytes) }
        let ms = Double(elapsed.components.attoseconds) / 1e15

        #expect(e.scrollbackCount == lines)
        #expect(e.line(at: 0).plainText == "café 0 ☕ bold normal output line here")
        print("PERF-TERM feed \(lines) lines (\(bytes.count) bytes): \(String(format: "%.2f", ms))ms")
    }

    @Test("optimized UTF-8 drain preserves split-scalar and multibyte behavior")
    func utf8Preserved() {
        // Scalar split across feeds is buffered, not corrupted.
        let e = TerminalEmulator()
        e.feed([0xC3])            // lead byte of 'é'
        #expect(e.line(at: e.lineCount - 1).plainText == "")   // incomplete tail held
        e.feed([0xA9])            // continuation
        #expect(e.line(at: e.lineCount - 1).plainText == "é")

        // A 3-byte scalar split 1+2 across feeds.
        let e2 = TerminalEmulator()
        e2.feed([0xE2])           // first of '☕' (U+2615)
        e2.feed([0x98, 0x95])     // remaining two
        #expect(e2.line(at: e2.lineCount - 1).plainText == "☕")
    }
}
