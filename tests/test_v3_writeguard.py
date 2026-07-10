"""Exhaustive tests for the zero-footprint write-guard (Addendum §A3).

The guard is THE hard rule: only ``initiator == user`` may write inside the
project, and every path must resolve strictly inside the project tree.
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


# -- provenance ------------------------------------------------------------
def test_user_initiator_is_allowed(tmp_path):
    g = _guard(tmp_path)
    # No exception for a user write inside the project.
    g.require_user("user", target_path=g.project / "CLAUDE.md")


@pytest.mark.parametrize("initiator", ["conductor", "agent", "", "system", "User", "USER"])
def test_non_user_initiator_is_forbidden(tmp_path, initiator):
    g = _guard(tmp_path)
    with pytest.raises(ApiError) as ei:
        g.require_user(initiator, target_path=g.project / "CLAUDE.md")
    assert ei.value.code == "conductor_write_forbidden"
    assert ei.value.status == 403


def test_forbidden_write_is_audited(tmp_path):
    g = _guard(tmp_path)
    with pytest.raises(ApiError):
        g.require_user("conductor", target_path=g.project / "CLAUDE.md", action="memory_write")
    audit = g.paths.audit_log
    assert audit.is_file()
    lines = [json.loads(x) for x in audit.read_text().splitlines() if x.strip()]
    assert any(
        e.get("event") == "write_denied" and e.get("initiator") == "conductor" for e in lines
    )
    # Audit log itself must be owner-only.
    assert (os.stat(audit).st_mode & 0o077) == 0


def test_guard_project_write_gates_only_inside_project(tmp_path):
    g = _guard(tmp_path)
    # A conductor write inside the project is blocked...
    with pytest.raises(ApiError):
        g.guard_project_write(g.project / "x.md", "conductor")
    # ...but a conductor write to the out-of-tree overlay is not blocked here.
    outside = g.paths.memory_overlay_dir / "notes.md"
    g.guard_project_write(outside, "conductor")  # no raise


# -- containment -----------------------------------------------------------
def test_is_inside_project(tmp_path):
    g = _guard(tmp_path)
    assert g.is_inside_project(g.project)
    assert g.is_inside_project(g.project / "a" / "b")
    assert not g.is_inside_project(g.project.parent)
    assert not g.is_inside_project("/etc/passwd")


def test_assert_scope_within_project_rejects_escape(tmp_path):
    g = _guard(tmp_path)
    with pytest.raises(ApiError) as ei:
        g.assert_scope_within_project(str(g.project.parent))
    assert ei.value.code == "path_escape"


@pytest.mark.parametrize(
    "filename",
    ["../evil", "../../etc/passwd", "a/b", "a\\b", "/abs/path", ".", "..", "", "with\x00null"],
)
def test_safe_join_rejects_bad_filenames(tmp_path, filename):
    g = _guard(tmp_path)
    with pytest.raises(ApiError) as ei:
        g.safe_join(str(g.project), filename)
    assert ei.value.code == "path_escape"


def test_safe_join_accepts_bare_name(tmp_path):
    g = _guard(tmp_path)
    p = g.safe_join(str(g.project), "CLAUDE.md")
    assert p == g.project / "CLAUDE.md"


def test_safe_join_blocks_symlink_escape(tmp_path):
    g = _guard(tmp_path)
    # A subdir that is actually a symlink pointing outside the project.
    outside = tmp_path / "outside"
    outside.mkdir()
    link = g.project / "sneaky"
    os.symlink(outside, link)
    # scope_dir resolves (via realpath) outside the project → path_escape.
    with pytest.raises(ApiError) as ei:
        g.safe_join(str(link), "passwd")
    assert ei.value.code == "path_escape"


def test_safe_join_nested_scope_ok(tmp_path):
    g = _guard(tmp_path)
    sub = g.project / "pkg" / "api"
    sub.mkdir(parents=True)
    p = g.safe_join(str(sub), "AGENTS.md")
    assert p == sub / "AGENTS.md"
    assert g.is_inside_project(p)
