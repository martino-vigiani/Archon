"""Out-of-project state storage & the ``0600`` runtime handshake (Addendum A3).

THE zero-footprint rule: nothing the app/orchestrator owns is ever written
inside the bound project directory. All runtime state lives under::

    $SUPPORT        = ~/Library/Application Support/Archon
    $PROJECT_STATE  = $SUPPORT/projects/<project_id>/

where ``project_id = sha256_hex(canonical_project_path)``. This module owns:

* computing those paths,
* the atomic, ``0600`` ``runtime.json`` handshake (write-temp-then-rename),
* refusing to read a ``token``-bearing file that is group/world-readable.

Files inside the project may change *only* through an agent PTY session or an
explicit ``initiator: user`` action — enforced by :mod:`writeguard`, not here.
"""

from __future__ import annotations

import contextlib
import json
import os
import stat
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import PROTOCOL_VERSION
from .ids import canonical_project_path, project_id_for


def support_root() -> Path:
    """Return ``~/Library/Application Support/Archon`` (override via env for tests)."""
    override = os.environ.get("ARCHON_V3_SUPPORT_DIR")
    if override:
        return Path(override)
    return Path.home() / "Library" / "Application Support" / "Archon"


def project_state_dir(project_path: str | Path, *, support: Path | None = None) -> Path:
    """Return ``$SUPPORT/projects/<project_id>/`` for a project path."""
    base = support or support_root()
    return base / "projects" / project_id_for(project_path)


@dataclass(frozen=True)
class StatePaths:
    """Resolved on-disk locations for a single bound project's runtime state."""

    project_path: Path
    project_id: str
    state_dir: Path

    @property
    def runtime_file(self) -> Path:
        return self.state_dir / "runtime.json"

    @property
    def kanban_db(self) -> Path:
        return self.state_dir / "kanban.sqlite3"

    @property
    def audit_log(self) -> Path:
        return self.state_dir / "audit.log"

    @property
    def memory_overlay_dir(self) -> Path:
        return self.state_dir / "memory-overlay"

    def ensure(self) -> None:
        """Create the state dir (owner-only) without touching the project tree."""
        self.state_dir.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError):
            os.chmod(self.state_dir, stat.S_IRWXU)  # 0o700


def resolve_paths(project_path: str | Path, *, support: Path | None = None) -> StatePaths:
    """Resolve all state paths for a project (canonicalizing the project path)."""
    canonical = canonical_project_path(project_path)
    return StatePaths(
        project_path=Path(canonical),
        project_id=project_id_for(project_path),
        state_dir=project_state_dir(project_path, support=support),
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def write_runtime_file(
    paths: StatePaths,
    *,
    port: int,
    pid: int,
    token: str,
    started_at: str | None = None,
) -> Path:
    """Atomically write ``runtime.json`` with mode ``0600`` (contract §1.2).

    Uses write-temp-then-rename with the temp file created ``0600`` from birth so
    the token is never briefly world-readable. Raises ``OSError`` if the file
    cannot be created ``0600`` (the caller MUST then refuse to start).
    """
    paths.ensure()
    payload: dict[str, Any] = {
        "pv": PROTOCOL_VERSION,
        "port": int(port),
        "pid": int(pid),
        "token": token,
        "project_id": paths.project_id,
        "project_path": str(paths.project_path),
        "started_at": started_at or _now_iso(),
    }
    target = paths.runtime_file
    fd, tmp_name = tempfile.mkstemp(prefix="runtime.", suffix=".tmp", dir=str(paths.state_dir))
    tmp_path = Path(tmp_name)
    try:
        os.fchmod(fd, stat.S_IRUSR | stat.S_IWUSR)  # 0o600 before any content
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, target)
        os.chmod(target, stat.S_IRUSR | stat.S_IWUSR)  # 0o600 on the final path
    except BaseException:
        with contextlib.suppress(OSError):
            tmp_path.unlink()
        raise
    return target


def read_runtime_file(path: Path) -> dict[str, Any]:
    """Read a ``runtime.json`` file, refusing group/world-readable token files.

    Raises:
        PermissionError: if the file is readable by group or others (the token
            must be owner-only, contract §1.2).
        FileNotFoundError / ValueError: on a missing or malformed file.
    """
    st = path.stat()
    if st.st_mode & (stat.S_IRGRP | stat.S_IROTH | stat.S_IWGRP | stat.S_IWOTH):
        raise PermissionError(f"runtime file {path} is group/world-accessible; refusing to read token")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("runtime.json is not an object")
    return data


def delete_runtime_file(path: Path) -> None:
    """Best-effort removal on clean shutdown (a stale file is ignored by clients)."""
    with contextlib.suppress(OSError):
        path.unlink()


def append_audit(paths: StatePaths, record: dict[str, Any]) -> None:
    """Append one JSON line to the audit log (owner-only). Best-effort."""
    with contextlib.suppress(OSError):
        paths.ensure()
        entry = {"ts": _now_iso(), **record}
        with open(paths.audit_log, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, default=str) + "\n")
        with contextlib.suppress(OSError):
            os.chmod(paths.audit_log, stat.S_IRUSR | stat.S_IWUSR)


__all__ = [
    "StatePaths",
    "support_root",
    "project_state_dir",
    "resolve_paths",
    "write_runtime_file",
    "read_runtime_file",
    "delete_runtime_file",
    "append_audit",
]
