"""Memory service tests: discovery, read/write/delete, guards, quotas, events."""

from __future__ import annotations

import pytest

from orchestrator.v3.errors import ApiError
from orchestrator.v3.memory import MAX_FILE_BYTES, MemoryService
from tests._v3_util import bare_services


def _seed(project, rel, name, content="# hi\n"):
    d = project / rel if rel else project
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(content)
    return d


async def test_list_discovers_claude_and_agents(tmp_path):
    svc = bare_services(tmp_path)
    m: MemoryService = svc["memory"]
    proj = svc["project"]
    _seed(proj, "", "CLAUDE.md")
    _seed(proj, "pkg", "AGENTS.md")
    listing = m.list_files()
    files = [(s["scope_dir"], f["filename"], f["kind"], f["location"]) for s in listing["scopes"] for f in s["files"]]
    assert any(f[1] == "CLAUDE.md" and f[3] == "project" for f in files)
    assert any(f[1] == "AGENTS.md" for f in files)


async def test_read_returns_content_and_meta(tmp_path):
    svc = bare_services(tmp_path)
    m, proj = svc["memory"], svc["project"]
    _seed(proj, "", "CLAUDE.md", "# guidance\n")
    r = m.read_file(str(proj), "CLAUDE.md")
    assert r["content"] == "# guidance\n"
    assert r["file"]["checksum"].startswith("sha256:")
    assert r["file"]["editable"] is True


async def test_read_missing_is_not_found(tmp_path):
    svc = bare_services(tmp_path)
    with pytest.raises(ApiError) as ei:
        svc["memory"].read_file(str(svc["project"]), "CLAUDE.md")
    assert ei.value.code == "not_found"


async def test_user_write_creates_and_emits(tmp_path):
    svc = bare_services(tmp_path)
    m, proj, bus = svc["memory"], svc["project"], svc["bus"]
    sub = bus.register()
    res = await m.write_file(scope_dir=str(proj), filename="CLAUDE.md", content="# v1\n", initiator="user")
    assert res["file"]["revision"] >= 1
    assert (proj / "CLAUDE.md").read_text() == "# v1\n"
    ev = sub.get_nowait()
    assert ev["type"] == "memory_changed" and ev["payload"]["op"] == "created"
    assert ev["payload"]["initiator"] == "user"


async def test_conductor_write_is_forbidden(tmp_path):
    svc = bare_services(tmp_path)
    with pytest.raises(ApiError) as ei:
        await svc["memory"].write_file(
            scope_dir=str(svc["project"]), filename="CLAUDE.md", content="x", initiator="conductor"
        )
    assert ei.value.code == "conductor_write_forbidden"


async def test_optimistic_concurrency_checksum_and_revision(tmp_path):
    svc = bare_services(tmp_path)
    m, proj = svc["memory"], svc["project"]
    r1 = await m.write_file(scope_dir=str(proj), filename="CLAUDE.md", content="# a\n", initiator="user")
    # Stale checksum → conflict.
    with pytest.raises(ApiError) as ei:
        await m.write_file(scope_dir=str(proj), filename="CLAUDE.md", content="# b\n",
                           base_checksum="sha256:deadbeef", initiator="user")
    assert ei.value.code == "revision_conflict"
    # Correct base_revision → success, revision increments.
    r2 = await m.write_file(scope_dir=str(proj), filename="CLAUDE.md", content="# b\n",
                            base_revision=r1["file"]["revision"], initiator="user")
    assert r2["file"]["revision"] == r1["file"]["revision"] + 1


async def test_too_large(tmp_path):
    svc = bare_services(tmp_path)
    big = "x" * (MAX_FILE_BYTES + 1)
    with pytest.raises(ApiError) as ei:
        await svc["memory"].write_file(scope_dir=str(svc["project"]), filename="CLAUDE.md", content=big, initiator="user")
    assert ei.value.code == "memory_too_large"


async def test_path_escape_write(tmp_path):
    svc = bare_services(tmp_path)
    with pytest.raises(ApiError) as ei:
        await svc["memory"].write_file(scope_dir=str(svc["project"]), filename="../../etc/passwd",
                                       content="x", initiator="user")
    assert ei.value.code == "path_escape"
    # And nothing was written outside.
    assert not (tmp_path / "etc").exists()


async def test_overlay_file_lives_outside_project(tmp_path):
    svc = bare_services(tmp_path)
    m, proj, paths = svc["memory"], svc["project"], svc["paths"]
    res = await m.write_file(scope_dir=str(proj), filename="NOTES.md", content="notes", initiator="user")
    assert res["file"]["location"] == "overlay"
    # Zero-footprint: NOTES.md must NOT appear in the project tree.
    assert not (proj / "NOTES.md").exists()
    assert str(paths.memory_overlay_dir) in str(paths.state_dir / "memory-overlay")
    # But it is readable back.
    assert m.read_file(str(proj), "NOTES.md")["content"] == "notes"


async def test_delete_user_only_and_emits(tmp_path):
    svc = bare_services(tmp_path)
    m, proj, bus = svc["memory"], svc["project"], svc["bus"]
    await m.write_file(scope_dir=str(proj), filename="CLAUDE.md", content="x", initiator="user")
    with pytest.raises(ApiError):
        await m.delete_file(scope_dir=str(proj), filename="CLAUDE.md", initiator="conductor")
    sub = bus.register()
    res = await m.delete_file(scope_dir=str(proj), filename="CLAUDE.md", initiator="user")
    assert res["deleted"] is True
    assert not (proj / "CLAUDE.md").exists()
    assert sub.get_nowait()["payload"]["op"] == "deleted"
