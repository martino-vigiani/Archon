import Foundation

/// Read-only filesystem access for the codebase tree. Direct FS reads are
/// explicitly allowed for the tree (never writes — addendum §A3). Enumeration
/// runs off the main actor and returns `Sendable` value DTOs.
enum FileTreeLoader {

    /// Lists the immediate children of `directory`, directories first then files,
    /// case-insensitive by name. Hidden files are included but the caller may dim
    /// them; `.git` internals are surfaced to the gitignore layer for dimming.
    static func loadChildren(of directory: URL) async -> [FileEntry] {
        await Task.detached(priority: .utility) {
            let keys: [URLResourceKey] = [.isDirectoryKey, .nameKey, .contentModificationDateKey]
            guard let items = try? FileManager.default.contentsOfDirectory(
                at: directory,
                includingPropertiesForKeys: keys,
                options: [.skipsSubdirectoryDescendants]
            ) else { return [] }

            let entries: [FileEntry] = items.map { url in
                let values = try? url.resourceValues(forKeys: Set(keys))
                let isDir = values?.isDirectory ?? false
                let name = values?.name ?? url.lastPathComponent
                return FileEntry(
                    url: url,
                    name: name,
                    isDirectory: isDir,
                    modifiedAt: values?.contentModificationDate
                )
            }

            return entries.sorted { lhs, rhs in
                if lhs.isDirectory != rhs.isDirectory { return lhs.isDirectory && !rhs.isDirectory }
                return lhs.name.localizedCaseInsensitiveCompare(rhs.name) == .orderedAscending
            }
        }.value
    }

    /// Reads a file for the read-only preview, bounded so a huge file can't stall
    /// the UI. Returns `nil` for binary/undecodable content.
    static func readPreview(_ url: URL, maxBytes: Int = 512 * 1024) async -> FilePreview {
        await Task.detached(priority: .utility) {
            guard let handle = try? FileHandle(forReadingFrom: url) else {
                return FilePreview(text: nil, truncated: false, isBinary: false, byteCount: 0)
            }
            defer { try? handle.close() }
            let data = (try? handle.read(upToCount: maxBytes)) ?? Data()
            let attributes = try? FileManager.default.attributesOfItem(atPath: url.path)
            let total = (attributes?[.size] as? Int) ?? data.count
            let truncated = total > maxBytes
            // Reject content with NUL bytes as binary.
            if data.contains(0) {
                return FilePreview(text: nil, truncated: truncated, isBinary: true, byteCount: total)
            }
            let text = String(data: data, encoding: .utf8) ?? String(decoding: data, as: UTF8.self)
            return FilePreview(text: text, truncated: truncated, isBinary: false, byteCount: total)
        }.value
    }
}

struct FilePreview: Sendable, Equatable {
    let text: String?
    let truncated: Bool
    let isBinary: Bool
    let byteCount: Int
}
