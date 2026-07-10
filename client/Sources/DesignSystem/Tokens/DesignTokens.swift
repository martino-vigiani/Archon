import SwiftUI

// ============================================================================
// DesignTokens — THE single canonical color file (REQ-DSN-002/003).
//
// STRICT RULE: this is the ONLY source file allowed to name raw palette steps
// or construct achromatic color literals. Every other file consumes semantic
// roles via `Theme`. No chromatic color anywhere in this module — color exists
// ONLY in the phase-B orb (REQ-DSN-011).
// ============================================================================

/// The achromatic ink ramp (REQ-DSN-001). All values are neutral grey
/// (R == G == B) in the sRGB space, so a pixel audit finds zero chroma.
enum Ink {
    /// Builds a neutral sRGB grey. Kept private-by-convention to this file.
    private static func grey(_ value: Double) -> Color {
        Color(.sRGB, red: value, green: value, blue: value, opacity: 1)
    }

    static let ink0   = grey(0.0)            // #000000 pure black
    static let ink5   = grey(13.0 / 255.0)   // #0D0D0D near-black surface
    static let ink10  = grey(26.0 / 255.0)   // #1A1A1A raised dark surface
    static let ink20  = grey(51.0 / 255.0)   // #333333 secondary dark
    static let ink40  = grey(102.0 / 255.0)  // #666666 mid-grey / disabled
    static let ink60  = grey(153.0 / 255.0)  // #999999 secondary text / borders
    static let ink80  = grey(204.0 / 255.0)  // #CCCCCC primary text on dark
    static let ink90  = grey(230.0 / 255.0)  // #E6E6E6 high-emphasis
    static let ink95  = grey(243.0 / 255.0)  // #F3F3F3 near-white surface
    static let ink100 = grey(1.0)            // #FFFFFF pure white
}

/// Light / Dark. Default is dark, independent of system appearance
/// (REQ-DSN-081).
enum ThemeMode: String, Sendable, CaseIterable {
    case dark
    case light

    var colorScheme: ColorScheme {
        switch self {
        case .dark: return .dark
        case .light: return .light
        }
    }
}

/// Resolves every semantic role to exactly one ink token per mode
/// (REQ-DSN-003 / REQ-DSN-082). The single role→token mapping in the app.
struct Theme: Sendable, Equatable {
    var mode: ThemeMode

    init(mode: ThemeMode = .dark) {
        self.mode = mode
    }

    private func pick(dark: Color, light: Color) -> Color {
        mode == .dark ? dark : light
    }

    // Surfaces
    var background: Color        { pick(dark: Ink.ink5,  light: Ink.ink95) }
    var surfaceRaised: Color     { pick(dark: Ink.ink10, light: Ink.ink90) }
    var surfaceFloating: Color   { pick(dark: Ink.ink10, light: Ink.ink95) }

    // Text
    var textPrimary: Color       { pick(dark: Ink.ink90, light: Ink.ink10) }
    var textSecondary: Color     { pick(dark: Ink.ink60, light: Ink.ink40) }
    var textDisabled: Color      { pick(dark: Ink.ink40, light: Ink.ink60) }

    // Borders
    var borderSubtle: Color      { pick(dark: Ink.ink20, light: Ink.ink80) }
    var borderStrong: Color      { pick(dark: Ink.ink40, light: Ink.ink60) }

    // Icons
    var iconPrimary: Color       { pick(dark: Ink.ink90, light: Ink.ink10) }
    var iconSecondary: Color     { pick(dark: Ink.ink60, light: Ink.ink40) }

    // Selection
    var selectionFill: Color     { pick(dark: Ink.ink20, light: Ink.ink80) }
    var selectionBorder: Color   { pick(dark: Ink.ink40, light: Ink.ink60) }

    /// A neutral hairline used for dividers / resize handles (`flat-hairline`).
    var hairline: Color { borderSubtle }
}

// MARK: - Environment plumbing

extension EnvironmentValues {
    /// The active theme. Injected at the root by `RootView` and read by every
    /// component. Defaults to dark (REQ-DSN-081).
    @Entry var archonTheme: Theme = Theme(mode: .dark)

    /// True when the shell is in the compact tier (< 1100 pt): feature sidebars
    /// render an icon rail instead of full rows (REQ-DSN-042). Set by the shell.
    @Entry var archonCompactLayout: Bool = false
}

extension View {
    /// Injects a resolved theme (and the matching color scheme) into the
    /// environment for a subtree. Mode changes cross-fade over 200 ms so a
    /// light/dark toggle animates rather than snapping (REQ-DSN-083).
    func archonTheme(_ mode: ThemeMode) -> some View {
        self
            .environment(\.archonTheme, Theme(mode: mode))
            .environment(\.colorScheme, mode.colorScheme)
            .preferredColorScheme(mode.colorScheme)
            .animation(.easeInOut(duration: 0.2), value: mode)
    }
}
