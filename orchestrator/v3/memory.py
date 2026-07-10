"""Directory-scoped memory files API (contract §2.6, REQ-BE-020..027).

Primary memory reuses the agents' own ``CLAUDE.md`` / ``AGENTS.md`` files
discovered per directory inside the project (Q6). Arbitrary Archon-specific files
are ``overlay`` files stored **outside** the project under
``$PROJECT_STATE/memory-overlay/<rel_dir>/`` (never ``.archon/`` in the project —
§A3). Project files are mutated only by an explicit ``initiator: user`` save; the
write-guard enforces this.

Per-file metadata (revision, owner) can't live in the project (zero-footprint),
so it is tracked in a JSON sidecar in the out-of-project state dir. Optimistic
concurrency uses ``base_revision`` and/or ``base_checksum`` (REQ-BE-023).
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any

from .errors import ApiError
from .events import EventBus
from .storage import StatePaths
from .writeguard import WriteGuard

#: Agent-native filenames that live in the project tree.
PROJECT_KINDS = {"CLAUDE.md": "CLAUDE.md", "AGENTS.md": "AGENTS.md"}

#: Per-file / per-scope quotas (REQ-BE-025).
MAX_FILE_BYTES = 1 * 1024 * 1024  # 1 MB
MAX_SCOPE_BYTES = 32 * 1024 * 1024  # 32 MB
MAX_SCOPE_FILES = 512

#: Directories skipped during discovery to bound cost / respect VCS internals.
_SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".build", "dist", "build", ".archon"}


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


class _MemoryMeta:
    """Tiny JSON sidecar tracking ``(rel_key) -> {revision, owner}`` outside the project."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._data: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        with contextlib.suppress(OSError, ValueError):
            self._data = json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self) -> None:
        with contextlib.suppress(OSError):
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._data), encoding="utf-8")
            os.replace(tmp, self.path)
            os.chmod(self.path, stat.S_IRUSR | stat.S_IWUSR)

    def get(self, key: str) -> dict[str, Any]:
        return self._data.get(key, {"revision": 1, "owner": "user"})

    def bump(self, key: str, owner: str = "user") -> int:
        entry = self._data.get(key, {"revision": 0, "owner": owner})
        entry["revision"] = int(entry.get("revision", 0)) + 1
        entry["owner"] = owner
        self._data[key] = entry
        self._save()
        return entry["revision"]

    def drop(self, key: str) -> None:
        if key in self._data:
            del self._data[key]
            self._save()


class MemoryService:
    """List / read / write / delete directory-scoped memory files."""

    def __init__(self, *, paths: StatePaths, bus: EventBus, guard: WriteGuard) -> None:
        self.paths = paths
        self.bus = bus
        self.guard = guard
        self.project = guard.project
        self._meta = _MemoryMeta(paths.state_dir / "memory-meta.json")

    # -- classification / paths -------------------------------------------
    @staticmethod
    def classify(filename: str) -> tuple[str, str]:
        """Return ``(kind, location)`` for a filename."""
        if filename in PROJECT_KINDS:
            return PROJECT_KINDS[filename], "project"
        return "overlay", "overlay"

    def _rel_dir(self, scope_dir: Path) -> str:
        try:
            return str(scope_dir.relative_to(self.project))
        except ValueError:
            return "."

    def _overlay_path(self, scope_dir: Path, filename: str) -> Path:
        rel = self._rel_dir(scope_dir)
        return self.paths.memory_overlay_dir / rel / filename

    def _meta_key(self, scope_dir: Path, filename: str, location: str) -> str:
        return f"{location}:{self._rel_dir(scope_dir)}/{filename}"

    def _resolve(self, scope_dir_raw: str, filename: str) -> tuple[Path, str, str, Path]:
        """Return ``(scope_dir, kind, location, disk_path)`` with validation.

        Validates scope containment and filename safety. Project files resolve to
        an in-tree path (via the write-guard's safe join); overlay files resolve
        to the out-of-project overlay location.
        """
        kind, location = self.classify(filename)
        scope_dir = self.guard.assert_scope_within_project(scope_dir_raw)
        if location == "project":
            disk = self.guard.safe_join(scope_dir_raw, filename)
        else:
            self.guard._validate_filename(filename)  # noqa: SLF001 - shared validation
            disk = self._overlay_path(scope_dir, filename)
        return scope_dir, kind, location, disk

    # -- file object -------------------------------------------------------
    def _file_object(self, scope_dir: Path, filename: str, location: str, disk: Path) -> dict[str, Any]:
        kind = self.classify(filename)[0]
        data = disk.read_bytes()
        st = disk.stat()
        meta = self._meta.get(self._meta_key(scope_dir, filename, location))
        return {
            "scope_dir": str(scope_dir),
            "filename": filename,
            "kind": kind,
            "location": location,
            "size": st.st_size,
            "mtime": _iso_from_mtime(st.st_mtime),
            "owner": meta.get("owner", "user"),
            "revision": int(meta.get("revision", 1)),
            "checksum": _sha256(data),
            "editable": True,
        }

    # -- list --------------------------------------------------------------
    def list_files(self, scope_dir: str | None = None) -> dict[str, Any]:
        """Discover memory files across the project (or a single scope)."""
        if scope_dir is not None:
            root = self.guard.assert_scope_within_project(scope_dir)
            scope_dirs = [root]
        else:
            scope_dirs = self._walk_dirs(self.project)

        scopes: list[dict[str, Any]] = []
        for d in scope_dirs:
            files: list[dict[str, Any]] = []
            for name in ("CLAUDE.md", "AGENTS.md"):
                p = d / name
                if p.is_file():
                    files.append(self._file_object(d, name, "project", p))
            # Overlay files for this scope.
            overlay_dir = self._overlay_path(d, "").parent
            if overlay_dir.is_dir():
                for p in sorted(overlay_dir.iterdir()):
                    if p.is_file():
                        files.append(self._file_object(d, p.name, "overlay", p))
            if files:
                scopes.append({"scope_dir": str(d), "files": files})
        return {"scopes": scopes}

    def _walk_dirs(self, root: Path) -> list[Path]:
        out: list[Path] = []
        for dirpath, dirnames, _files in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
            out.append(Path(dirpath))
        return out

    # -- read --------------------------------------------------------------
    def read_file(self, scope_dir: str, filename: str) -> dict[str, Any]:
        _scope, _kind, location, disk = self._resolve(scope_dir, filename)
        if not disk.is_file():
            raise ApiError("not_found", "Memory file not found", details={"filename": filename})
        obj = self._file_object(_scope, filename, location, disk)
        return {"file": obj, "content": disk.read_text(encoding="utf-8", errors="replace")}

    # -- write (user-initiated only) --------------------------------------
    async def write_file(
        self,
        *,
        scope_dir: str,
        filename: str,
        content: str,
        base_revision: int | None = None,
        base_checksum: str | None = None,
        initiator: str = "user",
    ) -> dict[str, Any]:
        scope, kind, location, disk = self._resolve(scope_dir, filename)
        # Hard rule: only explicit user action may write (project or overlay).
        self.guard.require_user(initiator, target_path=disk, action="memory_write")

        encoded = content.encode("utf-8")
        if len(encoded) > MAX_FILE_BYTES:
            raise ApiError("memory_too_large", "File exceeds the 1 MB per-file limit")

        self._enforce_scope_quota(scope, disk, len(encoded), location)

        key = self._meta_key(scope, filename, location)
        # Optimistic concurrency: compare against current on-disk state.
        if disk.is_file():
            current = disk.read_bytes()
            cur_meta = self._meta.get(key)
            if base_checksum is not None and _sha256(current) != base_checksum:
                raise ApiError(
                    "revision_conflict",
                    "base_checksum is stale",
                    details={"filename": filename, "current_checksum": _sha256(current)},
                )
            if base_revision is not None and int(cur_meta.get("revision", 1)) != int(base_revision):
                raise ApiError(
                    "revision_conflict",
                    "base_revision is stale",
                    details={"filename": filename, "current_revision": int(cur_meta.get("revision", 1))},
                )
            op = "updated"
        else:
            op = "created"

        _atomic_write_bytes(disk, encoded)
        revision = self._meta.bump(key, owner="user")
        obj = self._file_object(scope, filename, location, disk)
        await self.bus.publish(
            "memory_changed",
            {
                "scope_dir": str(scope),
                "filename": filename,
                "kind": kind,
                "op": op,
                "revision": revision,
                "checksum": obj["checksum"],
                "initiator": "user",
            },
        )
        return {"file": obj}

    # -- delete (user-initiated only) -------------------------------------
    async def delete_file(
        self,
        *,
        scope_dir: str,
        filename: str,
        base_revision: int | None = None,
        initiator: str = "user",
    ) -> dict[str, Any]:
        scope, kind, location, disk = self._resolve(scope_dir, filename)
        self.guard.require_user(initiator, target_path=disk, action="memory_delete")
        if not disk.is_file():
            raise ApiError("not_found", "Memory file not found", details={"filename": filename})
        key = self._meta_key(scope, filename, location)
        cur_meta = self._meta.get(key)
        if base_revision is not None and int(cur_meta.get("revision", 1)) != int(base_revision):
            raise ApiError(
                "revision_conflict",
                "base_revision is stale",
                details={"filename": filename, "current_revision": int(cur_meta.get("revision", 1))},
            )
        with contextlib.suppress(OSError):
            disk.unlink()
        self._meta.drop(key)
        await self.bus.publish(
            "memory_changed",
            {
                "scope_dir": str(scope),
                "filename": filename,
                "kind": kind,
                "op": "deleted",
                "revision": int(cur_meta.get("revision", 1)),
                "checksum": None,
                "initiator": "user",
            },
        )
        return {"deleted": True}

    # -- out-of-band change notification (REQ-BE-026 / REQ-ARCH-054) ------
    async def notify_out_of_band(self, scope_dir: str, filename: str) -> None:
        """Emit a ``memory_changed`` for an externally-detected edit (agent/git)."""
        with contextlib.suppress(ApiError):
            _scope, kind, location, disk = self._resolve(scope_dir, filename)
            op = "updated" if disk.is_file() else "deleted"
            checksum = _sha256(disk.read_bytes()) if disk.is_file() else None
            key = self._meta_key(_scope, filename, location)
            revision = self._meta.bump(key, owner=self._meta.get(key).get("owner", "user"))
            await self.bus.publish(
                "memory_changed",
                {
                    "scope_dir": str(_scope),
                    "filename": filename,
                    "kind": kind,
                    "op": op,
                    "revision": revision,
                    "checksum": checksum,
                    "initiator": "agent",
                },
            )

    def _enforce_scope_quota(self, scope: Path, disk: Path, new_bytes: int, location: str) -> None:
        """Reject writes that would breach the per-scope file/byte quota."""
        # Count sibling memory files in the same scope + location.
        if location == "project":
            siblings = [scope / n for n in ("CLAUDE.md", "AGENTS.md")]
        else:
            odir = self._overlay_path(scope, "").parent
            siblings = list(odir.iterdir()) if odir.is_dir() else []
        existing = [p for p in siblings if p.is_file()]
        total = 0
        count = 0
        for p in existing:
            if p == disk:
                continue
            with contextlib.suppress(OSError):
                total += p.stat().st_size
                count += 1
        if not disk.is_file():
            count += 1
        total += new_bytes
        if count > MAX_SCOPE_FILES:
            raise ApiError("memory_quota_exceeded", "Scope file-count quota exceeded")
        if total > MAX_SCOPE_BYTES:
            raise ApiError("memory_quota_exceeded", "Scope byte quota exceeded")


def _iso_from_mtime(mtime: float) -> str:
    from datetime import datetime, timezone

    return (
        datetime.fromtimestamp(mtime, tz=timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    """Atomic write-temp-then-rename inside the target's directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise


__all__ = ["MemoryService", "MAX_FILE_BYTES", "MAX_SCOPE_BYTES", "MAX_SCOPE_FILES"]
