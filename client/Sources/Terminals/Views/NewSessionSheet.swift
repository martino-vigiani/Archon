import SwiftUI

// ============================================================================
// Terminals · Views · NewSessionSheet
//
// The manual "New session" affordance (REQ-UX task item 2): a task-prompt sheet
// that spawns a Claude Code PTY session via APIClient with initiator: .user
// (Addendum §A3 — user-initiated only). The session's cwd is the project root.
// ============================================================================

struct NewSessionSheet: View {
    let store: TerminalsStore
    @Binding var isPresented: Bool

    @Environment(\.archonTheme) private var theme
    @State private var prompt: String = ""
    @State private var spawning = false

    var body: some View {
        VStack(alignment: .leading, spacing: Space.lg) {
            VStack(alignment: .leading, spacing: Space.xs) {
                Text("New Session")
                    .archonText(.title2)
                    .foregroundStyle(theme.textPrimary)
                Text("Spawn a Claude Code terminal in the project. Describe the task, or leave it blank for an open session.")
                    .archonText(.caption)
                    .foregroundStyle(theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            if let dir = store.projectDir {
                HStack(spacing: Space.xs) {
                    Image(systemName: "folder")
                        .font(.system(size: IconSize.inline, weight: .regular))
                        .foregroundStyle(theme.iconSecondary)
                    Text(dir)
                        .archonText(.monoSm)
                        .foregroundStyle(theme.textSecondary)
                        .lineLimit(1)
                        .truncationMode(.middle)
                }
            }

            VStack(alignment: .leading, spacing: Space.xs) {
                Text("Task prompt")
                    .archonText(.caption)
                    .foregroundStyle(theme.textSecondary)
                TextEditor(text: $prompt)
                    .archonText(.monoBody)
                    .foregroundStyle(theme.textPrimary)
                    .scrollContentBackground(.hidden)
                    .padding(Space.sm)
                    .frame(minHeight: 120)
                    .archonMaterial(.flatElevated, cornerRadius: Radius.input)
                    .overlay {
                        RoundedRectangle(cornerRadius: Radius.input, style: .continuous)
                            .strokeBorder(theme.borderSubtle, lineWidth: Space.hairline)
                    }
            }

            HStack(spacing: Space.sm) {
                Spacer()
                Button("Cancel") { isPresented = false }
                    .archonButtonStyle(.secondary)
                    .keyboardShortcut(.cancelAction)
                Button(spawning ? "Spawning…" : "Spawn") { spawn() }
                    .archonButtonStyle(.primary)
                    .keyboardShortcut(.defaultAction)
                    .disabled(spawning || !store.canSpawn)
            }
        }
        .padding(Space.xl)
        .frame(width: 460)
        .background(theme.background)
    }

    private func spawn() {
        guard store.canSpawn else { return }
        spawning = true
        Task {
            await store.spawnSession(prompt: prompt)
            spawning = false
            isPresented = false
        }
    }
}
