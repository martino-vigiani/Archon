import Foundation
import CryptoKit

/// Computes the canonical project identity shared with the orchestrator.
///
/// Contract §0: `project_id = sha256_hex(canonical_project_path)` — lowercase
/// 64-hex, deterministic. Both sides compute it identically from the absolute,
/// symlink-resolved project path. On macOS this must match Python's
/// `os.path.realpath` semantics (which also resolves `/tmp` → `/private/tmp`,
/// `/var` → `/private/var`); `URL.resolvingSymlinksInPath()` does the same.
enum ProjectIdentity {

    /// The canonical, absolute, symlink-resolved path string for `url`.
    static func canonicalPath(for url: URL) -> String {
        url.standardizedFileURL
            .resolvingSymlinksInPath()
            .path
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
