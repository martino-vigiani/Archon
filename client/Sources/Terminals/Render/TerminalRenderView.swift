import SwiftUI
import AppKit

// ============================================================================
// Terminals · Render · TerminalRenderView
//
// The PTY rendering engine view. AppKit/CoreText is justified here per Addendum
// §B (text throughput + virtualization). A custom flipped NSView inside an
// NSScrollView draws ONLY the line rows intersecting the visible/dirty rect
// (REQ-PERF-021 virtualization); scrollback beyond the viewport lives as raw
// model rows in the emulator ring (REQ-PERF-022). Redraw is driven by the
// session's coalesced `renderTick` (≤ 1/frame, REQ-PERF-020) and auto-follows
// the tail while the user is pinned to the bottom.
// ============================================================================

/// SwiftUI entry point. Reading `session.renderTick` in `body` makes SwiftUI
/// re-evaluate (and thus `updateNSView`) on every coalesced content bump.
struct TerminalRenderView: View {
    let session: TerminalSession
    var followsTail: Bool = true
    var fontSize: CGFloat = 13

    @Environment(\.archonTheme) private var theme

    var body: some View {
        _TerminalTextRepresentable(
            session: session,
            renderTick: session.renderTick,
            mode: theme.mode,
            followsTail: followsTail,
            fontSize: fontSize
        )
    }
}

// MARK: - Representable

private struct _TerminalTextRepresentable: NSViewRepresentable {
    let session: TerminalSession
    let renderTick: Int
    let mode: ThemeMode
    let followsTail: Bool
    let fontSize: CGFloat

    func makeCoordinator() -> Coordinator { Coordinator() }

    func makeNSView(context: Context) -> NSScrollView {
        let scroll = NSScrollView()
        scroll.drawsBackground = false
        scroll.hasVerticalScroller = true
        scroll.hasHorizontalScroller = false
        scroll.autohidesScrollers = true
        scroll.scrollerStyle = .overlay
        scroll.verticalScrollElasticity = .allowed

        let doc = TerminalDocumentView()
        doc.configure(session: session, mode: mode, fontSize: fontSize)
        doc.autoresizingMask = [.width]
        scroll.documentView = doc

        context.coordinator.doc = doc
        return scroll
    }

    func updateNSView(_ scroll: NSScrollView, context: Context) {
        guard let doc = context.coordinator.doc else { return }
        let wasPinned = context.coordinator.isPinnedToBottom(scroll: scroll)

        doc.configure(session: session, mode: mode, fontSize: fontSize)

        let width = scroll.contentSize.width
        let contentHeight = doc.contentHeight()
        let visibleHeight = scroll.contentSize.height
        doc.frame = NSRect(x: 0, y: 0, width: width, height: max(contentHeight, visibleHeight))
        doc.needsDisplay = true

        if followsTail && wasPinned {
            context.coordinator.scrollToBottom(scroll: scroll)
        }
    }

    @MainActor
    final class Coordinator {
        var doc: TerminalDocumentView?

        func isPinnedToBottom(scroll: NSScrollView) -> Bool {
            guard let doc else { return true }
            let clip = scroll.contentView.bounds
            // Flipped doc: bottom edge is at frame.height. Pinned when the
            // visible bottom is within ~2 lines of the content bottom.
            return clip.maxY >= doc.frame.height - doc.lineHeight * 2 - 1
        }

        func scrollToBottom(scroll: NSScrollView) {
            guard let doc else { return }
            let clip = scroll.contentView
            let maxY = max(0, doc.frame.height - clip.bounds.height)
            clip.scroll(to: NSPoint(x: 0, y: maxY))
            scroll.reflectScrolledClipView(clip)
        }
    }
}

// MARK: - Virtualized document view

/// Flipped NSView that draws only the visible band of terminal lines.
final class TerminalDocumentView: NSView {

    private weak var session: TerminalSession?
    private var mode: ThemeMode = .dark
    private var fontSize: CGFloat = 13
    private(set) var lineHeight: CGFloat = 18
    private var paper: NSColor = .clear

    override var isFlipped: Bool { true }

    func configure(session: TerminalSession, mode: ThemeMode, fontSize: CGFloat) {
        self.session = session
        self.mode = mode
        self.fontSize = fontSize
        self.lineHeight = ceil(fontSize * 1.38)
        self.paper = TerminalInkResolver.paperNSColor(mode: mode)
    }

    /// Total content height = renderable line count × line height.
    func contentHeight() -> CGFloat {
        CGFloat(max(1, session?.emulator.lineCount ?? 0)) * lineHeight
    }

    override func draw(_ dirtyRect: NSRect) {
        guard let session, lineHeight > 0 else { return }
        let count = session.emulator.lineCount
        guard count > 0 else { return }

        // Virtualization: only rows intersecting the dirty rect are laid out.
        let first = max(0, Int((dirtyRect.minY / lineHeight).rounded(.down)))
        let last = min(count, Int((dirtyRect.maxY / lineHeight).rounded(.up)))
        guard first < last else { return }

        let textWidth = max(1, bounds.width - 8)
        for index in first..<last {
            let line = session.emulator.line(at: index)
            let attributed = TerminalInkResolver.attributedString(
                for: line, mode: mode, fontSize: fontSize, paper: paper
            )
            let y = CGFloat(index) * lineHeight
            let rect = NSRect(x: 4, y: y + 1, width: textWidth, height: lineHeight)
            attributed.draw(with: rect, options: [.usesLineFragmentOrigin], context: nil)
        }
    }
}
