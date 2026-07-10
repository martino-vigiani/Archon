import SwiftUI

/// The top-level view: gates on project selection, injects the theme, and hosts
/// the three-pane shell once a project is open.
struct RootView: View {
    @Bindable var container: AppContainer
    @AppStorage("archon.themeMode") private var themeModeRaw: String = ThemeMode.dark.rawValue

    private var themeMode: ThemeMode {
        ThemeMode(rawValue: themeModeRaw) ?? .dark
    }

    var body: some View {
        Group {
            if container.appState.currentProjectURL == nil {
                ProjectLauncherView(container: container)
            } else {
                ThreePaneShell(appState: container.appState, registry: container.registry)
            }
        }
        .archonTheme(themeMode)
        .frame(minWidth: Breakpoint.minWindowWidth, minHeight: Breakpoint.minWindowHeight)
    }
}

/// The project launcher (Addendum §A2): open any directory or pick a recent.
struct ProjectLauncherView: View {
    @Bindable var container: AppContainer
    @Environment(\.archonTheme) private var theme

    var body: some View {
        VStack(spacing: Space.xl) {
            VStack(spacing: Space.sm) {
                Image(systemName: "circle.hexagongrid")
                    .font(.system(size: 44, weight: .light))
                    .foregroundStyle(theme.iconPrimary)
                Text("Archon")
                    .archonText(.display)
                    .foregroundStyle(theme.textPrimary)
                Text("Open any project directory to begin. Archon never writes inside it.")
                    .archonText(.body)
                    .foregroundStyle(theme.textSecondary)
                    .multilineTextAlignment(.center)
            }

            Button("Open Project…") {
                if let url = ProjectPicker.presentOpenPanel() {
                    Task { await container.openProject(at: url) }
                }
            }
            .archonButtonStyle(.primary)
            .keyboardShortcut("o", modifiers: .command)

            if !container.recentProjects.isEmpty {
                recentList
            }
        }
        .padding(Space.xxl)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(theme.background)
    }

    private var recentList: some View {
        VStack(alignment: .leading, spacing: Space.sm) {
            Text("Recent")
                .archonText(.caption)
                .foregroundStyle(theme.textSecondary)
            ForEach(container.recentProjects) { project in
                Button {
                    Task { await container.openProject(at: project.url) }
                } label: {
                    ArchonListRow {
                        Image(systemName: "folder")
                            .font(.system(size: IconSize.row))
                            .foregroundStyle(theme.iconSecondary)
                    } content: {
                        VStack(alignment: .leading, spacing: 0) {
                            Text(project.name)
                                .archonText(.bodyEmphasis)
                                .foregroundStyle(theme.textPrimary)
                            Text(project.path)
                                .archonText(.caption)
                                .foregroundStyle(theme.textSecondary)
                                .lineLimit(1)
                                .truncationMode(.middle)
                        }
                    }
                }
                .buttonStyle(.plain)
            }
        }
        .frame(maxWidth: 520)
        .padding(Space.md)
        .archonMaterial(.flatSurface, cornerRadius: Radius.card)
        .overlay {
            RoundedRectangle(cornerRadius: Radius.card, style: .continuous)
                .strokeBorder(theme.borderSubtle, lineWidth: Space.hairline)
        }
    }
}
