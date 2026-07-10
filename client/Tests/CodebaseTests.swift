import Testing
import Foundation
@testable import Archon

@Suite("GitignoreMatcher — read-only tree dimming")
struct GitignoreMatcherTests {

    @Test("Extension globs match by basename anywhere in the tree")
    func extensionGlob() {
        let matcher = GitignoreMatcher(contents: "*.log\n")
        #expect(matcher.isIgnored(relativePath: "debug.log", isDirectory: false))
        #expect(matcher.isIgnored(relativePath: "src/nested/app.log", isDirectory: false))
        #expect(!matcher.isIgnored(relativePath: "notes.txt", isDirectory: false))
    }

    @Test("Directory-only patterns match the directory")
    func directoryOnly() {
        let matcher = GitignoreMatcher(contents: "build/\nnode_modules/\n")
        #expect(matcher.isIgnored(relativePath: "build", isDirectory: true))
        #expect(matcher.isIgnored(relativePath: "node_modules", isDirectory: true))
    }

    @Test("Anchored patterns only match at the root")
    func anchored() {
        let matcher = GitignoreMatcher(contents: "/dist\n")
        #expect(matcher.isIgnored(relativePath: "dist", isDirectory: true))
        #expect(!matcher.isIgnored(relativePath: "src/dist", isDirectory: true))
    }

    @Test("Negation re-includes a previously ignored path")
    func negation() {
        let matcher = GitignoreMatcher(contents: "*.log\n!keep.log\n")
        #expect(matcher.isIgnored(relativePath: "debug.log", isDirectory: false))
        #expect(!matcher.isIgnored(relativePath: "keep.log", isDirectory: false))
    }

    @Test(".git is always ignored; comments and blanks are skipped")
    func gitAlwaysIgnoredAndComments() {
        let matcher = GitignoreMatcher(contents: "# a comment\n\n   \n")
        #expect(matcher.isIgnored(relativePath: ".git", isDirectory: true))
        #expect(matcher.isIgnored(relativePath: ".git/config", isDirectory: false))
        #expect(!matcher.isIgnored(relativePath: "README.md", isDirectory: false))
    }

    @Test("Empty gitignore ignores nothing (except .git)")
    func emptyMatcher() {
        let matcher = GitignoreMatcher(contents: "")
        #expect(matcher.isEmpty)
        #expect(!matcher.isIgnored(relativePath: "anything.swift", isDirectory: false))
    }
}

@MainActor
@Suite("FileNode model")
struct FileNodeTests {

    @Test("A file node has stable path identity and no lazy children marker")
    func fileNode() {
        let url = URL(fileURLWithPath: "/a/b/main.swift")
        let node = FileNode(url: url, name: "main.swift", isDirectory: false, relativePath: "b/main.swift")
        #expect(node.id == "/a/b/main.swift")
        #expect(node.isDirectory == false)
        #expect(node.children?.isEmpty == true) // files carry an empty (loaded) list
        #expect(node.isExpanded == false)
    }

    @Test("A directory node starts unloaded (children == nil)")
    func directoryNode() {
        let url = URL(fileURLWithPath: "/a/pkg")
        let node = FileNode(url: url, name: "pkg", isDirectory: true, relativePath: "pkg", isGitignored: true)
        #expect(node.isDirectory)
        #expect(node.children == nil)          // not yet lazily loaded
        #expect(node.isGitignored)
    }
}

@Suite("LineDiff — memory proposal review")
struct LineDiffTests {

    @Test("Single line change yields one removed + one added")
    func singleChange() {
        let lines = LineDiff.diff(old: "line1\nline2", new: "line1\nline2x")
        let counts = LineDiff.counts(lines)
        #expect(counts.added == 1)
        #expect(counts.removed == 1)
        // The unchanged line is preserved as context.
        #expect(lines.contains { $0.kind == .context && $0.text == "line1" })
        #expect(lines.contains { $0.kind == .added && $0.text == "line2x" })
        #expect(lines.contains { $0.kind == .removed && $0.text == "line2" })
    }

    @Test("Pure addition produces only added lines")
    func pureAddition() {
        let lines = LineDiff.diff(old: "a", new: "a\nb\nc")
        let counts = LineDiff.counts(lines)
        #expect(counts.added == 2)
        #expect(counts.removed == 0)
    }

    @Test("Identical content is all context")
    func identical() {
        let lines = LineDiff.diff(old: "x\ny", new: "x\ny")
        let counts = LineDiff.counts(lines)
        #expect(counts.added == 0)
        #expect(counts.removed == 0)
        #expect(lines.allSatisfy { $0.kind == .context })
    }
}
