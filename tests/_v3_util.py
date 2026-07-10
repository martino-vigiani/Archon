"""Shared helpers for the Archon V3 backend tests (not collected as tests)."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from orchestrator.v3.app import create_v3_app, build_state
from orchestrator.v3.adapters import EchoAdapter
from orchestrator.v3.events import EventBus
from orchestrator.v3.kanban import KanbanStore
from orchestrator.v3.memory import MemoryService
from orchestrator.v3.provider import FallbackProvider
from orchestrator.v3.storage import resolve_paths
from orchestrator.v3.writeguard import WriteGuard

TOKEN = "test-token-abc"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}


def new_project(tmp_path: Path) -> Path:
    """Create an isolated project dir under ``tmp_path``."""
    proj = tmp_path / "project"
    proj.mkdir(exist_ok=True)
    return proj


def new_support(tmp_path: Path) -> Path:
    support = tmp_path / "support"
    support.mkdir(exist_ok=True)
    return support


def make_app(tmp_path: Path, *, lines: int = 2, provider: Any | None = None):
    """Build a standalone V3 app with the Echo PTY adapter + fallback provider."""
    proj = new_project(tmp_path)
    support = new_support(tmp_path)
    app = create_v3_app(
        str(proj),
        token=TOKEN,
        support=support,
        provider=provider or FallbackProvider(),
        adapter=EchoAdapter(lines=lines),
    )
    return app, proj, support


def make_state(tmp_path: Path, *, provider: Any | None = None):
    proj = new_project(tmp_path)
    support = new_support(tmp_path)
    state = build_state(
        str(proj),
        token=TOKEN,
        support=support,
        provider=provider or FallbackProvider(),
        adapter=EchoAdapter(lines=2),
    )
    return state, proj, support


def bare_services(tmp_path: Path):
    """Construct kanban/memory/writeguard directly against a fresh bus (unit tests)."""
    proj = new_project(tmp_path)
    support = new_support(tmp_path)
    paths = resolve_paths(str(proj), support=support)
    paths.ensure()
    bus = EventBus()
    guard = WriteGuard(paths=paths)
    memory = MemoryService(paths=paths, bus=bus, guard=guard)
    kanban = KanbanStore(db_path=paths.kanban_db, bus=bus)
    return {
        "paths": paths,
        "bus": bus,
        "guard": guard,
        "memory": memory,
        "kanban": kanban,
        "project": Path(paths.project_path),
        "support": support,
    }
