import Foundation

/// Minimal ULID generator (Crockford base32, 26 chars, lexicographically
/// sortable). Used for client-generated `request_id`s for idempotency
/// (REQ-ARCH-021 / contract §1.5). Servers emit ULIDs too, but the client
/// treats *those* as opaque — this generator is only for our own request ids.
enum ULID {

    /// Crockford base32 alphabet (excludes I, L, O, U).
    private static let alphabet = Array("0123456789ABCDEFGHJKMNPQRSTVWXYZ")

    /// Generates a 26-character ULID: 48-bit millisecond timestamp + 80 bits of
    /// randomness, encoded big-endian.
    static func generate(date: Date = Date()) -> String {
        var bytes = [UInt8](repeating: 0, count: 16)

        let millis = UInt64((date.timeIntervalSince1970 * 1000).rounded(.down))
        // 48-bit timestamp, big-endian, into bytes 0..<6.
        bytes[0] = UInt8((millis >> 40) & 0xFF)
        bytes[1] = UInt8((millis >> 32) & 0xFF)
        bytes[2] = UInt8((millis >> 24) & 0xFF)
        bytes[3] = UInt8((millis >> 16) & 0xFF)
        bytes[4] = UInt8((millis >> 8) & 0xFF)
        bytes[5] = UInt8(millis & 0xFF)
        // 80 bits randomness into bytes 6..<16.
        for i in 6..<16 {
            bytes[i] = UInt8.random(in: 0...255)
        }

        return encodeBase32(bytes)
    }

    /// Encodes 16 bytes (128 bits) as 26 Crockford base32 characters.
    private static func encodeBase32(_ bytes: [UInt8]) -> String {
        precondition(bytes.count == 16)
        // Treat the 128 bits as a big integer and read 5 bits at a time from the
        // most-significant end. 128 bits → 26 symbols (the first symbol carries
        // only the top 2 bits, so it is always in 0...7).
        var output = [Character]()
        output.reserveCapacity(26)
        var bitBuffer: UInt32 = 0
        var bitCount: Int = 0
        var symbolsRemaining = 26
        // Prime with 2 leading zero bits so the total bit length is 130 (= 26*5).
        bitBuffer = 0
        bitCount = 2

        var index = 0
        while symbolsRemaining > 0 {
            while bitCount < 5 && index < bytes.count {
                bitBuffer = (bitBuffer << 8) | UInt32(bytes[index])
                bitCount += 8
                index += 1
            }
            if bitCount < 5 {
                bitBuffer <<= UInt32(5 - bitCount)
                bitCount = 5
            }
            let shift = UInt32(bitCount - 5)
            let value = (bitBuffer >> shift) & 0x1F
            output.append(alphabet[Int(value)])
            bitCount -= 5
            symbolsRemaining -= 1
        }
        return String(output)
    }
}
