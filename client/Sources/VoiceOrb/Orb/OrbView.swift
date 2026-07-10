import SwiftUI
import AppKit

/// The floating orb (REQ-DSN-051/052/057). The sole animated chromatic field in
/// the app. Rendered with `TimelineView` + `Canvas`: a two-layer domain-warped
/// fluid of drifting radial-gradient blobs plus a screen-composited bloom.
///
/// Render posture follows `presentation.motion`:
/// - Reduce Motion → a *static* radial gradient, no timeline (REQ-DSN-071).
/// - Low Power → 30 Hz timeline, bloom hidden (REQ-DSN-072).
/// - Otherwise → animation-cadence timeline (targets 120 Hz, REQ-DSN-053).
///
/// The per-frame CPU loop does NOT run forever: the timeline pauses when the orb
/// is idle with no voice (after a short graceful settle) and hard-pauses when the
/// host window is occluded / minimized / hidden (REQ-PERF-015 / REQ-DSN-074), so
/// steady-state idle CPU stays within budget (REQ-PERF-006).
///
/// The disconnected variant dims the whole orb (Addendum §A4) without changing
/// its hue/state.
struct OrbView: View {
    var presentation: OrbPresentation
    /// 0…1 voice amplitude envelope for reactive glow/turbulence (REQ-DSN-054).
    var amplitude: Double

    /// Whether the orb's window is on screen (driven by the occlusion probe).
    @State private var windowVisible = true
    /// Whether the animation timeline is currently running (settle-gated).
    @State private var animate = true

    /// Combined idle/occlusion gate key; a change restarts the settle task.
    private struct GateKey: Equatable { let wants: Bool; let visible: Bool }

    private var wantsAnimation: Bool {
        OrbRenderGate.wantsAnimation(
            state: presentation.state, amplitude: amplitude, windowVisible: windowVisible
        )
    }

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
        .background(OrbOcclusionProbe { visible in
            if windowVisible != visible { windowVisible = visible }
        })
        .task(id: GateKey(wants: wantsAnimation, visible: windowVisible)) {
            if wantsAnimation {
                animate = true                      // resume immediately
            } else if !windowVisible {
                animate = false                     // hard pause off-screen, no settle
            } else {
                // Quiescent but visible: keep animating briefly, then settle.
                try? await Task.sleep(for: OrbRenderGate.settle)
                if !Task.isCancelled { animate = false }
            }
        }
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
        TimelineView(.animation(minimumInterval: schedule.minInterval, paused: !animate)) { context in
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
            // blended additively. Blob motion uses mutually incommensurate
            // frequencies (OrbFluidField) → quasi-periodic, non-repeating for
            // ≥ 120 s (REQ-DSN-074).
            var fluid = layer
            fluid.blendMode = .plusLighter
            for i in 0..<OrbFluidField.blobCount {
                let offset = OrbFluidField.offset(
                    blob: i, time: time, flowSpeed: model.flowSpeed,
                    radius: Double(radius), turbulence: model.turbulence
                )
                let bx = center.x + CGFloat(offset.x)
                let by = center.y + CGFloat(offset.y)
                let blobR = CGFloat(OrbFluidField.blobRadius(
                    blob: i, time: time, flowSpeed: model.flowSpeed, radius: Double(radius)
                ))
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

/// Zero-size AppKit probe that reports whether the orb's host window is actually
/// visible — not occluded, minimized, or app-hidden — so the render loop can
/// hard-pause off screen (REQ-DSN-074 / REQ-PERF-015). It observes the window's
/// occlusion/miniaturize notifications plus app hide/unhide; SwiftUI's own
/// occlusion pausing is implicit, so this makes the guarantee explicit and lets
/// the idle-settle gate compose with it.
private struct OrbOcclusionProbe: NSViewRepresentable {
    let onChange: (Bool) -> Void

    func makeCoordinator() -> Coordinator { Coordinator(onChange: onChange) }

    func makeNSView(context: Context) -> NSView {
        let view = NSView(frame: .zero)
        context.coordinator.attach(to: view)
        return view
    }

    func updateNSView(_ nsView: NSView, context: Context) {
        context.coordinator.onChange = onChange
        context.coordinator.attach(to: nsView)
    }

    static func dismantleNSView(_ nsView: NSView, coordinator: Coordinator) {
        coordinator.detach()
    }

    @MainActor
    final class Coordinator {
        var onChange: (Bool) -> Void
        private weak var view: NSView?
        private var observers: [NSObjectProtocol] = []
        private var lastVisible = true

        init(onChange: @escaping (Bool) -> Void) { self.onChange = onChange }

        func attach(to view: NSView) {
            self.view = view
            if view.window == nil {
                // Window is assigned after the view joins the hierarchy.
                DispatchQueue.main.async { [weak self, weak view] in
                    guard let self, let view, view.window != nil else { return }
                    self.installObservers()
                    self.publish()
                }
            } else {
                installObservers()
                publish()
            }
        }

        private func installObservers() {
            guard observers.isEmpty else { return }
            let nc = NotificationCenter.default
            let names: [NSNotification.Name] = [
                NSWindow.didChangeOcclusionStateNotification,
                NSWindow.didMiniaturizeNotification,
                NSWindow.didDeminiaturizeNotification,
                NSApplication.didHideNotification,
                NSApplication.didUnhideNotification
            ]
            for name in names {
                let token = nc.addObserver(forName: name, object: nil, queue: .main) { [weak self] _ in
                    MainActor.assumeIsolated { self?.publish() }
                }
                observers.append(token)
            }
        }

        private func publish() {
            let visible = Self.isVisible(view?.window)
            guard visible != lastVisible else { return }
            lastVisible = visible
            onChange(visible)
        }

        static func isVisible(_ window: NSWindow?) -> Bool {
            guard let window else { return true }
            if NSApp.isHidden { return false }
            let target = window.parent ?? window
            if target.isMiniaturized { return false }
            return window.occlusionState.contains(.visible)
        }

        func detach() {
            let nc = NotificationCenter.default
            observers.forEach { nc.removeObserver($0) }
            observers.removeAll()
        }
    }
}
