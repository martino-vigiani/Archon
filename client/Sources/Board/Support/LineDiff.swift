import Foundation

/// A minimal line-level diff (LCS-based) for the conductor memory-edit review
/// card. Pure and deterministic so it is unit-testable and renders a readable
/// added/removed/context sequence without color (§5.1-5.2).
enum LineDiff {

    struct Line: Sendable, Equatable, Identifiable {
        enum Kind: Sendable, Equatable { case context, added, removed }
        let id: Int
        let kind: Kind
        let text: String
    }

    /// Computes a diff between two strings split on newlines.
    static func diff(old oldText: String, new newText: String) -> [Line] {
        diff(oldLines: split(oldText), newLines: split(newText))
    }

    static func split(_ text: String) -> [String] {
        // Preserve empty trailing content sensibly: split keeping interior blanks.
        text.components(separatedBy: "\n")
    }

    static func diff(oldLines: [String], newLines: [String]) -> [Line] {
        let table = lcsTable(oldLines, newLines)
        var result: [Line] = []
        var i = oldLines.count
        var j = newLines.count

        // Walk back through the LCS table to produce an ordered edit script.
        var reversed: [(Line.Kind, String)] = []
        while i > 0 && j > 0 {
            if oldLines[i - 1] == newLines[j - 1] {
                reversed.append((.context, oldLines[i - 1]))
                i -= 1; j -= 1
            } else if table[i - 1][j] >= table[i][j - 1] {
                reversed.append((.removed, oldLines[i - 1]))
                i -= 1
            } else {
                reversed.append((.added, newLines[j - 1]))
                j -= 1
            }
        }
        while i > 0 { reversed.append((.removed, oldLines[i - 1])); i -= 1 }
        while j > 0 { reversed.append((.added, newLines[j - 1])); j -= 1 }

        for (index, entry) in reversed.reversed().enumerated() {
            result.append(Line(id: index, kind: entry.0, text: entry.1))
        }
        return result
    }

    /// Standard forward (prefix) LCS table: `table[i][j]` = LCS length of the
    /// first `i` lines of `a` and first `j` lines of `b`.
    private static func lcsTable(_ a: [String], _ b: [String]) -> [[Int]] {
        var table = Array(repeating: Array(repeating: 0, count: b.count + 1), count: a.count + 1)
        guard !a.isEmpty && !b.isEmpty else { return table }
        for i in 1...a.count {
            for j in 1...b.count {
                if a[i - 1] == b[j - 1] {
                    table[i][j] = table[i - 1][j - 1] + 1
                } else {
                    table[i][j] = max(table[i - 1][j], table[i][j - 1])
                }
            }
        }
        return table
    }

    /// Summary counts for a compact header ("+N / −M").
    static func counts(_ lines: [Line]) -> (added: Int, removed: Int) {
        var added = 0, removed = 0
        for line in lines {
            switch line.kind {
            case .added: added += 1
            case .removed: removed += 1
            case .context: break
            }
        }
        return (added, removed)
    }
}
