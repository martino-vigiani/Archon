import Foundation

/// Centralised JSON coding for the Archon V3 wire protocol.
///
/// The contract (`API_CONTRACT_V3.md`) is entirely `snake_case` with RFC 3339
/// UTC millisecond timestamps. We convert snake_case ⇄ camelCase automatically
/// so Swift models can use idiomatic property names, and install a custom date
/// strategy that round-trips millisecond precision.
enum ArchonJSON {

    /// Parses/formats `2026-07-10T14:05:02.900Z` (fractional seconds), with a
    /// graceful fallback to whole-second RFC 3339.
    private static func makeRFC3339() -> (parse: (String) -> Date?, format: (Date) -> String) {
        let withFraction = ISO8601DateFormatter()
        withFraction.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let whole = ISO8601DateFormatter()
        whole.formatOptions = [.withInternetDateTime]
        return (
            parse: { string in
                withFraction.date(from: string) ?? whole.date(from: string)
            },
            format: { date in
                withFraction.string(from: date)
            }
        )
    }

    static func makeDecoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let rfc = makeRFC3339()
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let raw = try container.decode(String.self)
            guard let date = rfc.parse(raw) else {
                throw DecodingError.dataCorruptedError(
                    in: container,
                    debugDescription: "Invalid RFC 3339 timestamp: \(raw)"
                )
            }
            return date
        }
        return decoder
    }

    static func makeEncoder() -> JSONEncoder {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let rfc = makeRFC3339()
        encoder.dateEncodingStrategy = .custom { date, encoder in
            var container = encoder.singleValueContainer()
            try container.encode(rfc.format(date))
        }
        return encoder
    }

    static func decode<T: Decodable>(_ type: T.Type, from data: Data) throws -> T {
        try makeDecoder().decode(type, from: data)
    }

    static func encode<T: Encodable>(_ value: T) throws -> Data {
        try makeEncoder().encode(value)
    }
}
