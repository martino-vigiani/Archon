"""Conductor endpoints (contract §2.4): message → plan, confirm, cancel."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel, Field

from ..auth import AUTHORIZED, get_state
from ..state import V3State

router = APIRouter()


class ConductorContext(BaseModel):
    active_dir: str | None = None
    selected_card_id: str | None = None
    cap: int | None = None


class MessageBody(BaseModel):
    request_id: str | None = None
    text: str
    source: str = Field(default="text")
    context: ConductorContext = Field(default_factory=ConductorContext)


class ConfirmBody(BaseModel):
    request_id: str | None = None
    cap: int | None = None
    auto_apply: bool = False


@router.post("/conductor/message", dependencies=AUTHORIZED)
async def conductor_message(body: MessageBody, state: V3State = Depends(get_state)) -> dict[str, Any]:
    return await state.conductor.message(
        request_id=body.request_id,
        text=body.text,
        source=body.source,
        context=body.context.model_dump(),
    )


@router.post("/conductor/plans/{plan_id}/confirm", dependencies=AUTHORIZED)
async def confirm_plan(
    plan_id: str,
    body: ConfirmBody | None = Body(default=None),
    state: V3State = Depends(get_state),
) -> dict[str, Any]:
    b = body or ConfirmBody()
    return await state.conductor.confirm(
        plan_id, request_id=b.request_id, cap=b.cap, auto_apply=b.auto_apply
    )


@router.post("/conductor/plans/{plan_id}/cancel", dependencies=AUTHORIZED)
async def cancel_plan(plan_id: str, state: V3State = Depends(get_state)) -> dict[str, Any]:
    return await state.conductor.cancel(plan_id)


__all__ = ["router"]
