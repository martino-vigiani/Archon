import Foundation

/// Async REST control-plane client (contract §2). Loopback only; every request
/// carries the bearer token and `Archon-Protocol-Version` header. Idempotent
/// calls (GETs and `request_id`-keyed POSTs) retry with backoff on retriable
/// errors (Addendum §A4); non-idempotent mutations do not auto-retry.
///
/// `APIClient` is an immutable `Sendable` value: on token rotation or reconnect
/// the container creates a new instance.
struct APIClient: Sendable {
    let baseURL: URL
    let token: String
    let protocolVersion: Int
    let retryPolicy: BackoffPolicy
    let maxRetries: Int

    init(
        baseURL: URL,
        token: String,
        protocolVersion: Int = 1,
        retryPolicy: BackoffPolicy = .apiRetry,
        maxRetries: Int = 3
    ) {
        self.baseURL = baseURL
        self.token = token
        self.protocolVersion = protocolVersion
        self.retryPolicy = retryPolicy
        self.maxRetries = maxRetries
    }

    /// Builds `http://127.0.0.1:<port>` from a runtime handshake.
    static func baseURL(port: Int) -> URL {
        URL(string: "http://127.0.0.1:\(port)")!
    }

    private enum Method: String {
        case get = "GET"
        case post = "POST"
        case patch = "PATCH"
        case put = "PUT"
        case delete = "DELETE"
    }

    // MARK: - Health / project

    func health() async throws -> HealthResponse {
        try await send(.get, "/v3/health", idempotent: true)
    }

    func project() async throws -> ProjectInfo {
        try await send(.get, "/v3/project", idempotent: true)
    }

    // MARK: - Sessions

    func listSessions() async throws -> SessionsListResponse {
        try await send(.get, "/v3/sessions", idempotent: true)
    }

    func spawnSession(_ request: SpawnSessionRequest) async throws -> SpawnSessionResponse {
        // Idempotent via `request_id` (contract §1.5) → safe to retry.
        try await send(.post, "/v3/sessions", body: request, idempotent: true)
    }

    func sessionDetail(_ sessionId: String) async throws -> SessionDetailResponse {
        try await send(.get, "/v3/sessions/\(sessionId)", idempotent: true)
    }

    func killSession(_ sessionId: String, request: KillSessionRequest = .init()) async throws -> KillSessionResponse {
        // Kill is idempotent (REQ-ARCH-023).
        try await send(.post, "/v3/sessions/\(sessionId)/kill", body: request, idempotent: true)
    }

    func flagIdle(_ sessionId: String, request: FlagIdleRequest = .init()) async throws -> FlagIdleResponse {
        try await send(.post, "/v3/sessions/\(sessionId)/flag-idle", body: request, idempotent: true)
    }

    // MARK: - Conductor

    func conductorMessage(_ request: ConductorMessageRequest) async throws -> ConductorMessageResponse {
        try await send(.post, "/v3/conductor/message", body: request, idempotent: true)
    }

    func confirmPlan(_ planId: String, request: ConfirmPlanRequest = .init()) async throws -> ConfirmPlanResponse {
        try await send(.post, "/v3/conductor/plans/\(planId)/confirm", body: request, idempotent: true)
    }

    func cancelPlan(_ planId: String) async throws -> CancelPlanResponse {
        try await send(.post, "/v3/conductor/plans/\(planId)/cancel", body: EmptyBody(), idempotent: true)
    }

    // MARK: - Kanban

    func kanbanSnapshot() async throws -> KanbanSnapshotResponse {
        try await send(.get, "/v3/kanban", idempotent: true)
    }

    func createCard(_ request: CreateCardRequest) async throws -> CardResponse {
        try await send(.post, "/v3/kanban/cards", body: request, idempotent: true)
    }

    func readCard(_ cardId: String) async throws -> CardResponse {
        try await send(.get, "/v3/kanban/cards/\(cardId)", idempotent: true)
    }

    func patchCard(_ cardId: String, request: PatchCardRequest) async throws -> CardResponse {
        // Optimistic-concurrency mutation; do NOT auto-retry.
        try await send(.patch, "/v3/kanban/cards/\(cardId)", body: request, idempotent: false)
    }

    func moveCard(_ cardId: String, request: MoveCardRequest) async throws -> MoveCardResponse {
        try await send(.post, "/v3/kanban/cards/\(cardId)/move", body: request, idempotent: false)
    }

    func deleteCard(_ cardId: String, request: DeleteCardRequest) async throws -> DeleteCardResponse {
        try await send(.delete, "/v3/kanban/cards/\(cardId)", body: request, idempotent: false)
    }

    // MARK: - Memory

    func listMemory(scopeDir: String? = nil) async throws -> MemoryListResponse {
        var query: [URLQueryItem] = []
        if let scopeDir { query.append(URLQueryItem(name: "scope_dir", value: scopeDir)) }
        return try await send(.get, "/v3/memory", query: query, idempotent: true)
    }

    func readMemory(scopeDir: String, filename: String) async throws -> MemoryReadResponse {
        let query = [
            URLQueryItem(name: "scope_dir", value: scopeDir),
            URLQueryItem(name: "filename", value: filename),
        ]
        return try await send(.get, "/v3/memory/file", query: query, idempotent: true)
    }

    func writeMemory(_ request: MemoryWriteRequest) async throws -> MemoryWriteResponse {
        // Optimistic-concurrency write; do NOT auto-retry.
        try await send(.put, "/v3/memory/file", body: request, idempotent: false)
    }

    func deleteMemory(scopeDir: String, filename: String, request: MemoryDeleteRequest) async throws -> MemoryDeleteResponse {
        let query = [
            URLQueryItem(name: "scope_dir", value: scopeDir),
            URLQueryItem(name: "filename", value: filename),
        ]
        return try await send(.delete, "/v3/memory/file", query: query, body: request, idempotent: false)
    }

    // MARK: - Event replay

    func events(afterSeq: Int64, limit: Int = 500) async throws -> EventReplayResponse {
        let query = [
            URLQueryItem(name: "after_seq", value: String(afterSeq)),
            URLQueryItem(name: "limit", value: String(limit)),
        ]
        return try await send(.get, "/v3/events", query: query, idempotent: true)
    }

    // MARK: - Core request pipeline

    private func send<Response: Decodable>(
        _ method: Method,
        _ path: String,
        query: [URLQueryItem] = [],
        idempotent: Bool
    ) async throws -> Response {
        let data = try await perform(method, path, query: query, bodyData: nil, idempotent: idempotent)
        return try decode(Response.self, from: data)
    }

    private func send<Body: Encodable, Response: Decodable>(
        _ method: Method,
        _ path: String,
        query: [URLQueryItem] = [],
        body: Body,
        idempotent: Bool
    ) async throws -> Response {
        let bodyData = try ArchonJSON.encode(body)
        let data = try await perform(method, path, query: query, bodyData: bodyData, idempotent: idempotent)
        return try decode(Response.self, from: data)
    }

    private func decode<T: Decodable>(_ type: T.Type, from data: Data) throws -> T {
        do {
            return try ArchonJSON.decode(T.self, from: data)
        } catch {
            throw ArchonClientError.decoding("\(T.self): \(error)")
        }
    }

    private func perform(
        _ method: Method,
        _ path: String,
        query: [URLQueryItem],
        bodyData: Data?,
        idempotent: Bool
    ) async throws -> Data {
        var attempt = 0
        while true {
            do {
                return try await performOnce(method, path, query: query, bodyData: bodyData)
            } catch let error as ArchonClientError {
                let canRetry = idempotent && error.isRetriable && attempt < maxRetries
                guard canRetry else { throw error }
                let delay = retryPolicy.duration(forAttempt: attempt)
                try await Task.sleep(for: delay)
                attempt += 1
            }
        }
    }

    private func performOnce(
        _ method: Method,
        _ path: String,
        query: [URLQueryItem],
        bodyData: Data?
    ) async throws -> Data {
        guard var components = URLComponents(url: baseURL.appendingPathComponent(path), resolvingAgainstBaseURL: false) else {
            throw ArchonClientError.transport("Invalid URL for \(path)")
        }
        if !query.isEmpty { components.queryItems = query }
        guard let url = components.url else {
            throw ArchonClientError.transport("Invalid URL components for \(path)")
        }

        var request = URLRequest(url: url)
        request.httpMethod = method.rawValue
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue(String(protocolVersion), forHTTPHeaderField: "Archon-Protocol-Version")
        request.setValue("application/json; charset=utf-8", forHTTPHeaderField: "Accept")
        if let bodyData {
            request.httpBody = bodyData
            request.setValue("application/json; charset=utf-8", forHTTPHeaderField: "Content-Type")
        }
        request.timeoutInterval = 10   // bounded control-command timeout (REQ-ARCH-084)

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await URLSession.shared.data(for: request)
        } catch let urlError as URLError {
            switch urlError.code {
            case .cannotConnectToHost, .cannotFindHost, .networkConnectionLost, .notConnectedToInternet:
                throw ArchonClientError.orchestratorUnavailable
            case .timedOut:
                throw ArchonClientError.transport("Request timed out")
            default:
                throw ArchonClientError.transport(urlError.localizedDescription)
            }
        }

        guard let http = response as? HTTPURLResponse else {
            throw ArchonClientError.transport("Non-HTTP response")
        }

        switch http.statusCode {
        case 200...299:
            return data
        default:
            // Attempt to decode the typed error envelope (contract §1.6).
            if let envelope = try? ArchonJSON.decode(APIErrorEnvelope.self, from: data) {
                if envelope.error.code == .incompatibleVersion {
                    throw ArchonClientError.incompatibleVersion
                }
                throw ArchonClientError.api(envelope.error, httpStatus: http.statusCode)
            }
            if http.statusCode == 409 {
                throw ArchonClientError.incompatibleVersion
            }
            let fallback = APIError(
                code: .orchestratorError,
                message: "HTTP \(http.statusCode)",
                retriable: http.statusCode >= 500,
                details: nil
            )
            throw ArchonClientError.api(fallback, httpStatus: http.statusCode)
        }
    }
}

/// Empty JSON body for POSTs that take no parameters.
private struct EmptyBody: Encodable {}
