import Foundation

/// The pure, framework-free core of push-to-talk gating. Translates raw key
/// press/release edges into capture begin/end actions, swallowing duplicate
/// key-repeat "pressed" events while already capturing (Carbon can deliver
/// auto-repeat). Extracted from `HotKeyManager` so the logic is unit-testable
/// without registering a real global hotkey.
struct PushToTalkState: Sendable, Equatable {

    /// The action the caller should perform in response to a key edge.
    enum Action: Sendable, Equatable {
        case begin
        case end
    }

    private(set) var isCapturing: Bool = false

    init() {}

    /// A hotkey "pressed" edge. Returns `.begin` on the leading edge only;
    /// `nil` for auto-repeat while already capturing.
    mutating func press() -> Action? {
        guard !isCapturing else { return nil }
        isCapturing = true
        return .begin
    }

    /// A hotkey "released" edge. Returns `.end` only if a capture was active.
    mutating func release() -> Action? {
        guard isCapturing else { return nil }
        isCapturing = false
        return .end
    }

    /// Force-reset (e.g. on hotkey unregister / app resignation) so a stuck
    /// key can't wedge the capture state. Returns `.end` if it was capturing.
    mutating func reset() -> Action? {
        guard isCapturing else { return nil }
        isCapturing = false
        return .end
    }
}
