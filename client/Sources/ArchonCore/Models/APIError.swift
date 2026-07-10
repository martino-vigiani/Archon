import Foundation

/// The stable error `code` registry (contract §1.6). Additive-tolerant: an
/// unrecognised code decodes to `.unknown` rather than failing.
enum APIErrorCode: String, Codable, Sendable, Equatable {
    case unauthorized
    case forbidden
    case incompatibleVersion = "incompatible_version"
    case notFound = "not_found"
    case validationError = "validation_error"
    case revisionConflict = "revision_conflict"
    case capExceeded = "cap_exceeded"
    case ceilingReached = "ceiling_reached"
    case illegalTransition = "illegal_transition"
    case memoryWriteDenied = "memory_write_denied"
    case conductorWriteForbidden = "conductor_write_forbidden"
    case memoryTooLarge = "memory_too_large"
    case memoryQuotaExceeded = "memory_quota_exceeded"
    case pathEscape = "path_escape"
    case planExpired = "plan_expired"
    case sessionNotFound = "session_not_found"
    case rateLimited = "rate_limited"
    case orchestratorError = "orchestrator_error"
    case providerError = "provider_error"
    case unknown

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = APIErrorCode(rawValue: raw) ?? .unknown
    }

    /// Whether the contract marks this code retriable (safe to auto-retry for
    /// idempotent calls).
    var isRetriable: Bool {
        switch self {
        case .rateLimited, .orchestratorError, .providerError:
            return true
        default:
            return false
        }
    }
}

/// The typed error payload carried by non-2xx REST responses and WS `error`
/// frames (contract §1.6). `details` is preserved as free-form JSON.
struct APIError: Codable, Sendable, Equatable {
    var code: APIErrorCode
    var message: String
    var retriable: Bool
    var details: JSONValue?
}

/// Wrapper matching the `{ "error": { ... } }` envelope.
struct APIErrorEnvelope: Codable, Sendable {
    var error: APIError
}

/// Errors surfaced by the client transport layer.
enum ArchonClientError: Error, Sendable, Equatable {
    /// A typed error returned by the orchestrator.
    case api(APIError, httpStatus: Int?)
    /// Protocol major mismatch — the orchestrator is incompatible (REQ-ARCH-004).
    case incompatibleVersion
    /// A transport/URL failure (no HTTP response, socket error, etc.).
    case transport(String)
    /// Response body could not be decoded into the expected shape.
    case decoding(String)
    /// The orchestrator is not reachable (offline / not yet supervised).
    case orchestratorUnavailable

    /// Whether it is safe to retry an *idempotent* request after this error.
    var isRetriable: Bool {
        switch self {
        case .api(let error, let status):
            if let status, status == 429 || status >= 500 { return true }
            return error.code.isRetriable
        case .transport, .orchestratorUnavailable:
            return true
        case .incompatibleVersion, .decoding:
            return false
        }
    }
}
