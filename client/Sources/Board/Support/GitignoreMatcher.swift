import Foundation

/// A pragmatic `.gitignore` matcher for read-only tree *dimming* (REQ-UX-070,
/// §5 styling). This is intentionally NOT a full gitignore implementation — it
/// covers the common cases (comments, blanks, negation, anchored paths,
/// directory-only patterns, `*`/`?`/`**` globs) well enough to visually de-
/// emphasise ignored files. It never affects reads/writes (there are none in the
/// codebase view). Pure + deterministic so it is unit-tested.
struct GitignoreMatcher: Sendable {

    private struct Pattern: Sendable {
        let regex: String
        let negated: Bool
        let directoryOnly: Bool
        let anchored: Bool
    }

    private let patterns: [Pattern]

    /// Builds a matcher from raw `.gitignore` text.
    init(contents: String) {
        var parsed: [Pattern] = []
        for rawLine in contents.components(separatedBy: "\n") {
            var line = rawLine
            // Strip a trailing CR and unescaped trailing whitespace.
            if line.hasSuffix("\r") { line.removeLast() }
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            guard !trimmed.isEmpty, !trimmed.hasPrefix("#") else { continue }

            var body = trimmed
            let negated = body.hasPrefix("!")
            if negated { body.removeFirst() }

            let directoryOnly = body.hasSuffix("/")
            if directoryOnly { body.removeLast() }

            let anchored = body.hasPrefix("/") || body.contains("/")
            if body.hasPrefix("/") { body.removeFirst() }

            guard !body.isEmpty else { continue }
            parsed.append(Pattern(
                regex: Self.glob(body),
                negated: negated,
                directoryOnly: directoryOnly,
                anchored: anchored
            ))
        }
        self.patterns = parsed
    }

    /// Convenience: read `<dir>/.gitignore` if present.
    init(directory: URL) {
        let file = directory.appendingPathComponent(".gitignore")
        let contents = (try? String(contentsOf: file, encoding: .utf8)) ?? ""
        self.init(contents: contents)
    }

    var isEmpty: Bool { patterns.isEmpty }

    /// Whether `relativePath` (POSIX, relative to the gitignore's directory) is
    /// ignored. `.git` is always ignored. Later patterns win (last match), and a
    /// negation (`!`) can re-include.
    func isIgnored(relativePath: String, isDirectory: Bool) -> Bool {
        let path = relativePath.hasPrefix("/") ? String(relativePath.dropFirst()) : relativePath
        if path == ".git" || path.hasPrefix(".git/") { return true }

        let components = path.split(separator: "/").map(String.init)
        let basename = components.last ?? path

        var ignored = false
        for pattern in patterns {
            if pattern.directoryOnly && !isDirectory && !pathHasAncestorDir(path) { continue }
            let candidate: Bool
            if pattern.anchored {
                candidate = matches(pattern.regex, path)
            } else {
                // Unanchored: match against the basename OR any full path tail.
                candidate = matches(pattern.regex, basename) || matches(pattern.regex, path)
            }
            if candidate { ignored = !pattern.negated }
        }
        return ignored
    }

    private func pathHasAncestorDir(_ path: String) -> Bool {
        path.contains("/")
    }

    private func matches(_ pattern: String, _ value: String) -> Bool {
        value.range(of: pattern, options: .regularExpression) != nil
    }

    /// Translates a gitignore glob into an anchored regular expression.
    private static func glob(_ glob: String) -> String {
        var regex = "^"
        var index = glob.startIndex
        while index < glob.endIndex {
            let char = glob[index]
            switch char {
            case "*":
                let next = glob.index(after: index)
                if next < glob.endIndex && glob[next] == "*" {
                    // `**` matches across path separators.
                    regex += ".*"
                    index = glob.index(after: next)
                    continue
                } else {
                    regex += "[^/]*"
                }
            case "?":
                regex += "[^/]"
            case ".", "(", ")", "+", "|", "^", "$", "{", "}", "[", "]", "\\":
                regex += "\\\(char)"
            default:
                regex.append(char)
            }
            index = glob.index(after: index)
        }
        regex += "$"
        return regex
    }
}
