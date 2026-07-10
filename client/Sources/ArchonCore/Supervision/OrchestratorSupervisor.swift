import Foundation

/// How to launch the local Python orchestrator (client-supervised, Q8).
///
/// The client NEVER holds the provider API key — it only launches the process,
/// reads the `0600` token file, health-checks, and restarts. The key stays
/// server-side (REQ-VIS-002 / REQ-ARCH-040).
struct OrchestratorLaunchConfig: Sendable, Equatable {
    /// Python interpreter that runs `-m orchestrator.v3`.
    var pythonURL: URL
    /// Working directory so `python -m orchestrator` resolves the package.
    var workingDirectory: URL
    /// Extra arguments appended after `-m orchestrator --project <path>`.
    var extraArguments: [String]

    /// Resolves the interpreter + repo without shipping a developer's absolute
    /// paths in the binary. Resolution order (first hit wins):
    ///   1. Env override: `ARCHON_REPO` (and optional `ARCHON_PYTHON`) — CI,
    ///      packaging, and power users. This is also what makes a non-loopback
    ///      install work on any machine.
    ///   2. Bundled runtime shipped inside the app
    ///      (`Resources/orchestrator-runtime/.venv/bin/python`).
    ///   3. Auto-discovery: walk up from the running binary looking for a repo
    ///      root that has both `.venv/bin/python` and `orchestrator/v3` (covers
    ///      in-tree `swift`/xcode dev builds).
    ///   4. A last-resort dev fallback (the historical hardcode), used ONLY when
    ///      nothing above resolves — keeps this developer's machine working.
    static let `default` = resolve()

    static func resolve(
        environment: [String: String] = ProcessInfo.processInfo.environment,
        bundle: Bundle = .main,
        fileManager: FileManager = .default
    ) -> OrchestratorLaunchConfig {
        func makeConfig(repo: URL, python: URL? = nil) -> OrchestratorLaunchConfig {
            OrchestratorLaunchConfig(
                pythonURL: python ?? repo.appendingPathComponent(".venv/bin/python"),
                workingDirectory: repo,
                extraArguments: []
            )
        }
        func hasRepoLayout(_ dir: URL) -> Bool {
            fileManager.isExecutableFile(atPath: dir.appendingPathComponent(".venv/bin/python").path)
                && fileManager.fileExists(atPath: dir.appendingPathComponent("orchestrator/v3").path)
        }

        // 1. Explicit environment override.
        if let repoPath = environment["ARCHON_REPO"], !repoPath.isEmpty {
            let repo = URL(fileURLWithPath: repoPath)
            let python = environment["ARCHON_PYTHON"].flatMap { $0.isEmpty ? nil : URL(fileURLWithPath: $0) }
            return makeConfig(repo: repo, python: python)
        }
        if let pythonPath = environment["ARCHON_PYTHON"], !pythonPath.isEmpty {
            // Interpreter given without a repo: assume `<repo>/.venv/bin/python`.
            let python = URL(fileURLWithPath: pythonPath)
            let repo = python.deletingLastPathComponent()   // bin
                .deletingLastPathComponent()                // .venv
                .deletingLastPathComponent()                // repo
            return makeConfig(repo: repo, python: python)
        }

        // 2. Bundled runtime shipped with the app.
        if let resources = bundle.resourceURL {
            let bundledRepo = resources.appendingPathComponent("orchestrator-runtime")
            if hasRepoLayout(bundledRepo) {
                return makeConfig(repo: bundledRepo)
            }
        }

        // 3. Auto-discover an in-tree repo root above the running binary.
        var dir = bundle.bundleURL.resolvingSymlinksInPath()
        for _ in 0..<12 {
            if hasRepoLayout(dir) {
                return makeConfig(repo: dir)
            }
            let parent = dir.deletingLastPathComponent()
            if parent == dir { break }
            dir = parent
        }

        // 4. Last-resort dev fallback (historical hardcode).
        let devRepo = URL(fileURLWithPath: "/Users/martinovigiani/lab/Archon")
        return makeConfig(repo: devRepo)
    }

    /// The full argument vector. Integration seam: the V3 serve entry point is
    /// `python -m orchestrator.v3` (see `orchestrator/v3/__main__.py` and
    /// `create_v3_app` in `app.py`) — NOT the legacy `python -m orchestrator`,
    /// which is the organic multi-agent CLI and requires a task goal. The bound
    /// project dir is passed via `--project`; the port is left ephemeral (the
    /// backend picks one and writes it into `runtime.json`, contract §1.2).
    func arguments(projectPath: String) -> [String] {
        ["-m", "orchestrator.v3", "--project", projectPath] + extraArguments
    }
}

/// Observable supervisor lifecycle.
enum SupervisorState: Sendable, Equatable {
    case idle
    case launching
    case waitingForHandshake
    case healthChecking
    case ready(RuntimeHandshake)
    case restarting(attempt: Int)
    case incompatible
    case failed(reason: String)
    case stopped
}

/// Launches and supervises the local orchestrator process (Addendum §A4):
/// auto-restart on death (max 3 attempts, exponential backoff), health-check
/// `/v3/health`, read the `0600` handshake for port + token.
actor OrchestratorSupervisor {

    private let config: OrchestratorLaunchConfig
    private let store: ProjectStore
    private let backoff: BackoffPolicy
    private let maxRestarts: Int
    private let handshakeTimeout: Duration

    private var projectURL: URL?
    private var process: Process?
    private var restartAttempt = 0
    private var isActive = false
    private var superviseTask: Task<Void, Never>?

    private var stateSubscribers: [UUID: AsyncStream<SupervisorState>.Continuation] = [:]
    private var currentState: SupervisorState = .idle

    init(
        config: OrchestratorLaunchConfig = .default,
        store: ProjectStore = ProjectStore(),
        backoff: BackoffPolicy = .restart,
        maxRestarts: Int = 3,
        handshakeTimeout: Duration = .seconds(20)
    ) {
        self.config = config
        self.store = store
        self.backoff = backoff
        self.maxRestarts = maxRestarts
        self.handshakeTimeout = handshakeTimeout
    }

    // MARK: - State stream

    func stateStream() -> AsyncStream<SupervisorState> {
        let (stream, continuation) = AsyncStream.makeStream(of: SupervisorState.self)
        let id = UUID()
        stateSubscribers[id] = continuation
        continuation.yield(currentState)
        continuation.onTermination = { [weak self] _ in
            Task { await self?.removeStateSubscriber(id) }
        }
        return stream
    }

    private func removeStateSubscriber(_ id: UUID) {
        stateSubscribers[id] = nil
    }

    var state: SupervisorState { currentState }

    // MARK: - Lifecycle

    /// Begins supervising the orchestrator for `projectURL`. Returns the
    /// handshake once the orchestrator is healthy, or throws.
    @discardableResult
    func start(projectURL: URL) async throws -> RuntimeHandshake {
        self.projectURL = projectURL
        isActive = true
        restartAttempt = 0
        try store.ensureStateDirectory(forProjectAt: projectURL)
        store.clearStaleHandshake(forProjectAt: projectURL)
        return try await launchAndConnect()
    }

    func stop() {
        isActive = false
        superviseTask?.cancel()
        superviseTask = nil
        if let process, process.isRunning {
            process.terminate()
        }
        process = nil
        updateState(.stopped)
    }

    // MARK: - One launch cycle

    private func launchAndConnect() async throws -> RuntimeHandshake {
        guard let projectURL else {
            throw ArchonClientError.orchestratorUnavailable
        }
        updateState(.launching)

        let projectPath = ProjectIdentity.canonicalPath(for: projectURL)
        let process = Process()
        process.executableURL = config.pythonURL
        process.arguments = config.arguments(projectPath: projectPath)
        process.currentDirectoryURL = config.workingDirectory

        var env = ProcessInfo.processInfo.environment
        env["ARCHON_V3"] = "1"
        env["ARCHON_PROJECT_DIR"] = projectPath
        env["ARCHON_STATE_DIR"] = store.stateDirectory(forProjectAt: projectURL).path
        env["PYTHONUNBUFFERED"] = "1"
        process.environment = env

        process.terminationHandler = { [weak self] proc in
            let status = proc.terminationStatus
            Task { await self?.handleProcessExit(status: status) }
        }

        do {
            try process.run()
        } catch {
            throw ArchonClientError.transport("Failed to launch orchestrator: \(error.localizedDescription)")
        }
        self.process = process

        // Wait for the handshake file (contract §1.2).
        updateState(.waitingForHandshake)
        let handshake = try await waitForHandshake(projectURL: projectURL)

        guard handshake.pv == 1 else {
            updateState(.incompatible)
            throw ArchonClientError.incompatibleVersion
        }

        // Health-check /v3/health (contract §2.1).
        updateState(.healthChecking)
        try await healthCheck(handshake: handshake)

        restartAttempt = 0
        updateState(.ready(handshake))
        return handshake
    }

    private func waitForHandshake(projectURL: URL) async throws -> RuntimeHandshake {
        let deadline = Date().addingTimeInterval(Double(handshakeTimeout.components.seconds))
        while Date() < deadline {
            if !isActive { throw ArchonClientError.orchestratorUnavailable }
            if let handshake = store.readRuntimeHandshake(forProjectAt: projectURL) {
                return handshake
            }
            try? await Task.sleep(for: .milliseconds(150))
        }
        throw ArchonClientError.transport("Orchestrator handshake timed out")
    }

    private func healthCheck(handshake: RuntimeHandshake) async throws {
        let client = APIClient(
            baseURL: APIClient.baseURL(port: handshake.port),
            token: handshake.token
        )
        // `status: starting` is tolerated for a few attempts.
        var attempt = 0
        while attempt < 10 {
            if !isActive { throw ArchonClientError.orchestratorUnavailable }
            do {
                let health = try await client.health()
                guard health.pv == 1 else {
                    throw ArchonClientError.incompatibleVersion
                }
                if health.status == .ok || health.status == .degraded {
                    return
                }
            } catch ArchonClientError.incompatibleVersion {
                throw ArchonClientError.incompatibleVersion
            } catch {
                // transient; keep polling
            }
            attempt += 1
            try? await Task.sleep(for: .milliseconds(300))
        }
        throw ArchonClientError.transport("Orchestrator did not become healthy")
    }

    // MARK: - Restart on death (Addendum §A4)

    private func handleProcessExit(status: Int32) async {
        guard isActive else { return }   // intentional stop
        process = nil

        restartAttempt += 1
        guard restartAttempt <= maxRestarts else {
            updateState(.failed(reason: "Orchestrator exited (status \(status)); exceeded \(maxRestarts) restart attempts"))
            isActive = false
            return
        }

        updateState(.restarting(attempt: restartAttempt))
        let attempt = restartAttempt
        superviseTask?.cancel()
        superviseTask = Task { [weak self] in
            guard let self else { return }
            let delay = await self.backoffDuration(forAttempt: attempt)
            try? await Task.sleep(for: delay)
            guard await self.stillActive() else { return }
            do {
                _ = try await self.launchAndConnect()
            } catch {
                await self.recordFailure(error)
            }
        }
    }

    private func backoffDuration(forAttempt attempt: Int) -> Duration {
        backoff.duration(forAttempt: attempt)
    }

    private func stillActive() -> Bool { isActive }

    private func recordFailure(_ error: Error) {
        if case ArchonClientError.incompatibleVersion = error {
            updateState(.incompatible)
        } else {
            updateState(.failed(reason: error.localizedDescription))
        }
    }

    private func updateState(_ state: SupervisorState) {
        guard state != currentState else { return }
        currentState = state
        for continuation in stateSubscribers.values {
            continuation.yield(state)
        }
    }
}
