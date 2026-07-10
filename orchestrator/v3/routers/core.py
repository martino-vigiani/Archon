"""Core control-plane endpoints: health, project info, and the replay cursor.

* ``GET /v3/health`` — supervision/health-check (token required; answers 200 even
  on a protocol-major mismatch so the client can read ``pv``).
* ``GET /v3/project`` — the fixed single-project binding (Q3); no selection endpoint.
* ``GET /v3/events`` — REST replay mirror of the WS ``resume`` (REQ-BE-043).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from ..auth import TOKEN_ONLY, AUTHORIZED, get_state
from ..state import V3State

router = APIRouter()


@router.get("/health", dependencies=TOKEN_ONLY)
async def health(state: V3State = Depends(get_state)) -> dict[str, Any]:
    return state.health(state.uptime_s())


@router.get("/project", dependencies=AUTHORIZED)
async def project(state: V3State = Depends(get_state)) -> dict[str, Any]:
    return state.project_info()


@router.get("/events", dependencies=AUTHORIZED)
async def events(
    after_seq: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=2000),
    state: V3State = Depends(get_state),
) -> dict[str, Any]:
    evs, truncated = state.bus.snapshot_since(after_seq, limit=limit)
    from_seq = evs[0]["seq"] if evs else after_seq + 1
    next_seq = evs[-1]["seq"] if evs else after_seq
    return {
        "events": evs,
        "from_seq": from_seq,
        "next_seq": next_seq,
        "truncated": truncated,
    }


__all__ = ["router"]
