import Foundation
import CryptoKit

/// Computes the canonical project identity shared with the orchestrator.
///
/// Contract §0: `project_id = sha256_hex(canonical_project_path)` — lowercase
/// 64-hex, deterministic. Both sides MUST compute it identically from the
/// absolute, symlink-resolved project path. The orchestrator uses Python's
/// `os.path.realpath`, which resolves the macOS firmlink aliases FORWARD
/// (`/tmp` → `/private/tmp`, `/var` → `/private/var`, `/etc` → `/private/etc`).
///
/// Foundation's `URL.resolvingSymlinksInPath()` resolves them the OPPOSITE way
/// (`/private/tmp` → `/tmp`), so for any project under those roots the client and
/// orchestrator would derive DIFFERENT `project_id`s — the supervisor then polls
/// the wrong state dir and never finds `runtime.json` (handshake times out, the
/// client is stuck "reconnecting" against a healthy but undiscoverable
/// orchestrator). We therefore canonicalize with POSIX `realpath(3)`, which
/// matches `os.path.realpath` exactly.
enum ProjectIdentity {

    /// The canonical, absolute, symlink-resolved path string for `url`,
    /// byte-for-byte identical to the orchestrator's `os.path.realpath`.
    static func canonicalPath(for url: URL) -> String {
        let standardized = url.standardizedFileURL.path
        // `realpath(3)` resolves every symlink/firmlink against the real
        // filesystem — the same direction Python's `os.path.realpath` does.
        if let resolved = realpath(standardized, nil) {
            defer { free(resolved) }
            return String(cString: resolved)
        }
        // `realpath` only fails when the path does not exist yet; a selected
        // project directory always exists, so this is a defensive fallback.
        return url.standardizedFileURL.resolvingSymlinksInPath().path
    }

    /// The lowercase 64-hex SHA-256 of the canonical path (the `project_id`).
    static func projectID(for url: URL) -> String {
        sha256Hex(of: canonicalPath(for: url))
    }

    static func sha256Hex(of string: String) -> String {
        let digest = SHA256.hash(data: Data(string.utf8))
        return digest.map { String(format: "%02x", $0) }.joined()
    }
}
