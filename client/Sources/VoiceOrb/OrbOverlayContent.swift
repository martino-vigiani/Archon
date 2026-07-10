import SwiftUI

/// The SwiftUI content hosted inside the floating orb panel: the orb itself and,
/// when there's conductor activity (or the user pins it open), the Conductor
/// surface floating above it. Because this lives in an `NSHostingView` outside
/// the main window's SwiftUI environment, it injects the app theme explicitly.
///
/// It reads the coordinator's `@Observable` state directly, so the hosting view
/// re-renders via Observation without the representable pushing new content.
struct OrbOverlayContent: View {
    @Bindable var coordinator: VoiceOrbCoordinator
    @AppStorage("archon.themeMode") private var themeModeRaw: String = ThemeMode.dark.rawValue
    @State private var pinnedOpen = false

    private var themeMode: ThemeMode { ThemeMode(rawValue: themeModeRaw) ?? .dark }

    private var showsSurface: Bool {
        coordinator.hasConductorActivity || pinnedOpen
    }

    var body: some View {
        VStack(spacing: Space.sm) {
            if showsSurface {
                ConductorSurfaceView(
                    conductor: coordinator.conductor,
                    voice: coordinator.voice
                )
                .frame(maxWidth: 460)
                .transition(.move(edge: .bottom).combined(with: .opacity))
            }

            ConductorEdgeAffordance(isExpanded: $pinnedOpen)

            OrbView(
                presentation: coordinator.orbPresentation,
                amplitude: coordinator.voice.amplitude
            )
            .contentShape(Circle())
            .onTapGesture { coordinator.orbClicked() }
            .help("Hold \(HotKeyBinding.defaultBinding.displayString) to speak")
        }
        .padding(Space.sm)
        .fixedSize()
        .animation(MotionEvent.terminalSpawn.animation(reduceMotion: coordinator.orbEnvironment.reduceMotion), value: showsSurface)
        .archonTheme(themeMode)
    }
}
