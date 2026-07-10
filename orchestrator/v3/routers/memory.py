"""Memory endpoints (contract §2.6). Writes are user-initiated only (§A3)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, Query
from pydantic import BaseModel, Field

from ..auth import AUTHORIZED, get_state
from ..state import V3State

router = APIRouter()


class MemoryWriteBody(BaseModel):
    scope_dir: str
    filename: str
    content: str
    base_revision: int | None = None
    base_checksum: str | None = None
    initiator: str = Field(default="user")


class MemoryDeleteBody(BaseModel):
    scope_dir: str | None = None
    filename: str | None = None
    base_revision: int | None = None
    initiator: str = Field(default="user")


@router.get("/memory", dependencies=AUTHORIZED)
async def list_memory(
    scope_dir: str | None = Query(default=None),
    state: V3State = Depends(get_state),
) -> dict[str, Any]:
    return state.memory.list_files(scope_dir)


@router.get("/memory/file", dependencies=AUTHORIZED)
async def read_memory(
    scope_dir: str = Query(...),
    filename: str = Query(...),
    state: V3State = Depends(get_state),
) -> dict[str, Any]:
    return state.memory.read_file(scope_dir, filename)


@router.put("/memory/file", dependencies=AUTHORIZED)
async def write_memory(
    body: MemoryWriteBody,
    state: V3State = Depends(get_state),
) -> dict[str, Any]:
    return await state.memory.write_file(
        scope_dir=body.scope_dir,
        filename=body.filename,
        content=body.content,
        base_revision=body.base_revision,
        base_checksum=body.base_checksum,
        initiator=body.initiator,
    )


@router.delete("/memory/file", dependencies=AUTHORIZED)
async def delete_memory(
    scope_dir: str | None = Query(default=None),
    filename: str | None = Query(default=None),
    base_revision: int | None = Query(default=None),
    body: MemoryDeleteBody | None = Body(default=None),
    state: V3State = Depends(get_state),
) -> dict[str, Any]:
    # Accept params from query or body (contract allows either).
    b = body or MemoryDeleteBody()
    return await state.memory.delete_file(
        scope_dir=b.scope_dir or scope_dir,
        filename=b.filename or filename,
        base_revision=b.base_revision if b.base_revision is not None else base_revision,
        initiator=b.initiator,
    )


__all__ = ["router"]
