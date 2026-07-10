import Foundation

/// A global push-to-talk key binding (Q13). Pure value type with no Carbon
/// dependency so it is trivially testable and `Codable` for persistence. The
/// raw `keyCode`/`modifiers` are Carbon virtual-key + modifier-mask values,
/// consumed by `HotKeyManager`.
struct HotKeyBinding: Sendable, Equatable, Codable {
    /// Carbon virtual key code (e.g. Space = 49).
    var keyCode: UInt32
    /// Carbon modifier mask (bitwise OR of the `Modifier` values below).
    var modifiers: UInt32

    init(keyCode: UInt32, modifiers: UInt32) {
        self.keyCode = keyCode
        self.modifiers = modifiers
    }

    /// Carbon modifier masks (`Carbon/Events.h`), redeclared here so this file
    /// stays framework-free and unit-testable.
    enum Modifier: UInt32, CaseIterable {
        case command = 0x0100   // cmdKey
        case shift   = 0x0200   // shiftKey
        case option  = 0x0800   // optionKey
        case control = 0x1000   // controlKey
    }

    /// Space virtual key code (`kVK_Space`).
    static let spaceKeyCode: UInt32 = 49

    /// Default binding: ⌥Space (REQ-UX-030 default; rebindable later).
    static let defaultBinding = HotKeyBinding(
        keyCode: spaceKeyCode,
        modifiers: Modifier.option.rawValue
    )

    func contains(_ modifier: Modifier) -> Bool {
        modifiers & modifier.rawValue == modifier.rawValue
    }

    /// A human-readable glyph string, e.g. "⌥Space".
    var displayString: String {
        var glyphs = ""
        if contains(.control) { glyphs += "⌃" }
        if contains(.option) { glyphs += "⌥" }
        if contains(.shift) { glyphs += "⇧" }
        if contains(.command) { glyphs += "⌘" }
        return glyphs + keyName
    }

    private var keyName: String {
        switch keyCode {
        case HotKeyBinding.spaceKeyCode: return "Space"
        default: return "Key \(keyCode)"
        }
    }
}
