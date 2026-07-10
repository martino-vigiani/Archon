import SwiftUI

/// The floating orb (REQ-DSN-051/052/057). The sole animated chromatic field in
/// the app. Rendered with `TimelineView` + `Canvas`: a two-layer domain-warped
/// fluid of drifting radial-gradient blobs plus a screen-composited bloom.
///
/// Render posture follows `presentation.motion`:
/// - Reduce Motion → a *static* radial gradient, no timeline (REQ-DSN-071).
/// - Low Power → 30 Hz timeline, bloom hidden (REQ-DSN-072).
/// - Otherwise → animation-cadence timeline (targets 120 Hz, REQ-DSN-053).
///
/// The disconnected variant dims the whole orb (Addendum §A4) without changing
/// its hue/state.
struct OrbView: View {
    var presentation: OrbPresentation
    /// 0…1 voice amplitude envelope for reactive glow/turbulence (REQ-DSN-054).
    var amplitude: Double

    var body: some View {
        let model = OrbRenderModel.model(for: presentation.state)
        let gradient = OrbHue.gradient(for: presentation.state)
        let canvasSide = OrbRenderModel.listeningDiameter * 2.2   // room for bloom

        Group {
            if presentation.motion.rendersStaticField {
                staticOrb(model: model, gradient: gradient, side: canvasSide)
            } else {
                animatedOrb(model: model, gradient: gradient, side: canvasSide)
            }
        }
        .frame(width: canvasSide, height: canvasSide)
        .opacity(presentation.isDisconnected ? 0.38 : 1)
        .saturation(presentation.isDisconnected ? 0.5 : 1)
        .animation(.easeInOut(duration: 0.25), value: presentation.isDisconnected)
        .animation(.easeInOut(duration: 0.5), value: presentation.state)
        .accessibilityElement()
        .accessibilityLabel(presentation.state.accessibilityLabel)
        .accessibilityAddTraits(.updatesFrequently)
    }

    // MARK: - Animated (fluid) orb

    @ViewBuilder
    private func animatedOrb(model: OrbRenderModel, gradient: OrbGradient, side: CGFloat) -> some View {
        let schedule: OrbTimelineSchedule = presentation.motion.targetHz <= 30
            ? .lowPower
            : .promotion
        TimelineView(.animation(minimumInterval: schedule.minInterval, paused: false)) { context in
            let t = context.date.timeIntervalSinceReferenceDate
            Canvas(rendersAsynchronously: false) { ctx, size in
                drawOrb(ctx: &ctx, size: size, time: t, model: model, gradient: gradient)
            }
            .drawingGroup(opaque: false)
        }
    }

    // MARK: - Static (reduced-motion) orb

    @ViewBuilder
    private func staticOrb(model: OrbRenderModel, gradient: OrbGradient, side: CGFloat) -> some View {
        let d = model.baseDiameter
        Circle()
            .fill(
                RadialGradient(
                    gradient: Gradient(colors: [gradient.core, gradient.mid, gradient.edge]),
                    center: .center,
                    startRadius: 1,
                    endRadius: d * 0.62
                )
            )
            .frame(width: d, height: d)
            .frame(width: side, height: side)
    }

    // MARK: - Canvas drawing

    private func drawOrb(
        ctx: inout GraphicsContext,
        size: CGSize,
        time: Double,
        model: OrbRenderModel,
        gradient: OrbGradient
    ) {
        let center = CGPoint(x: size.width / 2, y: size.height / 2)
        let flow = time * model.flowSpeed
        let diameter = model.diameter(time: time, amplitude: amplitude)
        let radius = diameter / 2

        // --- Bloom (screen-composited soft halo, REQ-DSN-058) ---
        if presentation.motion.bloomEnabled {
            let glow = model.glowRadius(diameter: diameter, amplitude: amplitude)
            var bloom = ctx
            bloom.addFilter(.blur(radius: glow * 0.5))
            bloom.blendMode = .screen
            bloom.opacity = 0.55
            let bloomRect = CGRect(x: center.x - glow, y: center.y - glow, width: glow * 2, height: glow * 2)
            bloom.fill(
                Circle().path(in: bloomRect),
                with: .radialGradient(
                    Gradient(colors: [gradient.glow.opacity(0.9), gradient.glow.opacity(0)]),
                    center: center, startRadius: 0, endRadius: glow
                )
            )
        }

        // --- Orb body: base sphere clip ---
        let bodyRect = CGRect(x: center.x - radius, y: center.y - radius, width: diameter, height: diameter)
        let bodyPath = Circle().path(in: bodyRect)
        ctx.drawLayer { layer in
            layer.clip(to: bodyPath)

            // Base fill.
            layer.fill(
                bodyPath,
                with: .radialGradient(
                    Gradient(colors: [gradient.mid, gradient.edge]),
                    center: center, startRadius: 0, endRadius: radius
                )
            )

            // Two-layer domain-warped fluid: several drifting bright blobs
            // blended additively → non-repeating, physically-plausible motion.
            var fluid = layer
            fluid.blendMode = .plusLighter
            let blobCount = 5
            for i in 0..<blobCount {
                let phase = Double(i) * 1.7
                // Layer 1 drift.
                let ax = sin(flow * 0.6 + phase) * Double(radius) * 0.5 * model.turbulence
                let ay = cos(flow * 0.5 + phase * 1.3) * Double(radius) * 0.5 * model.turbulence
                // Layer 2 warp of the drift (domain warp).
                let wx = sin(flow * 0.9 + ay * 0.03) * Double(radius) * 0.22
                let wy = cos(flow * 0.8 + ax * 0.03) * Double(radius) * 0.22
                let bx = center.x + CGFloat(ax + wx)
                let by = center.y + CGFloat(ay + wy)
                let blobR = radius * (0.5 + 0.18 * CGFloat(sin(flow + phase)))
                let color = i % 2 == 0 ? gradient.core : gradient.mid
                let rect = CGRect(x: bx - blobR, y: by - blobR, width: blobR * 2, height: blobR * 2)
                fluid.fill(
                    Circle().path(in: rect),
                    with: .radialGradient(
                        Gradient(colors: [color.opacity(0.9), color.opacity(0)]),
                        center: CGPoint(x: bx, y: by), startRadius: 0, endRadius: blobR
                    )
                )
            }

            // Specular highlight (top-left) for a glassy sphere read.
            let hl = CGRect(x: center.x - radius * 0.5, y: center.y - radius * 0.62,
                            width: radius * 0.8, height: radius * 0.8)
            layer.fill(
                Circle().path(in: hl),
                with: .radialGradient(
                    Gradient(colors: [Color.white.opacity(0.5), Color.white.opacity(0)]),
                    center: CGPoint(x: hl.midX, y: hl.midY), startRadius: 0, endRadius: radius * 0.5
                )
            )
        }

        // Rim light for definition against dark chrome.
        ctx.stroke(bodyPath, with: .color(gradient.core.opacity(0.35)), lineWidth: 1)
    }
}

/// Timeline cadence presets. `.animation` targets the display refresh (up to
/// 120 Hz on ProMotion, REQ-DSN-053); Low Power drops to 30 Hz (REQ-DSN-072).
private enum OrbTimelineSchedule {
    case promotion
    case lowPower

    var minInterval: Double {
        switch self {
        case .promotion: return 1.0 / 120.0
        case .lowPower: return 1.0 / 30.0
        }
    }
}
