"""Kanban endpoints (contract §2.5): snapshot + card CRUD/move."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..auth import AUTHORIZED, get_state
from ..state import V3State

router = APIRouter()


class CreateCardBody(BaseModel):
    request_id: str | None = None
    title: str
    body: str = ""
    column: str = "queued"
    priority: str = "normal"
    provenance: str = Field(default="user")


class PatchCardBody(BaseModel):
    base_revision: int | None = None
    title: str | None = None
    body: str | None = None
    priority: str | None = None
    status: str | None = None
    provenance: str = Field(default="user")


class MoveCardBody(BaseModel):
    base_revision: int | None = None
    to_column: str
    to_ordinal: int | None = None
    provenance: str = Field(default="user")


class DeleteCardBody(BaseModel):
    base_revision: int | None = None
    provenance: str = Field(default="user")


@router.get("/kanban", dependencies=AUTHORIZED)
async def snapshot(state: V3State = Depends(get_state)) -> dict[str, Any]:
    return await state.kanban.snapshot()


@router.post("/kanban/cards", dependencies=AUTHORIZED)
async def create_card(body: CreateCardBody, state: V3State = Depends(get_state)) -> JSONResponse:
    result = await state.kanban.create_card(
        request_id=body.request_id,
        title=body.title,
        body=body.body,
        column=body.column,
        priority=body.priority,
        provenance=body.provenance,
    )
    return JSONResponse(status_code=201, content=result)


@router.get("/kanban/cards/{card_id}", dependencies=AUTHORIZED)
async def read_card(card_id: str, state: V3State = Depends(get_state)) -> dict[str, Any]:
    return state.kanban.get_card(card_id)


@router.patch("/kanban/cards/{card_id}", dependencies=AUTHORIZED)
async def patch_card(card_id: str, body: PatchCardBody, state: V3State = Depends(get_state)) -> dict[str, Any]:
    return await state.kanban.update_card(
        card_id,
        base_revision=body.base_revision,
        provenance=body.provenance,
        title=body.title,
        body=body.body,
        priority=body.priority,
        status=body.status,
    )


@router.post("/kanban/cards/{card_id}/move", dependencies=AUTHORIZED)
async def move_card(card_id: str, body: MoveCardBody, state: V3State = Depends(get_state)) -> dict[str, Any]:
    return await state.kanban.move_card(
        card_id,
        base_revision=body.base_revision,
        to_column=body.to_column,
        to_ordinal=body.to_ordinal,
        provenance=body.provenance,
    )


@router.delete("/kanban/cards/{card_id}", dependencies=AUTHORIZED)
async def delete_card(
    card_id: str,
    base_revision: int | None = Query(default=None),
    body: DeleteCardBody | None = Body(default=None),
    state: V3State = Depends(get_state),
) -> dict[str, Any]:
    b = body or DeleteCardBody()
    return await state.kanban.delete_card(
        card_id,
        base_revision=b.base_revision if b.base_revision is not None else base_revision,
        provenance=b.provenance,
    )


__all__ = ["router"]
