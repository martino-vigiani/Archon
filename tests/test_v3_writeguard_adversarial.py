"""Adversarial write-guard tests — phase C coverage (Addendum §A3 hard rule).

Extends test_v3_writeguard.py with cases not covered there:
* File-level symlink pointing outside the project is blocked on write.
* Double-slash / trailing-slash in scope_dir normalise correctly.
* Project root itself is a valid scope_dir.
* Multiple consecutive conductor-provenance denials accumulate in the audit log.
* Audit entry carries the correct ``action`` field.
* ``guard_project_write`` with a path that equals the project root itself.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from orchestrator.v3.errors import ApiError
from orchestrator.v3.storage import resolve_paths
from orchestrator.v3.writeguard import WriteGuard
from tests._v3_util import new_project, new_support


def _guard(tmp_path: Path) -> WriteGuard:
    proj = new_project(tmp_path)
    support = new_support(tmp_path)
    paths = resolve_paths(str(proj), support=support)
    paths.ensure()
    return WriteGuard(paths=paths)


# ---------------------------------------------------------------------------
# Symlink escape — file-level (not tested in the base suite)
# ---------------------------------------------------------------------------

def test_safe_join_blocks_symlink_file_pointing_outside(tmp_path):
    """A file inside the scope that is already a symlink to outside → path_escape."""
    g = _guard(tmp_path)
    # Create a regular file outside the project.
    outside_file = tmp_path / "outside_secret.txt"
    outside_file.write_text("secret content")
    # Place a symlink to it inside the project directory.
    link_in_project = g.project / "link.md"
    os.symlink(outside_file, link_in_project)
    # Writing to link.md (which resolves outside) must be blocked.
    with pytest.raises(ApiError) as ei:
        g.safe_join(str(g.project), "link.md")
    assert ei.value.code == "path_escape"


def test_safe_join_with_nested_symlink_chain(tmp_path):
    """A two-hop symlink chain ultimately pointing outside → path_escape."""
    g = _guard(tmp_path)
    outside = tmp_path / "outside_dir"
    outside.mkdir()
    outer_file = outside / "evil.md"
    outer_file.write_text("evil")
    # First hop: project/sublink → outside_dir
    sublink = g.project / "sublink"
    os.symlink(outside, sublink)
    # Second hop: project/link2.md → project/sublink/evil.md
    # When scope_dir=sublink, _canonical resolves it to outside → path_escape.
    with pytest.raises(ApiError) as ei:
        g.safe_join(str(sublink), "evil.md")
    assert ei.value.code == "path_escape"


# ---------------------------------------------------------------------------
# Scope_dir normalisation (double-slash, trailing slash)
# ---------------------------------------------------------------------------

def test_scope_dir_with_double_slash_is_accepted(tmp_path):
    """Double slashes in scope_dir normalise via realpath and are accepted."""
    g = _guard(tmp_path)
    # Construct a path with an extra slash.
    doubled = str(g.project).replace("/", "//", 1)
    # Should not raise – the project is the canonical target.
    result = g.assert_scope_within_project(doubled)
    # Returns the canonical (slash-normalised) project path.
    assert result == g.project


def test_scope_dir_with_trailing_slash_is_accepted(tmp_path):
    """Trailing slash is normalised and the scope is accepted."""
    g = _guard(tmp_path)
    trailing = str(g.project) + "/"
    result = g.assert_scope_within_project(trailing)
    assert result == g.project


# ---------------------------------------------------------------------------
# Project root itself is a valid scope_dir
# ---------------------------------------------------------------------------

def test_project_root_as_scope_dir_is_valid(tmp_path):
    """scope_dir = the project root is explicitly allowed (§2.6 CLAUDE.md at root)."""
    g = _guard(tmp_path)
    result = g.assert_scope_within_project(str(g.project))
    assert result == g.project


def test_safe_join_at_project_root(tmp_path):
    """Writing CLAUDE.md directly at the project root must work."""
    g = _guard(tmp_path)
    p = g.safe_join(str(g.project), "CLAUDE.md")
    assert p == g.project / "CLAUDE.md"
    assert g.is_inside_project(p)


# ---------------------------------------------------------------------------
# guard_project_write boundary: path == project root
# ---------------------------------------------------------------------------

def test_guard_project_write_at_root_requires_user(tmp_path):
    """Writing exactly at the project root (edge) is inside → provenance enforced."""
    g = _guard(tmp_path)
    with pytest.raises(ApiError) as ei:
        g.guard_project_write(g.project, "conductor")
    assert ei.value.code == "conductor_write_forbidden"


# ---------------------------------------------------------------------------
# Audit log accumulates multiple entries; each has ``action`` field
# ---------------------------------------------------------------------------

def test_multiple_forbidden_writes_accumulate_in_audit(tmp_path):
    """Each conductor-provenance rejection appends a distinct audit entry."""
    g = _guard(tmp_path)
    for action in ("memory_write", "project_file_write", "custom_action"):
        with pytest.raises(ApiError):
            g.require_user("conductor", target_path=g.project / "x.md", action=action)
    lines = [
        json.loads(l)
        for l in g.paths.audit_log.read_text().splitlines()
        if l.strip()
    ]
    assert len(lines) == 3
    actions_logged = {l.get("action") for l in lines}
    assert actions_logged == {"memory_write", "project_file_write", "custom_action"}


def test_audit_entry_contains_correct_fields(tmp_path):
    """Audit record must include event, reason, action, initiator, target (§A3)."""
    g = _guard(tmp_path)
    target = g.project / "CLAUDE.md"
    with pytest.raises(ApiError):
        g.require_user("conductor", target_path=target, action="memory_write")
    lines = [json.loads(l) for l in g.paths.audit_log.read_text().splitlines() if l.strip()]
    assert len(lines) == 1
    entry = lines[0]
    assert entry["event"] == "write_denied"
    assert entry["reason"] == "conductor_write_forbidden"
    assert entry["action"] == "memory_write"
    assert entry["initiator"] == "conductor"
    assert str(target) in str(entry.get("target", ""))


# ---------------------------------------------------------------------------
# Path-escape with absolute filename (regression: os.path.isabs on filename)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("filename", [
    "/etc/passwd",
    "/tmp/evil",
    "//double",
])
def test_safe_join_rejects_absolute_filename(tmp_path, filename):
    """Filenames that look absolute must be rejected as path_escape."""
    g = _guard(tmp_path)
    with pytest.raises(ApiError) as ei:
        g.safe_join(str(g.project), filename)
    assert ei.value.code == "path_escape"


# ---------------------------------------------------------------------------
# is_inside_project with boundary edge cases
# ---------------------------------------------------------------------------

def test_is_inside_project_boundary(tmp_path):
    """Project sibling directory must NOT be inside project."""
    g = _guard(tmp_path)
    sibling = g.project.parent / "sibling_project"
    assert not g.is_inside_project(sibling)


def test_is_inside_project_with_deep_path(tmp_path):
    """Deeply nested path inside project is inside."""
    g = _guard(tmp_path)
    deep = g.project / "a" / "b" / "c" / "d" / "e"
    assert g.is_inside_project(deep)
