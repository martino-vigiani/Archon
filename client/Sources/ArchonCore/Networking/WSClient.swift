import Foundation

/// Connection lifecycle surfaced to the app (drives the "reconnecting" banner,
/// REQ-UX-092, and the offline state, REQ-ARCH-080).
enum WSConnectionState: Sendable, Equatable {
    case idle
    case connecting
    case connected
    case reconnecting(attempt: Int)
    case incompatible
    case disconnected
}

/// Persistent WebSocket stream client (contract §3).
///
/// - Single full-duplex socket `ws://127.0.0.1:<port>/v3/stream?token=…`.
/// - Auto-reconnect with jittered exponential backoff (REQ-ARCH-007).
/// - Resume-by-seq on reconnect; gap detection issues `resume` (REQ-ARCH-005/008).
/// - Application heartbeat staleness → reconnect (REQ-ARCH-011).
/// - Decoded events fanned out to any number of `AsyncStream` subscribers.
///
/// Reconnection MUST NOT spawn/kill/duplicate anything (REQ-ARCH-007) — this
/// client only reads and requests replay; all mutations go through `APIClient`.
actor WSClient {

    private var baseURL: URL?          // ws://127.0.0.1:<port>
    private var token: String?
    private let backoff: BackoffPolicy
    private let staleTimeout: Duration

    private var task: URLSessionWebSocketTask?
    private var runTask: Task<Void, Never>?
    private var watchdog: Task<Void, Never>?
    private var seqTracker = SeqTracker()
    private var isActive = false
    private var lastInboundAt = Date()

    private var eventSubscribers: [UUID: AsyncStream<EventEnvelope>.Continuation] = [:]
    private var stateSubscribers: [UUID: AsyncStream<WSConnectionState>.Continuation] = [:]
    private var currentState: WSConnectionState = .idle

    /// Per-subscriber fan-out buffer bound (REQ-ARCH-009: the client never uses
    /// an unbounded queue). A consumer that falls this far behind is already
    /// broken; we drop the oldest events for it (the server's own
    /// drop-with-marker + a reconnect REST resync recover authoritative state)
    /// rather than let a busy `@MainActor` grow the buffer without bound. Sized
    /// so the aggregate across the handful of live subscribers (terminals,
    /// board, conductor, container pump) stays under the §3.5 64 MiB ceiling even
    /// at the ~44 KiB base64 of a 32 KiB max `pty_output` chunk
    /// (≈ 4 × 256 × 44 KiB ≈ 44 MiB worst case).

    init(backoff: BackoffPolicy = .reconnect, staleTimeout: Duration = .seconds(30)) {
        self.backoff = backoff
        self.staleTimeout = staleTimeout
    }

    // MARK: - Subscriptions (multicast fan-out)

    /// A new independent stream of decoded events. Multiple consumers are
    /// supported (grid, dashboard, board can each subscribe).
    static let fanOutBufferBound = 256

    func events() -> AsyncStream<EventEnvelope> {
        let (stream, continuation) = AsyncStream.makeStream(
            of: EventEnvelope.self,
            bufferingPolicy: .bufferingNewest(Self.fanOutBufferBound)
        )
        let id = UUID()
        eventSubscribers[id] = continuation
        continuation.onTermination = { [weak self] _ in
            Task { await self?.removeEventSubscriber(id) }
        }
        return stream
    }

    func connectionStates() -> AsyncStream<WSConnectionState> {
        let (stream, continuation) = AsyncStream.makeStream(of: WSConnectionState.self)
        let id = UUID()
        stateSubscribers[id] = continuation
        continuation.yield(currentState)
        continuation.onTermination = { [weak self] _ in
            Task { await self?.removeStateSubscriber(id) }
        }
        return stream
    }

    private func removeEventSubscriber(_ id: UUID) {
        eventSubscribers[id] = nil
    }

    private func removeStateSubscriber(_ id: UUID) {
        stateSubscribers[id] = nil
    }

    // MARK: - Lifecycle

    /// Points the client at an orchestrator and starts the connect/reconnect
    /// loop. `resumeFrom` seeds the replay cursor across a full client restart.
    func start(baseURL: URL, token: String, resumeFrom seq: Int64? = nil) {
        self.baseURL = baseURL
        self.token = token
        if let seq { seqTracker.reset(to: seq) }
        guard !isActive else { return }
        isActive = true
        runTask = Task { [weak self] in
            await self?.runLoop()
        }
    }

    func stop() {
        isActive = false
        runTask?.cancel()
        runTask = nil
        watchdog?.cancel()
        watchdog = nil
        task?.cancel(with: .goingAway, reason: nil)
        task = nil
        updateState(.disconnected)
    }

    /// Re-point the socket at a freshly (re)launched orchestrator instance and
    /// reconnect immediately (no backoff wait). Used by the supervisor
    /// crash-restart path: a restarted orchestrator is a BRAND-NEW event bus
    /// whose `seq` resets to 0, so the resume cursor MUST be dropped — otherwise
    /// every new event (seq ≤ the stale cursor) would be treated as a duplicate
    /// and silently discarded, and the app would stay stuck reconnecting. The
    /// caller re-fetches full REST snapshots to resync (REQ-ARCH-008).
    func reconfigure(baseURL: URL, token: String) {
        // Tear down the loop/socket pointed at the dead endpoint.
        runTask?.cancel()
        runTask = nil
        watchdog?.cancel()
        watchdog = nil
        task?.cancel(with: .goingAway, reason: nil)
        task = nil
        // New endpoint + fresh replay cursor.
        self.baseURL = baseURL
        self.token = token
        seqTracker.reset(to: nil)
        isActive = true
        runTask = Task { [weak self] in
            await self?.runLoop()
        }
    }

    /// The highest globally-ordered `seq` observed (the resume cursor).
    var lastSeq: Int64? { seqTracker.lastSeq }

    // MARK: - Control frames

    func send(_ frame: ClientControlFrame) async {
        guard let task else { return }
        do {
            let text = try frame.jsonText()
            try await task.send(.string(text))
        } catch {
            // A failed send implies a dead socket; the receive loop will notice.
        }
    }

    /// Subscribe to a subset of topics (REQ-BE-045). Default (no call) = all.
    func subscribe(topics: [StreamTopic]) async {
        await send(.subscribe(topics: topics))
    }

    // MARK: - Connect / reconnect loop

    private func runLoop() async {
        var attempt = 0
        while isActive && !Task.isCancelled {
            guard let url = streamURL() else {
                updateState(.disconnected)
                return
            }
            updateState(attempt == 0 ? .connecting : .reconnecting(attempt: attempt))

            let session = URLSession(configuration: .ephemeral)
            var request = URLRequest(url: url)
            if let token { request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
            let socket = session.webSocketTask(with: request)
            self.task = socket
            socket.resume()

            let closedNormally = await receiveUntilFailure(on: socket, session: session)
            self.task = nil

            if !isActive || Task.isCancelled { break }

            if closedNormally == .incompatible {
                updateState(.incompatible)
                return
            }

            // Reconnect with jittered backoff.
            attempt += 1
            let delay = backoff.duration(forAttempt: attempt)
            updateState(.reconnecting(attempt: attempt))
            try? await Task.sleep(for: delay)
        }
        // Only report a terminal .disconnected when we were actually stopped.
        // A `reconfigure()` cancels this loop while `isActive` stays true and
        // spins up a fresh loop; that replacement owns the connection state, so
        // the cancelled loop must not clobber it with .disconnected.
        if !isActive {
            updateState(.disconnected)
        }
    }

    private enum ClosureKind { case failure, incompatible }

    /// Receives frames until the socket fails/closes. Returns why it stopped.
    private func receiveUntilFailure(on socket: URLSessionWebSocketTask, session: URLSession) async -> ClosureKind {
        // On (re)connect: replay from the last seq, then live (contract §3.3).
        if let last = seqTracker.lastSeq {
            await send(.resume(afterSeq: last))
        }
        // Default subscription = all topics; explicit for clarity.
        await send(.subscribe(topics: StreamTopic.allCases))

        markInbound()
        startWatchdog()
        defer {
            watchdog?.cancel()
            watchdog = nil
            session.invalidateAndCancel()
        }

        while isActive && !Task.isCancelled {
            do {
                let message = try await socket.receive()
                markInbound()
                if let closure = handle(message: message) {
                    return closure
                }
            } catch {
                return .failure
            }
        }
        return .failure
    }

    private func handle(message: URLSessionWebSocketTask.Message) -> ClosureKind? {
        let data: Data
        switch message {
        case .string(let text):
            data = Data(text.utf8)
        case .data(let raw):
            data = raw
        @unknown default:
            return nil
        }

        guard let envelope = try? ArchonJSON.decode(EventEnvelope.self, from: data) else {
            // Unparseable / unknown frame → ignore, do not disconnect
            // (REQ-ARCH-006).
            return nil
        }

        // Version negotiation on the hello frame (REQ-ARCH-004).
        if case .hello(let hello) = envelope.event {
            if hello.pv != 1 {
                return .incompatible
            }
            if hello.truncated == true {
                // Buffer truncation: adopt current_seq and resume live from the
                // newest point (the app re-fetches full REST snapshots).
                seqTracker.reset(to: hello.currentSeq)
            } else if seqTracker.lastSeq == nil {
                seqTracker.reset(to: hello.currentSeq)
            }
            updateState(.connected)
            fanOut(envelope)
            return nil
        }

        // Connection-local repair frames (drop-markers, `rate_limited`) carry
        // `seq: null`: they are NOT part of the replayable stream, so deliver
        // them without gap tracking (REQ-ARCH-006).
        guard let seq = envelope.seq else {
            fanOut(envelope)
            return nil
        }

        // Gap detection on the globally-ordered seq (REQ-ARCH-005).
        switch seqTracker.observe(seq) {
        case .inOrder:
            fanOut(envelope)
        case .gap(let expected):
            // Do NOT deliver this frame yet and do NOT advance the cursor: a
            // single resume redelivers [expected, seq] in order (the replayed
            // frames arrive in-order and are fanned out exactly once). Resuming
            // from `expected - 1` re-requests the missing range starting at
            // `expected` (REQ-ARCH-005).
            let afterSeq = expected - 1
            Task { [weak self] in
                await self?.send(.resume(afterSeq: afterSeq))
            }
        case .duplicate:
            // Already delivered during a prior replay; drop.
            break
        }
        return nil
    }

    private func fanOut(_ envelope: EventEnvelope) {
        for continuation in eventSubscribers.values {
            continuation.yield(envelope)
        }
        if currentState != .connected {
            updateState(.connected)
        }
    }

    // MARK: - Heartbeat watchdog (REQ-ARCH-011)

    private func markInbound() {
        lastInboundAt = Date()
    }

    private func startWatchdog() {
        watchdog?.cancel()
        watchdog = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(5))
                guard let self else { return }
                let stop = await self.watchdogTick()
                if stop { return }
            }
        }
    }

    /// One watchdog iteration (actor-isolated, so it may touch `task`). Returns
    /// `true` when it has forced a close and the watchdog should stop. Never
    /// captures the socket in a `Sendable` closure — all socket access is here.
    private func watchdogTick() async -> Bool {
        guard let socket = task else { return true }
        let staleSeconds = Double(staleTimeout.components.seconds)
        if Date().timeIntervalSince(lastInboundAt) > staleSeconds {
            // Two consecutive missed heartbeats (~30 s) → force reconnect.
            socket.cancel(with: .abnormalClosure, reason: nil)
            return true
        }
        // Keep-alive ping between heartbeats.
        await send(.ping(id: "c-\(Int(Date().timeIntervalSince1970))"))
        return false
    }

    // MARK: - Helpers

    private func streamURL() -> URL? {
        guard let baseURL, let token else { return nil }
        guard var components = URLComponents(url: baseURL.appendingPathComponent("/v3/stream"), resolvingAgainstBaseURL: false) else {
            return nil
        }
        components.queryItems = [
            URLQueryItem(name: "token", value: token),
            URLQueryItem(name: "pv", value: "1"),
        ]
        return components.url
    }

    static func baseURL(port: Int) -> URL {
        URL(string: "ws://127.0.0.1:\(port)")!
    }

    private func updateState(_ state: WSConnectionState) {
        guard state != currentState else { return }
        currentState = state
        for continuation in stateSubscribers.values {
            continuation.yield(state)
        }
    }
}
