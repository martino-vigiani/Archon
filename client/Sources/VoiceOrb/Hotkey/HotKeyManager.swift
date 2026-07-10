import AppKit
import Carbon.HIToolbox

/// Registers a system-wide push-to-talk hotkey via Carbon `RegisterEventHotKey`
/// (Q13 / REQ-UX-036). This mechanism needs NO accessibility permission and is
/// notarization-compatible — it only observes its own registered chord, never
/// arbitrary keystrokes. Carbon delivers both `kEventHotKeyPressed` and
/// `kEventHotKeyReleased`, so hold-to-talk works: press → begin capture,
/// release → finalize.
@MainActor
final class HotKeyManager {

    /// Leading-edge press (begin capture).
    var onPressed: (() -> Void)?
    /// Release edge (finalize capture).
    var onReleased: (() -> Void)?

    private(set) var binding: HotKeyBinding?
    private var hotKeyRef: EventHotKeyRef?
    private var handlerRef: EventHandlerRef?
    private var ptt = PushToTalkState()

    private let signature: OSType = 0x4152_4348 // 'ARCH'
    private let hotKeyID: UInt32 = 1

    /// Whether a hotkey is currently registered.
    var isRegistered: Bool { hotKeyRef != nil }

    /// (Re)register the given binding. Safe to call repeatedly.
    func register(_ binding: HotKeyBinding) {
        unregister()
        self.binding = binding

        var eventTypes = [
            EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed)),
            EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyReleased)),
        ]
        let selfPtr = Unmanaged.passUnretained(self).toOpaque()
        InstallEventHandler(
            GetApplicationEventTarget(),
            archonHotKeyEventCallback,
            eventTypes.count,
            &eventTypes,
            selfPtr,
            &handlerRef
        )

        let hkID = EventHotKeyID(signature: signature, id: hotKeyID)
        RegisterEventHotKey(
            binding.keyCode,
            binding.modifiers,
            hkID,
            GetApplicationEventTarget(),
            0,
            &hotKeyRef
        )
    }

    /// Unregister and release any in-flight capture (so a stuck key cannot wedge
    /// the pipeline).
    func unregister() {
        if let hotKeyRef {
            UnregisterEventHotKey(hotKeyRef)
            self.hotKeyRef = nil
        }
        if let handlerRef {
            RemoveEventHandler(handlerRef)
            self.handlerRef = nil
        }
        if let action = ptt.reset() { deliver(action) }
        binding = nil
    }

    /// Called from the Carbon C trampoline (main thread) with the raw event kind.
    fileprivate func handle(eventKind kind: UInt32) {
        let action: PushToTalkState.Action?
        switch Int(kind) {
        case kEventHotKeyPressed: action = ptt.press()
        case kEventHotKeyReleased: action = ptt.release()
        default: action = nil
        }
        if let action { deliver(action) }
    }

    private func deliver(_ action: PushToTalkState.Action) {
        switch action {
        case .begin: onPressed?()
        case .end: onReleased?()
        }
    }
}

/// C trampoline for the Carbon event handler. Captures nothing (so it bridges to
/// a `@convention(c)` pointer) and hops onto the main actor — Carbon hotkey
/// events are already delivered on the main run loop.
private func archonHotKeyEventCallback(
    _ callRef: EventHandlerCallRef?,
    _ event: EventRef?,
    _ userData: UnsafeMutableRawPointer?
) -> OSStatus {
    guard let event, let userData else { return OSStatus(eventNotHandledErr) }
    let kind = GetEventKind(event)
    let manager = Unmanaged<HotKeyManager>.fromOpaque(userData).takeUnretainedValue()
    MainActor.assumeIsolated {
        manager.handle(eventKind: kind)
    }
    return noErr
}
