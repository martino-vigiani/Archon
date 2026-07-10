import SwiftUI

/// The Archon macOS client entry point. A single primary window (REQ-UX-001)
/// hosting the three-pane shell + floating orb overlay.
@main
struct ArchonApp: App {
    @State private var container = AppContainer()

    var body: some Scene {
        Window("Archon", id: "archon.main") {
            RootView(container: container)
                .task { container.bootstrap() }
        }
        .defaultSize(width: 1280, height: 800)
        .commands {
            CommandGroup(replacing: .newItem) {
                Button("Open Project…") {
                    if let url = ProjectPicker.presentOpenPanel() {
                        Task { await container.openProject(at: url) }
                    }
                }
                .keyboardShortcut("o", modifiers: .command)
            }
            CommandGroup(after: .toolbar) {
                Picker("View", selection: Binding(
                    get: { container.appState.selectedPane },
                    set: { container.appState.selectedPane = $0 }
                )) {
                    ForEach(MainPane.allCases) { pane in
                        Text(pane.title).tag(pane)
                    }
                }
            }
        }
    }
}
