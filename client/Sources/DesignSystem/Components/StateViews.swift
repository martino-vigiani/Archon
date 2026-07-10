import SwiftUI

/// Explicit empty state (REQ-UX-090): a single concise instruction + optional
/// activation affordance. No blank areas.
struct EmptyStateView: View {
    var systemImage: String
    var title: String
    var message: String?
    var actionTitle: String?
    var action: (() -> Void)?
    @Environment(\.archonTheme) private var theme

    var body: some View {
        VStack(spacing: Space.md) {
            Image(systemName: systemImage)
                .font(.system(size: IconSize.emptyState, weight: .light))
                .foregroundStyle(theme.iconSecondary)
            VStack(spacing: Space.xs) {
                Text(title)
                    .archonText(.title2)
                    .foregroundStyle(theme.textPrimary)
                if let message {
                    Text(message)
                        .archonText(.body)
                        .foregroundStyle(theme.textSecondary)
                        .multilineTextAlignment(.center)
                }
            }
            if let actionTitle, let action {
                Button(actionTitle, action: action)
                    .archonButtonStyle(.secondary)
            }
        }
        .padding(Space.xl)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .accessibilityElement(children: .combine)
    }
}

/// Achromatic skeleton shimmer for initial load (REQ-UX-091). No spinner modal.
/// Honors Reduce Motion (static under reduce).
struct SkeletonView: View {
    var cornerRadius: CGFloat = Radius.badge
    @Environment(\.archonTheme) private var theme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var phase: CGFloat = -1

    var body: some View {
        RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
            .fill(theme.surfaceRaised)
            .overlay {
                if !reduceMotion {
                    GeometryReader { geo in
                        LinearGradient(
                            colors: [.clear, theme.borderSubtle.opacity(0.6), .clear],
                            startPoint: .leading,
                            endPoint: .trailing
                        )
                        .frame(width: geo.size.width * 0.5)
                        .offset(x: phase * geo.size.width)
                    }
                    .clipShape(RoundedRectangle(cornerRadius: cornerRadius, style: .continuous))
                }
            }
            .onAppear {
                guard !reduceMotion else { return }
                withAnimation(.easeInOut(duration: 1.2).repeatForever(autoreverses: false)) {
                    phase = 1.5
                }
            }
            .accessibilityHidden(true)
    }
}

/// A vertical stack of skeleton rows for list placeholders.
struct SkeletonList: View {
    var rows: Int = 5
    var body: some View {
        VStack(spacing: Space.sm) {
            ForEach(0..<rows, id: \.self) { _ in
                SkeletonView().frame(height: 20)
            }
        }
        .padding(Space.md)
    }
}

/// Inline error state (REQ-UX-093/094): plain language + next action, no raw
/// stack trace.
struct ErrorStateView: View {
    var title: String
    var message: String
    var retryTitle: String?
    var retry: (() -> Void)?
    @Environment(\.archonTheme) private var theme

    var body: some View {
        VStack(spacing: Space.md) {
            Image(systemName: "exclamationmark.triangle")
                .font(.system(size: IconSize.emptyState, weight: .light))
                .foregroundStyle(theme.iconSecondary)
            VStack(spacing: Space.xs) {
                Text(title)
                    .archonText(.title2)
                    .foregroundStyle(theme.textPrimary)
                Text(message)
                    .archonText(.body)
                    .foregroundStyle(theme.textSecondary)
                    .multilineTextAlignment(.center)
            }
            if let retryTitle, let retry {
                Button(retryTitle, action: retry)
                    .archonButtonStyle(.primary)
            }
        }
        .padding(Space.xl)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

/// Persistent non-modal disconnection banner (REQ-UX-092).
struct DisconnectedBanner: View {
    var message: String = "Disconnected from orchestrator — reconnecting…"
    @Environment(\.archonTheme) private var theme

    var body: some View {
        HStack(spacing: Space.sm) {
            Image(systemName: "bolt.horizontal.circle")
                .font(.system(size: IconSize.row, weight: .medium))
                .foregroundStyle(theme.iconSecondary)
            Text(message)
                .archonText(.caption)
                .foregroundStyle(theme.textSecondary)
            Spacer(minLength: 0)
        }
        .padding(.horizontal, Space.md)
        .padding(.vertical, Space.sm)
        .archonMaterial(.flatElevated, cornerRadius: Radius.input)
        .overlay {
            RoundedRectangle(cornerRadius: Radius.input, style: .continuous)
                .strokeBorder(theme.borderSubtle, lineWidth: Space.hairline)
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(message)
    }
}
