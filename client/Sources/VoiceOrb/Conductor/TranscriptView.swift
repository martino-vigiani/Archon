import SwiftUI

/// A single turn in the exchange log (REQ-UX-031). User turns are right-leaning
/// emphasis; Conductor turns are left-leaning secondary. Achromatic — hierarchy
/// via tone/weight only (REQ-DSN-093).
struct ConductorMessageRow: View {
    let exchange: ConductorExchange
    @Environment(\.archonTheme) private var theme

    var body: some View {
        HStack(alignment: .top, spacing: Space.sm) {
            if exchange.role == .conductor {
                Image(systemName: "circle.hexagongrid")
                    .font(.system(size: IconSize.inline))
                    .foregroundStyle(theme.iconSecondary)
                    .padding(.top, 1)
            }
            Text(exchange.text)
                .archonText(exchange.role == .user ? .bodyEmphasis : .body)
                .foregroundStyle(exchange.role == .user ? theme.textPrimary : theme.textSecondary)
                .frame(maxWidth: .infinity, alignment: exchange.role == .user ? .trailing : .leading)
                .multilineTextAlignment(exchange.role == .user ? .trailing : .leading)
                .textSelection(.enabled)
        }
        .accessibilityElement(children: .combine)
    }
}

/// The live transcription preview shown while capturing (REQ-UX-031): partial
/// hypotheses are visually distinguished from finalized text (italic, secondary,
/// trailing caret). Never sent to the orchestrator — display-only (REQ-ARCH-032).
struct LiveTranscriptView: View {
    let text: String
    let isPreparing: Bool
    let downloadProgress: Double?
    @Environment(\.archonTheme) private var theme

    var body: some View {
        VStack(alignment: .leading, spacing: Space.xs) {
            if isPreparing {
                preparing
            } else {
                HStack(alignment: .firstTextBaseline, spacing: 2) {
                    Text(text.isEmpty ? "Listening…" : text)
                        .archonText(.body)
                        .italic()
                        .foregroundStyle(text.isEmpty ? theme.textDisabled : theme.textSecondary)
                    Rectangle()
                        .fill(theme.textSecondary)
                        .frame(width: 2, height: 16)
                        .opacity(0.8)
                        .accessibilityHidden(true)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(Space.sm)
        .archonMaterial(.flatElevated, cornerRadius: Radius.input)
        .accessibilityLabel(isPreparing ? "Preparing dictation" : "Live transcript: \(text)")
    }

    @ViewBuilder
    private var preparing: some View {
        HStack(spacing: Space.sm) {
            Image(systemName: "arrow.down.circle")
                .foregroundStyle(theme.iconSecondary)
            VStack(alignment: .leading, spacing: Space.xs) {
                Text("Preparing dictation")
                    .archonText(.captionEmphasis)
                    .foregroundStyle(theme.textPrimary)
                if let progress = downloadProgress {
                    ProgressView(value: progress)
                        .tint(theme.textSecondary)
                        .frame(maxWidth: 200)
                }
            }
        }
    }
}
