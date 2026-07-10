import SwiftUI

/// The five Liquid-Glass / flat surface classes (REQ-DSN-021). Every visible
/// background surface is tagged with exactly one via `archonMaterial(_:)`. No
/// glass surface carries a chromatic tint — vibrancy stays neutral
/// (REQ-DSN-023).
enum ArchonMaterial: Sendable {
    /// Blur + refractive rim + specular — orb shell, command palette, popovers,
    /// toasts.
    case glassFloating
    /// Reduced blur, no rim — primary sidebar, Conductor presence panel.
    case glassSidebar
    /// Solid achromatic, opaque, no blur — terminal panels, card bodies, main
    /// content bg. ALWAYS fully opaque (REQ-DSN-025).
    case flatSurface
    /// Solid, one ramp step from parent — column headers, selected row, tab bar.
    case flatElevated
    /// 1-px achromatic stroke, no fill — borders, dividers, resize handles.
    case flatHairline
}

private struct ArchonMaterialModifier: ViewModifier {
    let material: ArchonMaterial
    let cornerRadius: CGFloat
    @Environment(\.archonTheme) private var theme

    func body(content: Content) -> some View {
        switch material {
        case .glassFloating:
            content.background {
                RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                    .fill(.regularMaterial)
                    .overlay {
                        // Neutral refractive rim (leading/top), ≤ 0.5 opacity.
                        RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                            .strokeBorder(Ink.ink100.opacity(0.12), lineWidth: 1)
                    }
                    .shadow(color: Ink.ink0.opacity(0.2), radius: 6, x: 0, y: 2)
            }

        case .glassSidebar:
            content.background {
                Rectangle().fill(.ultraThinMaterial)
            }

        case .flatSurface:
            content.background {
                RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                    .fill(theme.background)
            }

        case .flatElevated:
            content.background {
                RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                    .fill(theme.surfaceRaised)
            }

        case .flatHairline:
            content.overlay {
                RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                    .strokeBorder(theme.hairline, lineWidth: Space.hairline)
            }
        }
    }
}

extension View {
    /// Tags a surface with exactly one material class (REQ-DSN-021).
    func archonMaterial(_ material: ArchonMaterial, cornerRadius: CGFloat = 0) -> some View {
        modifier(ArchonMaterialModifier(material: material, cornerRadius: cornerRadius))
    }

    /// A neutral 1-px divider (`flat-hairline`).
    func archonHairlineBorder(cornerRadius: CGFloat = 0) -> some View {
        modifier(ArchonMaterialModifier(material: .flatHairline, cornerRadius: cornerRadius))
    }
}
