"""Kanban board: SQLite-backed, five fixed columns (contract §2.5, REQ-BE-010..017).

Columns are fixed, ordered, non-renameable: ``queued, in_progress, blocked,
review, done``. The store lives in the out-of-project state dir (Addendum §A3 —
never inside the project). Cards carry a monotonic ``revision`` for optimistic
concurrency (REQ-BE-015) and a board-wide ``board_revision``. Every mutation
emits exactly one ``kanban_updated`` event so the board is reconstructable from
the stream alone (REQ-BE-016).
"""

from __future__ import annotations

import contextlib
import sqlite3
import threading
from pathlib import Path
from typing import Any

from .errors import ApiError
from .events import EventBus
from .ids import new_ulid
from .util import now_iso

COLUMNS: tuple[str, ...] = ("queued", "in_progress", "blocked", "review", "done")
PRIORITIES = frozenset({"low", "normal", "high"})
PROVENANCES = frozenset({"user", "conductor"})
STATUSES = frozenset({"idle", "running", "blocked", "error", "done"})

#: Legal column transitions (REQ-BE-011). Reorder (to==from) is always legal.
#: ``done`` may only reopen to ``review`` — ``done→in_progress`` is illegal.
_ALLOWED_MOVES: dict[str, frozenset[str]] = {
    "queued": frozenset({"queued", "in_progress", "blocked", "review", "done"}),
    "in_progress": frozenset({"in_progress", "blocked", "review", "done", "queued"}),
    "blocked": frozenset({"blocked", "in_progress", "review", "queued", "done"}),
    "review": frozenset({"review", "in_progress", "done", "blocked", "queued"}),
    "done": frozenset({"done", "review"}),
}

_DEFAULT_STATUS_BY_COLUMN = {
    "queued": "idle",
    "in_progress": "running",
    "blocked": "blocked",
    "review": "idle",
    "done": "done",
}

_CARD_COLUMNS = (
    "card_id",
    "title",
    "body",
    "column",
    "ordinal",
    "priority",
    "provenance",
    "session_id",
    "status",
    "revision",
    "created_at",
    "updated_at",
)


class KanbanStore:
    """Thread-safe SQLite kanban store with event emission."""

    def __init__(self, *, db_path: Path, bus: EventBus) -> None:
        self.bus = bus
        self._lock = threading.RLock()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # WAL keeps reads from blocking the single writer; busy_timeout lets a
        # transient lock (e.g. an OS-level flush) retry instead of erroring.
        with contextlib.suppress(sqlite3.Error):
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=5000")
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS cards (
                    card_id     TEXT PRIMARY KEY,
                    title       TEXT NOT NULL,
                    body        TEXT NOT NULL DEFAULT '',
                    column      TEXT NOT NULL,
                    ordinal     INTEGER NOT NULL,
                    priority    TEXT NOT NULL DEFAULT 'normal',
                    provenance  TEXT NOT NULL DEFAULT 'user',
                    session_id  TEXT,
                    status      TEXT NOT NULL DEFAULT 'idle',
                    revision    INTEGER NOT NULL DEFAULT 1,
                    created_at  TEXT NOT NULL,
                    updated_at  TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS board_meta (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    board_revision INTEGER NOT NULL
                );
                INSERT OR IGNORE INTO board_meta (id, board_revision) VALUES (1, 0);
                """
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # -- helpers -----------------------------------------------------------
    def _board_revision(self) -> int:
        row = self._conn.execute("SELECT board_revision FROM board_meta WHERE id = 1").fetchone()
        return int(row["board_revision"]) if row else 0

    def _bump_board(self) -> int:
        self._conn.execute("UPDATE board_meta SET board_revision = board_revision + 1 WHERE id = 1")
        return self._board_revision()

    @staticmethod
    def _row_to_card(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "card_id": row["card_id"],
            "title": row["title"],
            "body": row["body"],
            "column": row["column"],
            "ordinal": row["ordinal"],
            "priority": row["priority"],
            "provenance": row["provenance"],
            "session_id": row["session_id"],
            "status": row["status"],
            "revision": row["revision"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _get_row(self, card_id: str) -> sqlite3.Row:
        row = self._conn.execute("SELECT * FROM cards WHERE card_id = ?", (card_id,)).fetchone()
        if row is None:
            raise ApiError("not_found", "Card not found", details={"card_id": card_id})
        return row

    def _repack(self, column: str) -> None:
        """Re-number a column's ordinals contiguously from 0, preserving order."""
        rows = self._conn.execute(
            "SELECT card_id FROM cards WHERE column = ? ORDER BY ordinal ASC, updated_at ASC",
            (column,),
        ).fetchall()
        for i, r in enumerate(rows):
            self._conn.execute("UPDATE cards SET ordinal = ? WHERE card_id = ?", (i, r["card_id"]))

    @staticmethod
    def _check_revision(row: sqlite3.Row, base_revision: int | None) -> None:
        if base_revision is not None and int(row["revision"]) != int(base_revision):
            raise ApiError(
                "revision_conflict",
                f"Card revision {row['revision']} is stale; you sent {base_revision}.",
                details={"card_id": row["card_id"], "expected_revision": int(row["revision"])},
            )

    # -- snapshot ----------------------------------------------------------
    def snapshot_sync(self) -> dict[str, Any]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM cards ORDER BY column, ordinal ASC"
            ).fetchall()
            return {
                "columns": list(COLUMNS),
                "cards": [self._row_to_card(r) for r in rows],
                "board_revision": self._board_revision(),
            }

    async def snapshot(self) -> dict[str, Any]:
        return self.snapshot_sync()

    async def emit_snapshot(self) -> dict[str, Any]:
        """Publish a full ``kanban_updated:snapshot`` (used on resync)."""
        snap = self.snapshot_sync()
        await self.bus.publish(
            "kanban_updated",
            {"op": "snapshot", "cards": snap["cards"], "board_revision": snap["board_revision"]},
        )
        return snap

    # -- create ------------------------------------------------------------
    async def create_card(
        self,
        *,
        request_id: str | None = None,
        title: str,
        body: str = "",
        column: str = "queued",
        priority: str = "normal",
        provenance: str = "user",
        session_id: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        self._validate_column(column)
        self._validate_priority(priority)
        self._validate_provenance(provenance)
        if status is not None and status not in STATUSES:
            raise ApiError("validation_error", f"Invalid status {status!r}")
        with self._lock:
            now = now_iso()
            card_id = new_ulid()
            row = self._conn.execute(
                "SELECT COALESCE(MAX(ordinal), -1) + 1 AS nxt FROM cards WHERE column = ?",
                (column,),
            ).fetchone()
            ordinal = int(row["nxt"])
            eff_status = status or _DEFAULT_STATUS_BY_COLUMN.get(column, "idle")
            self._conn.execute(
                """INSERT INTO cards
                   (card_id, title, body, column, ordinal, priority, provenance,
                    session_id, status, revision, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
                (card_id, title, body, column, ordinal, priority, provenance,
                 session_id, eff_status, now, now),
            )
            board_rev = self._bump_board()
            self._conn.commit()
            card = self._row_to_card(self._get_row(card_id))
        await self.bus.publish(
            "kanban_updated",
            {"op": "created", "card": card, "board_revision": board_rev},
            task_id=card_id,
        )
        return {"card": card}

    # -- read --------------------------------------------------------------
    def get_card(self, card_id: str) -> dict[str, Any]:
        with self._lock:
            return {"card": self._row_to_card(self._get_row(card_id))}

    # -- update ------------------------------------------------------------
    async def update_card(
        self,
        card_id: str,
        *,
        base_revision: int | None = None,
        provenance: str = "user",
        **fields: Any,
    ) -> dict[str, Any]:
        with self._lock:
            row = self._get_row(card_id)
            self._check_revision(row, base_revision)
            updates: dict[str, Any] = {}
            for key in ("title", "body", "priority", "status", "session_id"):
                if key in fields and fields[key] is not None:
                    updates[key] = fields[key]
            if "priority" in updates:
                self._validate_priority(updates["priority"])
            if "status" in updates and updates["status"] not in STATUSES:
                raise ApiError("validation_error", f"Invalid status {updates['status']!r}")
            now = now_iso()
            new_rev = int(row["revision"]) + 1
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            params: list[Any] = list(updates.values())
            if set_clause:
                set_clause += ", "
            self._conn.execute(
                f"UPDATE cards SET {set_clause}revision = ?, updated_at = ? WHERE card_id = ?",
                (*params, new_rev, now, card_id),
            )
            board_rev = self._bump_board()
            self._conn.commit()
            card = self._row_to_card(self._get_row(card_id))
        await self.bus.publish(
            "kanban_updated",
            {"op": "updated", "card": card, "board_revision": board_rev},
            task_id=card_id,
        )
        return {"card": card}

    # -- move / reorder ----------------------------------------------------
    async def move_card(
        self,
        card_id: str,
        *,
        base_revision: int | None = None,
        to_column: str,
        to_ordinal: int | None = None,
        provenance: str = "user",
    ) -> dict[str, Any]:
        self._validate_column(to_column)
        with self._lock:
            row = self._get_row(card_id)
            self._check_revision(row, base_revision)
            from_column = row["column"]
            from_ordinal = int(row["ordinal"])
            if to_column not in _ALLOWED_MOVES.get(from_column, frozenset()):
                raise ApiError(
                    "illegal_transition",
                    f"Move {from_column}→{to_column} is not allowed.",
                    details={"card_id": card_id, "from": from_column, "to": to_column},
                )
            now = now_iso()
            new_rev = int(row["revision"]) + 1

            # Detach the card to a sentinel ordinal, repack the source column.
            self._conn.execute(
                "UPDATE cards SET column = ?, ordinal = ?, revision = ?, updated_at = ? WHERE card_id = ?",
                (to_column, 10_000_000, new_rev, now, card_id),
            )
            if from_column != to_column:
                self._repack(from_column)

            # Insert at the requested position within the target column.
            siblings = self._conn.execute(
                "SELECT card_id FROM cards WHERE column = ? AND card_id != ? ORDER BY ordinal ASC",
                (to_column, card_id),
            ).fetchall()
            ids = [r["card_id"] for r in siblings]
            insert_at = len(ids) if to_ordinal is None else max(0, min(int(to_ordinal), len(ids)))
            ids.insert(insert_at, card_id)
            for i, cid in enumerate(ids):
                self._conn.execute("UPDATE cards SET ordinal = ? WHERE card_id = ?", (i, cid))

            # Moving to done releases any bound session (REQ-BE-014).
            if to_column == "done":
                self._conn.execute(
                    "UPDATE cards SET session_id = NULL, status = 'done' WHERE card_id = ?", (card_id,)
                )
            board_rev = self._bump_board()
            self._conn.commit()
            card = self._row_to_card(self._get_row(card_id))
        await self.bus.publish(
            "kanban_updated",
            {
                "op": "moved",
                "card": card,
                "from": {"column": from_column, "ordinal": from_ordinal},
                "to": {"column": card["column"], "ordinal": card["ordinal"]},
                "board_revision": board_rev,
            },
            task_id=card_id,
        )
        return {"card": card, "board_revision": board_rev}

    # -- delete ------------------------------------------------------------
    async def delete_card(
        self,
        card_id: str,
        *,
        base_revision: int | None = None,
        provenance: str = "user",
    ) -> dict[str, Any]:
        with self._lock:
            row = self._get_row(card_id)
            self._check_revision(row, base_revision)
            column = row["column"]
            self._conn.execute("DELETE FROM cards WHERE card_id = ?", (card_id,))
            self._repack(column)
            board_rev = self._bump_board()
            self._conn.commit()
        await self.bus.publish(
            "kanban_updated",
            {"op": "deleted", "card_id": card_id, "board_revision": board_rev},
            task_id=card_id,
        )
        return {"card_id": card_id, "deleted": True}

    # -- session binding (used by the policy engine / conductor) ----------
    async def bind_session(self, card_id: str, session_id: str | None, *, status: str | None = None) -> None:
        """Attach/detach a session to a card and emit an update (best-effort)."""
        with self._lock:
            row = self._conn.execute("SELECT * FROM cards WHERE card_id = ?", (card_id,)).fetchone()
            if row is None:
                return
            now = now_iso()
            new_rev = int(row["revision"]) + 1
            eff_status = status or row["status"]
            self._conn.execute(
                "UPDATE cards SET session_id = ?, status = ?, revision = ?, updated_at = ? WHERE card_id = ?",
                (session_id, eff_status, new_rev, now, card_id),
            )
            board_rev = self._bump_board()
            self._conn.commit()
            card = self._row_to_card(self._get_row(card_id))
        await self.bus.publish(
            "kanban_updated",
            {"op": "updated", "card": card, "board_revision": board_rev},
            task_id=card_id,
        )

    # -- validation --------------------------------------------------------
    @staticmethod
    def _validate_column(column: str) -> None:
        if column not in COLUMNS:
            raise ApiError("validation_error", f"Unknown column {column!r}", details={"columns": list(COLUMNS)})

    @staticmethod
    def _validate_priority(priority: str) -> None:
        if priority not in PRIORITIES:
            raise ApiError("validation_error", f"Invalid priority {priority!r}")

    @staticmethod
    def _validate_provenance(provenance: str) -> None:
        if provenance not in PROVENANCES:
            raise ApiError("validation_error", f"Invalid provenance {provenance!r}")


__all__ = ["KanbanStore", "COLUMNS", "STATUSES", "PRIORITIES", "PROVENANCES"]
