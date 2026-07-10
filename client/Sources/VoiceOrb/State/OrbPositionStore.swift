import CoreGraphics
import Foundation

/// Persists the orb's per-project position offset (Q17 / REQ-UX-042) as a small
/// JSON file under the project's Application Support state directory. NEVER
/// writes inside the project tree (Addendum §A3 zero-footprint).
@MainActor
final class OrbPositionStore: OrbPositionPersisting {
    private weak var container: AppContainer?

    init(container: AppContainer) {
        self.container = container
    }

    private var fileURL: URL? {
        guard let container,
              let projectURL = container.appState.currentProjectURL
        else { return nil }
        return container.projectStore
            .stateDirectory(forProjectAt: projectURL)
            .appendingPathComponent("orb-offset.json", isDirectory: false)
    }

    func loadOffset() -> CGPoint? {
        guard let fileURL,
              let data = try? Data(contentsOf: fileURL),
              let offset = try? JSONDecoder().decode(StoredOffset.self, from: data)
        else { return nil }
        return CGPoint(x: offset.x, y: offset.y)
    }

    func saveOffset(_ offset: CGPoint) {
        guard let fileURL else { return }
        let dir = fileURL.deletingLastPathComponent()
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let stored = StoredOffset(x: Double(offset.x), y: Double(offset.y))
        if let data = try? JSONEncoder().encode(stored) {
            try? data.write(to: fileURL, options: .atomic)
        }
    }

    private struct StoredOffset: Codable {
        var x: Double
        var y: Double
    }
}
