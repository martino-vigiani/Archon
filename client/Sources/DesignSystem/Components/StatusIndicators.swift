import SwiftUI

/// Monochrome mapping for the five-state status vocabulary (REQ-UX-060). Status
/// is conveyed by SF Symbol + label ONLY — never color (REQ-DSN-047).
extension SessionStatus {
    var systemImageName: String {
        switch self {
        case .idle:    return "circle"
        case .running: return "play.circle.fill"
        case .blocked: return "pause.circle"
        case .error:   return "xmark.octagon"
        case .done:    return "checkmark.circle.fill"
        case .unknown: return "questionmark.circle"
        }
    }

    var label: String {
        switch self {
        case .idle:    return "Idle"
        case .running: return "Running"
        case .blocked: return "Blocked"
        case .error:   return "Error"
        case .done:    return "Done"
        case .unknown: return "Unknown"
        }
    }
}

/// A compact monochrome status dot (icon only), for dense rows.
struct StatusDot: View {
    let status: SessionStatus
    var size: CGFloat = IconSize.inline
    @Environment(\.archonTheme) private var theme

    var body: some View {
        Image(systemName: status.systemImageName)
            .font(.system(size: size, weight: .medium))
            .foregroundStyle(theme.iconSecondary)
            .accessibilityLabel(status.label)
    }
}

/// A status badge: monochrome icon + label (REQ-UX-060).
struct StatusBadge: View {
    let status: SessionStatus
    var emphasized: Bool = false
    @Environment(\.archonTheme) private var theme

    var body: some View {
        HStack(spacing: Space.xs) {
            Image(systemName: status.systemImageName)
                .font(.system(size: IconSize.inline, weight: .medium))
                .foregroundStyle(emphasized ? theme.iconPrimary : theme.iconSecondary)
            Text(status.label)
                .archonText(.captionEmphasis)
                .foregroundStyle(emphasized ? theme.textPrimary : theme.textSecondary)
                .lineLimit(1)
                .fixedSize()
        }
        .padding(.horizontal, Space.sm)
        .padding(.vertical, Space.xs)
        .archonMaterial(.flatElevated, cornerRadius: Radius.badge)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Status: \(status.label)")
    }
}
