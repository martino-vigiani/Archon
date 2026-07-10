import SwiftUI

/// The Codebase main pane (`.main(.codebase)`, §4.8): a VS Code-like file tree
/// on the left and the singular read-only intelligence surface on the right
/// (preview when a file is selected, project overview otherwise). Strictly B/W,
/// read-only, self-contained.
struct CodebaseView: View {
    let store: CodebaseStore
    @Environment(\.archonTheme) private var theme

    init(store: CodebaseStore) {
        self.store = store
    }

    var body: some View {
        HSplitView {
            FileTreeView(store: store)
                .frame(minWidth: 220, idealWidth: 280, maxWidth: 380)
            IntelligencePane(store: store)
                .frame(minWidth: 420, maxWidth: .infinity)
        }
        .background(theme.background)
    }
}
