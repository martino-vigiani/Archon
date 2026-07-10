"""FastAPI app factory for the V3 orchestrator (contract §1–§3).

Two entry points:

* :func:`create_v3_app` — build a standalone ASGI app bound to one project
  directory (the primary, client-supervised deployment; ``python -m
  orchestrator.v3`` runs this under uvicorn).
* :func:`mount_v3` — attach the same ``/v3`` routes onto an existing FastAPI app
  (optional integration with the legacy dashboard). It does not modify or import
  ``dashboard.py``; the legacy 778-test surface is untouched.

All feature services (sessions / kanban / memory / conductor) are constructed
here and injected into :class:`~orchestrator.v3.state.V3State`, so the wiring —
and every seam — lives in one place.
"""

from __future__ import annotations

import os
import secrets
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from . import HARD_CEILING_DEFAULT, ORCHESTRATOR_VERSION
from .conductor import Conductor
from .errors import install_error_handlers
from .events import EventBus
from .kanban import KanbanStore
from .memory import MemoryService
from .provider import make_default_provider
from .routers.conductor import router as conductor_router
from .routers.core import router as core_router
from .routers.kanban import router as kanban_router
from .routers.memory import router as memory_router
from .routers.sessions import router as sessions_router
from .session_manager import SessionManager
from .state import V3State
from .storage import delete_runtime_file, resolve_paths, write_runtime_file
from .stream import router as stream_router
from .writeguard import WriteGuard

_FEATURE_ROUTERS = (
    core_router,
    sessions_router,
    kanban_router,
    memory_router,
    conductor_router,
    stream_router,
)


def build_state(
    project_path: str,
    *,
    port: int = 0,
    token: str | None = None,
    support: Any | None = None,
    provider: Any | None = None,
    ceiling: int = HARD_CEILING_DEFAULT,
    adapter: Any | None = None,
) -> V3State:
    """Construct a fully-wired :class:`V3State` for a bound project directory."""
    paths = resolve_paths(project_path, support=support)
    paths.ensure()
    token = token or secrets.token_hex(32)
    bus = EventBus()

    prov = provider if provider is not None else make_default_provider(paths)
    provider_ready = bool(getattr(prov, "ready", False))

    state = V3State(paths=paths, token=token, port=port, bus=bus, provider_ready=provider_ready)

    guard = WriteGuard(paths=paths)
    memory = MemoryService(paths=paths, bus=bus, guard=guard)
    kanban = KanbanStore(db_path=paths.kanban_db, bus=bus)
    sessions = SessionManager(paths=paths, bus=bus, ceiling=ceiling, adapter=adapter)
    conductor = Conductor(
        paths=paths,
        bus=bus,
        sessions=sessions,
        kanban=kanban,
        memory=memory,
        provider=prov,
        ceiling=ceiling,
    )

    state.writeguard = guard
    state.memory = memory
    state.kanban = kanban
    state.sessions = sessions
    state.conductor = conductor
    return state


def _register_routes(app: FastAPI) -> None:
    install_error_handlers(app)
    for router in _FEATURE_ROUTERS:
        app.include_router(router, prefix="/v3")


def create_v3_app(
    project_path: str,
    *,
    port: int = 0,
    token: str | None = None,
    support: Any | None = None,
    provider: Any | None = None,
    ceiling: int = HARD_CEILING_DEFAULT,
    adapter: Any | None = None,
    write_runtime: bool | None = None,
) -> FastAPI:
    """Build a standalone V3 ASGI app bound to ``project_path``.

    Args:
        project_path: The project directory this instance drives (single-project).
        port: The port the app will be served on; when > 0 (and ``write_runtime``
            is not False) the ``0600`` ``runtime.json`` handshake is written on
            startup and removed on clean shutdown.
        token: Bearer token; a fresh 256-bit token is minted when omitted.
        support: Override for the Application-Support root (tests).
        provider: Injected conductor provider (tests); defaults to the real one.
        ceiling: Hard concurrency ceiling (REQ-BE-004).
        adapter: Injected PTY adapter (tests); defaults to the Claude Code adapter.
        write_runtime: Force/suppress the runtime-file handshake; defaults to
            "write when ``port > 0``".
    """
    state = build_state(
        project_path,
        port=port,
        token=token,
        support=support,
        provider=provider,
        ceiling=ceiling,
        adapter=adapter,
    )
    do_write = (port > 0) if write_runtime is None else write_runtime

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await state.start()
        if do_write:
            write_runtime_file(
                state.paths, port=state.port, pid=os.getpid(), token=state.token
            )
        try:
            yield
        finally:
            await state.stop()
            if do_write:
                delete_runtime_file(state.paths.runtime_file)

    app = FastAPI(title="Archon V3 Orchestrator", version=ORCHESTRATOR_VERSION, lifespan=lifespan)
    app.state.v3 = state
    _register_routes(app)
    return app


def mount_v3(
    existing_app: FastAPI,
    project_path: str,
    *,
    port: int = 0,
    token: str | None = None,
    support: Any | None = None,
    provider: Any | None = None,
    ceiling: int = HARD_CEILING_DEFAULT,
    adapter: Any | None = None,
    write_runtime: bool = False,
) -> V3State:
    """Attach the ``/v3`` routes to an existing FastAPI app; return the V3State.

    The caller owns the app's lifespan; this registers startup/shutdown handlers
    to run feature-service lifecycle and (optionally) the runtime handshake.
    """
    state = build_state(
        project_path,
        port=port,
        token=token,
        support=support,
        provider=provider,
        ceiling=ceiling,
        adapter=adapter,
    )
    existing_app.state.v3 = state
    _register_routes(existing_app)

    async def _startup() -> None:
        await state.start()
        if write_runtime:
            write_runtime_file(state.paths, port=state.port, pid=os.getpid(), token=state.token)

    async def _shutdown() -> None:
        await state.stop()
        if write_runtime:
            delete_runtime_file(state.paths.runtime_file)

    # FastAPI 0.139 removed ``add_event_handler``; append to the router's
    # lifespan lists (honored by the default lifespan when the host app has not
    # supplied its own context-manager lifespan).
    existing_app.router.on_startup.append(_startup)
    existing_app.router.on_shutdown.append(_shutdown)
    return state


__all__ = ["create_v3_app", "mount_v3", "build_state"]
