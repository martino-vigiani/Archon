import SwiftUI

/// Provenance shown by SHAPE + PATTERN + WEIGHT, never color (§5.1-5.2 / strict
/// B/W). `user` = solid-outline pill with a filled glyph; `conductor` = dashed
/// pill with a light "assistant" glyph — differentiable in a pixel audit with
/// zero chroma.
struct ProvenanceBadge: View {
    let provenance: Initiator
    @Environment(\.archonTheme) private var theme

    private var glyph: String {
        switch provenance {
        case .user: return "person.fill"
        case .conductor: return "sparkles"
        case .unknown: return "questionmark"
        }
    }

    private var label: String {
        switch provenance {
        case .user: return "You"
        case .conductor: return "Conductor"
        case .unknown: return "—"
        }
    }

    private var dashed: Bool { provenance == .conductor }

    var body: some View {
        HStack(spacing: Space.xs) {
            Image(systemName: glyph)
                .font(.system(size: 9, weight: provenance == .user ? .bold : .regular))
            Text(label)
                .archonText(.monoSm)
        }
        .foregroundStyle(theme.textSecondary)
        .padding(.horizontal, Space.sm)
        .padding(.vertical, 2)
        .overlay {
            RoundedRectangle(cornerRadius: Radius.badge, style: .continuous)
                .strokeBorder(
                    theme.borderStrong,
                    style: StrokeStyle(lineWidth: Space.hairline, dash: dashed ? [3, 2] : [])
                )
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Created by \(label)")
    }
}
