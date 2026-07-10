import Testing
import Foundation
import SwiftUI
import AppKit
import CoreGraphics
@testable import Archon

// ============================================================================
// Design-acceptance harness (§5 / REQ-DSN). Three cheap, headless gates that
// lock in the strict black/white system and the normative token scale:
//
//   1. Static lint — scans Sources/ for forbidden raw patterns (magic font
//      sizes, IconSize arithmetic, `.tint`, chromatic color literals, linear
//      animation) outside a documented allowlist.
//   2. Token chroma audit — every semantic role resolves to a neutral grey in
//      both modes (REQ-DSN-001).
//   3. Offscreen render audit — a composed swatch renders with zero chromatic
//      pixels (REQ-DSN-001), using ImageRenderer (works headless, no TCC).
//
// Plus token/breakpoint lock-in for the fixes in this phase.
// ============================================================================

// MARK: - 1. Static source lint

@Suite("Design static lint (REQ-DSN-002/032/047/049/056)")
struct DesignStaticLintTests {

    /// The `client/Sources` directory, derived from this test file's path so the
    /// lint runs headless from a plain checkout.
    private static var sourcesDirectory: URL {
        URL(fileURLWithPath: #filePath)          // …/client/Tests/DesignLintTests.swift
            .deletingLastPathComponent()          // …/client/Tests
            .deletingLastPathComponent()          // …/client
            .appendingPathComponent("Sources")
    }

    private static func swiftFiles() -> [URL] {
        let root = sourcesDirectory
        guard let enumerator = FileManager.default.enumerator(
            at: root, includingPropertiesForKeys: nil
        ) else { return [] }
        return enumerator.compactMap { $0 as? URL }.filter { $0.pathExtension == "swift" }
    }

    /// Relative path under Sources/, e.g. `Board/Views/Kanban/CardView.swift`.
    private static func relativePath(_ url: URL) -> String {
        let base = sourcesDirectory.path
        return url.path.hasPrefix(base) ? String(url.path.dropFirst(base.count + 1)) : url.lastPathComponent
    }

    private struct Violation: CustomStringConvertible {
        let file: String
        let line: Int
        let rule: String
        let text: String
        var description: String { "\(file):\(line) [\(rule)] \(text.trimmingCharacters(in: .whitespaces))" }
    }

    private static func scan(
        rule: String,
        matches: (String) -> Bool,
        allow: (_ path: String, _ line: String) -> Bool = { _, _ in false }
    ) -> [Violation] {
        var out: [Violation] = []
        for file in swiftFiles() {
            let path = relativePath(file)
            guard let content = try? String(contentsOf: file, encoding: .utf8) else { continue }
            for (index, raw) in content.split(separator: "\n", omittingEmptySubsequences: false).enumerated() {
                let line = String(raw)
                guard matches(line), !allow(path, line) else { continue }
                out.append(Violation(file: path, line: index + 1, rule: rule, text: line))
            }
        }
        return out
    }

    private static func contains(_ line: String, regex: String) -> Bool {
        line.range(of: regex, options: .regularExpression) != nil
    }

    @Test("no raw magic font sizes — sizes must come from the type/icon tokens (REQ-DSN-032/049)")
    func noRawFontSizes() {
        // App/ is owned by a separate fixer in this phase; RootView's 44-pt
        // launcher hero glyph is tracked there, not here.
        let allowlist: Set<String> = ["App/RootView.swift"]
        let violations = Self.scan(
            rule: "raw-font-size",
            matches: { Self.contains($0, regex: #"\.font\(\.system\(size:\s*[0-9]"#) },
            allow: { path, _ in allowlist.contains(path) }
        )
        #expect(violations.isEmpty, "Raw font sizes found:\n\(violations.map(\.description).joined(separator: "\n"))")
    }

    @Test("no off-grid IconSize arithmetic (REQ-DSN-049)")
    func noIconSizeArithmetic() {
        let violations = Self.scan(
            rule: "icon-arithmetic",
            matches: { Self.contains($0, regex: #"IconSize\.[A-Za-z]+\s*[-+]\s*[0-9]"#) }
        )
        #expect(violations.isEmpty, "IconSize arithmetic found:\n\(violations.map(\.description).joined(separator: "\n"))")
    }

    @Test(".tint is banned — hierarchy is achromatic (REQ-DSN-047)")
    func noTint() {
        let violations = Self.scan(
            rule: "tint",
            matches: { Self.contains($0, regex: #"\.tint\("#) }
        )
        #expect(violations.isEmpty, ".tint usage found:\n\(violations.map(\.description).joined(separator: "\n"))")
    }

    @Test("no chromatic color literals outside the two sanctioned sources (REQ-DSN-002)")
    func noChromaticColorLiterals() {
        // DesignTokens builds the achromatic grey ramp; OrbHue is the ONLY
        // permitted chromatic source (the orb, REQ-DSN-011/012).
        let allowlist: Set<String> = [
            "DesignSystem/Tokens/DesignTokens.swift",
            "VoiceOrb/Orb/OrbHue.swift",
        ]
        let violations = Self.scan(
            rule: "color-literal",
            matches: { Self.contains($0, regex: #"Color\(\.displayP3|Color\(hue:|Color\(red:|Color\(\.sRGB,\s*red:"#) },
            allow: { path, _ in allowlist.contains(path) }
        )
        #expect(violations.isEmpty, "Chromatic color literals found:\n\(violations.map(\.description).joined(separator: "\n"))")
    }

    @Test("no linear animation curves (REQ-DSN-056)")
    func noLinearAnimation() {
        let violations = Self.scan(
            rule: "linear-animation",
            matches: { Self.contains($0, regex: #"\.animation\(\.linear|withAnimation\(\.linear|Animation\.linear|timingCurve\(\s*0"#) }
        )
        #expect(violations.isEmpty, "Linear animations found:\n\(violations.map(\.description).joined(separator: "\n"))")
    }

    @Test("the lint actually sees the source tree")
    func sourceTreeResolves() {
        #expect(Self.swiftFiles().count > 20)
    }
}

// MARK: - 2. Token chroma audit

@Suite("Palette chroma audit (REQ-DSN-001)")
struct PaletteChromaTests {

    /// Resolves a SwiftUI Color to sRGB channels via AppKit.
    private func channels(_ color: Color) -> (r: CGFloat, g: CGFloat, b: CGFloat)? {
        guard let ns = NSColor(color).usingColorSpace(.sRGB) else { return nil }
        return (ns.redComponent, ns.greenComponent, ns.blueComponent)
    }

    @Test("every semantic role is a neutral grey in both modes")
    func rolesAreAchromatic() {
        for mode in ThemeMode.allCases {
            let theme = Theme(mode: mode)
            let roles: [(String, Color)] = [
                ("background", theme.background),
                ("surfaceRaised", theme.surfaceRaised),
                ("surfaceFloating", theme.surfaceFloating),
                ("textPrimary", theme.textPrimary),
                ("textSecondary", theme.textSecondary),
                ("textDisabled", theme.textDisabled),
                ("borderSubtle", theme.borderSubtle),
                ("borderStrong", theme.borderStrong),
                ("iconPrimary", theme.iconPrimary),
                ("iconSecondary", theme.iconSecondary),
                ("selectionFill", theme.selectionFill),
                ("selectionBorder", theme.selectionBorder),
                ("hairline", theme.hairline),
            ]
            for (name, color) in roles {
                guard let (r, g, b) = channels(color) else {
                    Issue.record("\(mode)/\(name): could not resolve to sRGB")
                    continue
                }
                let chroma = max(abs(r - g), abs(g - b), abs(r - b))
                #expect(chroma < 0.01, "\(mode)/\(name) is chromatic (Δ=\(chroma))")
            }
        }
    }
}

// MARK: - 3. Offscreen render chroma audit

@Suite("Offscreen render chroma audit (REQ-DSN-001)")
@MainActor
struct RenderChromaTests {

    /// A composed swatch exercising the ink ramp + achromatic text + an SF Symbol.
    private struct Swatch: View {
        let mode: ThemeMode
        var body: some View {
            let theme = Theme(mode: mode)
            return VStack(spacing: 0) {
                ForEach([Ink.ink0, Ink.ink10, Ink.ink40, Ink.ink60, Ink.ink90, Ink.ink100], id: \.self) { ink in
                    Rectangle().fill(ink).frame(height: 12)
                }
                HStack(spacing: 4) {
                    Image(systemName: "circle.hexagongrid").foregroundStyle(theme.iconSecondary)
                    Text("Archon").archonText(.caption).foregroundStyle(theme.textPrimary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(theme.background)
            }
            .frame(width: 160, height: 160)
            .background(theme.background)
            .environment(\.archonTheme, theme)
        }
    }

    private func maxChroma(of image: CGImage) -> Int {
        let width = image.width, height = image.height
        let bytesPerPixel = 4, bytesPerRow = width * bytesPerPixel
        var data = [UInt8](repeating: 0, count: height * bytesPerRow)
        let space = CGColorSpaceCreateDeviceRGB()
        guard let ctx = CGContext(
            data: &data, width: width, height: height, bitsPerComponent: 8,
            bytesPerRow: bytesPerRow, space: space,
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
        ) else { return 0 }
        ctx.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))
        var worst = 0
        var i = 0
        while i < data.count {
            let a = Int(data[i + 3])
            if a > 0 {
                let r = Int(data[i]), g = Int(data[i + 1]), b = Int(data[i + 2])
                worst = max(worst, abs(r - g), abs(g - b), abs(r - b))
            }
            i += bytesPerPixel
        }
        return worst
    }

    @Test("a rendered swatch has no chromatic pixels in either mode")
    func swatchIsAchromatic() {
        for mode in ThemeMode.allCases {
            let renderer = ImageRenderer(content: Swatch(mode: mode))
            renderer.scale = 1
            guard let cg = renderer.cgImage else {
                Issue.record("ImageRenderer produced no image for \(mode)")
                continue
            }
            // Matches the validator's audit threshold: |R−G| or |G−B| > 2.
            #expect(maxChroma(of: cg) <= 2, "\(mode): rendered swatch has chromatic pixels")
        }
    }
}

// MARK: - Token & breakpoint lock-in (this phase's fixes)

@Suite("Design token scale (REQ-DSN-032/049)")
struct DesignTokenScaleTests {

    @Test("IconSize.caption is the 12-pt inline-glyph tier")
    func captionIcon() {
        #expect(IconSize.caption == 12)
        // Grid-aligned with the rest of the icon set.
        for size in [IconSize.caption, IconSize.inline, IconSize.row, IconSize.nav, IconSize.emptyState] {
            #expect(size.truncatingRemainder(dividingBy: 4) == 0)
        }
    }

    @Test("type scale keeps the caption / monoSm roles used for small text")
    func typeScale() {
        #expect(TextStyle.caption.size == 12)
        #expect(TextStyle.monoSm.size == 11)
    }
}

@Suite("Responsive breakpoints (REQ-DSN-042)")
struct BreakpointTests {

    @Test("compact tier below 1100 pt, regular at/above")
    func compactTier() {
        #expect(Breakpoint.isCompact(windowWidth: 900))
        #expect(Breakpoint.isCompact(windowWidth: 950))
        #expect(Breakpoint.isCompact(windowWidth: 1099))
        #expect(!Breakpoint.isCompact(windowWidth: 1100))
        #expect(!Breakpoint.isCompact(windowWidth: 1440))
    }

    @Test("conductor edge auto-collapses only in the compact tier")
    func drawerCollapse() {
        #expect(Breakpoint.collapsesConductorEdge(windowWidth: 950))
        #expect(!Breakpoint.collapsesConductorEdge(windowWidth: 1440))
    }

    @Test("sidebar width steps at the normative boundaries 1099/1100/1599/1600")
    func sidebarWidthSteps() {
        #expect(Breakpoint.sidebarWidth(forWindowWidth: 1099) == Breakpoint.railWidth)
        #expect(Breakpoint.sidebarWidth(forWindowWidth: 1100) == 220)
        #expect(Breakpoint.sidebarWidth(forWindowWidth: 1599) == 220)
        #expect(Breakpoint.sidebarWidth(forWindowWidth: 1600) == 260)
        #expect(Breakpoint.railWidth == 48)
    }
}

@Suite("Conductor-edge drawer is a distinct agenda (§5.10 / REQ-DSN-095)")
struct BoardDrawerTests {

    @Test("agenda lists actionable columns in priority order and omits Done")
    func agendaOrder() {
        let order = BoardDrawerView.agendaOrder
        #expect(order == [.inProgress, .blocked, .review, .queued])
        #expect(!order.contains(.done))
        // It is NOT the full five-column board (that stays the ⌘4 main pane).
        #expect(order.count < BoardColumn.allCases.count)
    }
}
