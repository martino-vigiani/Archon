import AppKit

/// Presents an NSOpenPanel for choosing ANY directory as the active project
/// (Addendum §A2; non-sandboxed app has arbitrary-directory access).
enum ProjectPicker {
    @MainActor
    static func presentOpenPanel() -> URL? {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        panel.canCreateDirectories = false
        panel.prompt = "Open Project"
        panel.title = "Open Project"
        panel.message = "Choose any project directory. Archon never writes inside it."
        guard panel.runModal() == .OK else { return nil }
        return panel.url
    }
}
