import SwiftUI

/// The visual weight of a button. All achromatic — contrast, not color, carries
/// hierarchy (REQ-DSN-093 typographic/tonal silence).
enum ArchonButtonKind: Sendable {
    case primary    // inverted high-contrast fill
    case secondary  // hairline outline
    case ghost      // text only
}

/// The one canonical button style for the app.
struct ArchonButtonStyle: ButtonStyle {
    let kind: ArchonButtonKind
    @Environment(\.archonTheme) private var theme
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        let pressed = configuration.isPressed
        return configuration.label
            .archonText(.bodyEmphasis)
            .foregroundStyle(foreground)
            .padding(.horizontal, Space.md)
            .padding(.vertical, Space.sm)
            .background {
                RoundedRectangle(cornerRadius: Radius.button, style: .continuous)
                    .fill(background(pressed: pressed))
            }
            .overlay {
                if kind == .secondary {
                    RoundedRectangle(cornerRadius: Radius.button, style: .continuous)
                        .strokeBorder(theme.borderStrong, lineWidth: Space.hairline)
                }
            }
            .opacity(isEnabled ? 1 : 0.5)
            .contentShape(Rectangle())
            .animation(Micro.tap, value: pressed)
    }

    private var foreground: Color {
        switch kind {
        case .primary: return theme.background
        case .secondary: return theme.textPrimary
        case .ghost: return theme.textSecondary
        }
    }

    private func background(pressed: Bool) -> Color {
        switch kind {
        case .primary:
            return pressed ? theme.textSecondary : theme.textPrimary
        case .secondary:
            return pressed ? theme.surfaceRaised : .clear
        case .ghost:
            return pressed ? theme.surfaceRaised : .clear
        }
    }
}

extension View {
    func archonButtonStyle(_ kind: ArchonButtonKind = .secondary) -> some View {
        buttonStyle(ArchonButtonStyle(kind: kind))
    }
}

/// A flat/glass panel container tagged with a single material class.
struct ArchonPanel<Content: View>: View {
    var material: ArchonMaterial = .flatSurface
    var cornerRadius: CGFloat = Radius.card
    var padding: CGFloat = Space.md
    var showsBorder: Bool = true
    @ViewBuilder var content: () -> Content
    @Environment(\.archonTheme) private var theme

    var body: some View {
        content()
            .padding(padding)
            .frame(maxWidth: .infinity, alignment: .leading)
            .archonMaterial(material, cornerRadius: cornerRadius)
            .overlay {
                if showsBorder {
                    RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                        .strokeBorder(theme.borderSubtle, lineWidth: Space.hairline)
                }
            }
    }
}

/// A standard selectable list row (achromatic selection fill, REQ-DSN-082).
struct ArchonListRow<Leading: View, Content: View>: View {
    var isSelected: Bool = false
    @ViewBuilder var leading: () -> Leading
    @ViewBuilder var content: () -> Content
    @Environment(\.archonTheme) private var theme

    var body: some View {
        HStack(spacing: Space.sm) {
            leading()
            content()
            Spacer(minLength: 0)
        }
        .padding(.horizontal, Space.sm)
        .padding(.vertical, Space.xs)
        .background {
            RoundedRectangle(cornerRadius: Radius.input, style: .continuous)
                .fill(isSelected ? theme.selectionFill : Color.clear)
        }
        .overlay {
            if isSelected {
                RoundedRectangle(cornerRadius: Radius.input, style: .continuous)
                    .strokeBorder(theme.selectionBorder, lineWidth: Space.hairline)
            }
        }
        .contentShape(Rectangle())
    }
}
