import SwiftUI

/// The 4-pt spacing grid (REQ-DSN-041). All static measurements are multiples
/// of 4 pt.
enum Space {
    static let xs: CGFloat = 4
    static let sm: CGFloat = 8
    static let md: CGFloat = 16
    static let lg: CGFloat = 24
    static let xl: CGFloat = 32
    static let xxl: CGFloat = 48
    /// 1-px hairline (the only permitted sub-4-pt static measurement).
    static let hairline: CGFloat = 1
}

/// Normative corner radii (REQ-DSN-043).
enum Radius {
    static let floatingPanel: CGFloat = 16
    static let card: CGFloat = 12
    static let button: CGFloat = 8
    static let input: CGFloat = 6
    static let badge: CGFloat = 4
}

/// Icon sizes aligned to the grid (REQ-DSN-049).
enum IconSize {
    static let inline: CGFloat = 16     // inline / caption
    static let row: CGFloat = 20        // toolbar / row actions
    static let nav: CGFloat = 24        // primary nav
    static let emptyState: CGFloat = 32 // empty-state illustrations
}

/// Layout breakpoints (REQ-DSN-042). Minimum window 900 × 600 pt.
enum Breakpoint {
    static let minWindowWidth: CGFloat = 900
    static let minWindowHeight: CGFloat = 600

    static let compactMax: CGFloat = 1099        // < 1100 → icon rail
    static let regularMax: CGFloat = 1599        // 1100–1599 → sidebar 220
    // ≥ 1600 → Wide (sidebar 260 + optional inspector)

    static func sidebarWidth(forWindowWidth width: CGFloat) -> CGFloat {
        if width < 1100 { return 48 }       // icon rail
        if width < 1600 { return 220 }
        return 260
    }
}
