"""The zero-footprint write-guard (Addendum §A3 — THE hard rule).

Every mutation that could touch the bound project directory passes through this
module. Two guarantees:

1. **Provenance gate.** A project-directory write is permitted only when
   ``initiator == "user"``. A ``conductor`` (or any non-``user``) initiator is
   rejected ``403 conductor_write_forbidden`` and audited. The Conductor may only
   *propose* edits; it never writes.
2. **Path containment.** Scope directories and filenames are validated to
   resolve strictly inside the project (``..``, absolute paths, path separators
   in filenames, and symlink escapes are rejected ``path_escape``) so a write can
   never land outside the granted tree.

This module is intentionally tiny and dependency-light so it can be unit-tested
exhaustively.
"""

from __future__ import annotations

import os
from pathlib import Path

from .errors import ApiError
from .storage import StatePaths, append_audit


class WriteGuard:
    """Gate project-directory writes on ``user`` provenance and path containment."""

    def __init__(self, *, paths: StatePaths) -> None:
        self.paths = paths
        # Canonical (symlink-resolved, absolute) project root — the trust boundary.
        self.project = Path(os.path.realpath(os.path.abspath(str(paths.project_path))))

    # -- containment -------------------------------------------------------
    @staticmethod
    def _canonical(path: str | Path) -> Path:
        return Path(os.path.realpath(os.path.abspath(str(path))))

    def is_inside_project(self, path: str | Path) -> bool:
        """True when ``path`` canonicalizes to the project root or a descendant."""
        try:
            cp = self._canonical(path)
        except (OSError, ValueError):
            return False
        return cp == self.project or self.project in cp.parents

    def assert_scope_within_project(self, scope_dir: str | Path) -> Path:
        """Return the canonical scope dir, or raise ``path_escape``."""
        real = self._canonical(scope_dir)
        if not (real == self.project or self.project in real.parents):
            raise ApiError(
                "path_escape",
                "scope_dir resolves outside the project directory",
                details={"scope_dir": str(scope_dir)},
            )
        return real

    @staticmethod
    def _validate_filename(filename: str) -> None:
        if (
            not filename
            or filename in (".", "..")
            or "/" in filename
            or "\\" in filename
            or "\x00" in filename
            or os.path.isabs(filename)
        ):
            raise ApiError(
                "path_escape",
                "filename must be a bare name inside the scope directory",
                details={"filename": filename},
            )

    def safe_join(self, scope_dir: str | Path, filename: str) -> Path:
        """Validate + join ``scope_dir``/``filename``, guaranteeing containment.

        Raises ``path_escape`` on a bad filename, an escaping scope, or a target
        (after symlink resolution) that would land outside the project.
        """
        self._validate_filename(filename)
        scope = self.assert_scope_within_project(scope_dir)
        target = scope / filename
        # Resolve symlinks on the existing prefix; the bare filename cannot add
        # separators (validated above), so a symlinked target is caught here.
        real = self._canonical(target)
        if not (real == self.project or self.project in real.parents):
            raise ApiError(
                "path_escape",
                "target path resolves outside the project directory",
                details={"scope_dir": str(scope_dir), "filename": filename},
            )
        return target

    # -- provenance --------------------------------------------------------
    def require_user(
        self,
        initiator: str,
        *,
        target_path: str | Path | None = None,
        action: str = "memory_write",
    ) -> None:
        """Reject and audit any non-``user`` initiator (the A3 hard rule).

        This is unconditional for the user-facing memory API (project files and
        overlay alike): only an explicit user action may write. Conductor-origin
        writes are forbidden and recorded in the audit log.
        """
        if initiator != "user":
            append_audit(
                self.paths,
                {
                    "event": "write_denied",
                    "reason": "conductor_write_forbidden",
                    "action": action,
                    "initiator": initiator,
                    "target": str(target_path) if target_path is not None else None,
                },
            )
            raise ApiError(
                "conductor_write_forbidden",
                "Project-directory writes require initiator=user (Addendum §A3); "
                "the Conductor may only propose edits.",
                details={"initiator": initiator, "action": action},
            )

    def guard_project_write(
        self,
        target_path: str | Path,
        initiator: str,
        *,
        action: str = "project_write",
    ) -> None:
        """Combined gate for a concrete project-dir write: provenance if inside.

        A write *inside* the project requires ``user`` provenance; a write to a
        path outside the project (e.g. the out-of-tree overlay) is not gated on
        containment here (the memory API still enforces ``user`` provenance for
        its own writes via :meth:`require_user`).
        """
        if self.is_inside_project(target_path):
            self.require_user(initiator, target_path=target_path, action=action)


__all__ = ["WriteGuard"]
