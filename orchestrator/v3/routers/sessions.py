"""Session endpoints (contract §2.3): list / spawn / detail / kill / flag-idle.

Interactive stdin is intentionally absent in ``pv=1`` (Q11).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..auth import AUTHORIZED, get_state
from ..state import V3State

router = APIRouter()


class SpawnBody(BaseModel):
    request_id: str | None = None
    cwd: str | None = None
    card_id: str | None = None
    initiator: str = Field(default="user")
    prompt: str | None = None
    cap: int | None = None


class KillBody(BaseModel):
    grace_ms: int = 5000
    force: bool = True


class FlagIdleBody(BaseModel):
    flagged: bool = True


@router.get("/sessions", dependencies=AUTHORIZED)
async def list_sessions(state: V3State = Depends(get_state)) -> dict[str, Any]:
    return state.sessions.list_sessions()


@router.post("/sessions", dependencies=AUTHORIZED)
async def spawn_session(body: SpawnBody, state: V3State = Depends(get_state)) -> JSONResponse:
    status_code, payload = await state.sessions.spawn(
        request_id=body.request_id,
        cwd=body.cwd,
        card_id=body.card_id,
        initiator=body.initiator,
        prompt=body.prompt,
        cap=body.cap,
    )
    return JSONResponse(status_code=status_code, content=payload)


@router.get("/sessions/{session_id}", dependencies=AUTHORIZED)
async def session_detail(session_id: str, state: V3State = Depends(get_state)) -> dict[str, Any]:
    return state.sessions.detail(session_id)


@router.post("/sessions/{session_id}/kill", dependencies=AUTHORIZED)
async def kill_session(
    session_id: str,
    body: KillBody | None = Body(default=None),
    state: V3State = Depends(get_state),
) -> JSONResponse:
    b = body or KillBody()
    result = await state.sessions.kill(session_id, grace_ms=b.grace_ms, force=b.force)
    return JSONResponse(status_code=202, content=result)


@router.post("/sessions/{session_id}/flag-idle", dependencies=AUTHORIZED)
async def flag_idle(
    session_id: str,
    body: FlagIdleBody | None = Body(default=None),
    state: V3State = Depends(get_state),
) -> dict[str, Any]:
    b = body or FlagIdleBody()
    return state.sessions.flag_idle(session_id, flagged=b.flagged)


__all__ = ["router"]
