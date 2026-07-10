import Foundation

/// `GET /v3/health` response (contract §2.1). No side effects; used for
/// supervision/health-checks and protocol negotiation.
struct HealthResponse: Codable, Sendable, Equatable {
    var status: HealthStatus
    var pv: Int
    var orchestratorVersion: String
    var projectId: String
    var uptimeS: Double
    var providerReady: Bool
    var conductorState: ConductorState
    var sessionCount: Int
    var capabilities: Capabilities
}

enum HealthStatus: String, Codable, Sendable {
    case ok
    case degraded
    case starting
    case unknown

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = HealthStatus(rawValue: raw) ?? .unknown
    }
}

/// Capabilities descriptor advertised in health + the WS `hello` frame
/// (contract §2.1 / §3.2). Additive-tolerant.
struct Capabilities: Codable, Sendable, Equatable {
    var streamTransport: String
    var replayEvents: Int
    var replayWindowS: Int
    var hardCeiling: Int
    var supportedProvider: String
    var memoryKinds: [String]
    var dryRunMaxS: Double
}
