"""The single ``/v3/stream`` WebSocket endpoint (contract §3).

One full-duplex socket per client. Server→client is the globally-ordered event
stream from :class:`~orchestrator.v3.events.EventBus`; client→server carries
small control frames (``resume`` / ``subscribe`` / ``unsubscribe`` / ``ping``).

Responsibilities:

* auth + origin + version gate (close ``1008`` on failure) before the socket is usable;
* send exactly one ``hello`` frame, then live deltas (snapshots come via REST);
* heartbeats every ≤ 15 s (client treats two misses ~30 s as stale);
* honor ``resume{after_seq}`` (replay ring; ``truncated`` → fresh ``hello``);
* enforce §3.5 backpressure: ``pty_output`` drop-with-marker, never-drop topics
  disconnect with ``error(code=rate_limited)``.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect, WebSocketState

from . import PROTOCOL_VERSION, ORCHESTRATOR_VERSION, REPLAY_MAX_EVENTS, REPLAY_WINDOW_S
from .auth import ws_auth_check
from .errors import error_body
from .events import ALL_TOPICS, EventBus, Subscriber
from .util import now_iso

router = APIRouter()

HEARTBEAT_INTERVAL_S = 10.0


def _hello_frame(bus: EventBus, conductor_state: str, *, truncated: bool = False) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "pv": PROTOCOL_VERSION,
        "orchestrator_version": ORCHESTRATOR_VERSION,
        "current_seq": bus.current_seq(),
        "replay_window_events": REPLAY_MAX_EVENTS,
        "replay_window_s": REPLAY_WINDOW_S,
        "resume_supported": True,
        "conductor_state": conductor_state,
    }
    if truncated:
        payload["truncated"] = True
    return {
        "v": PROTOCOL_VERSION,
        "seq": bus.current_seq(),
        "ts": now_iso(),
        "type": "hello",
        "payload": payload,
    }


def _heartbeat_frame(bus: EventBus, pong: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"current_seq": bus.current_seq()}
    if pong is not None:
        payload["pong"] = pong
    return {
        "v": PROTOCOL_VERSION,
        "seq": bus.current_seq(),
        "ts": now_iso(),
        "type": "heartbeat",
        "payload": payload,
    }


def _parse_topics(raw: Any) -> frozenset[str]:
    if not isinstance(raw, list):
        return ALL_TOPICS
    return frozenset(str(t) for t in raw) & ALL_TOPICS


@router.websocket("/stream")
async def stream_endpoint(websocket: WebSocket) -> None:
    state = getattr(websocket.app.state, "v3", None)
    if state is None:  # pragma: no cover - misconfiguration
        await websocket.close(code=1011)
        return

    bus: EventBus = state.bus
    ok, close_code, reason = ws_auth_check(websocket, state)
    if not ok:
        await websocket.accept()
        with contextlib.suppress(Exception):
            if reason == "incompatible_version":
                await websocket.send_json(
                    {
                        "v": PROTOCOL_VERSION,
                        "seq": bus.current_seq(),
                        "ts": now_iso(),
                        "type": "error",
                        "payload": error_body("incompatible_version", "Protocol major mismatch"),
                    }
                )
        await websocket.close(code=close_code)
        return

    await websocket.accept()
    sub: Subscriber = bus.register()
    # Serialize every outbound frame through one lock: the sender, the receiver
    # (pong / resume-hello) and the heartbeat all write to the same socket, and
    # Starlette does not document concurrent sends as safe (frames could interleave
    # at the ASGI layer). All sends after the initial hello go through this lock.
    send_lock = asyncio.Lock()
    try:
        await websocket.send_json(_hello_frame(bus, state.conductor_state()))
        sender = asyncio.create_task(_sender_loop(websocket, bus, sub, send_lock))
        receiver = asyncio.create_task(_receiver_loop(websocket, bus, sub, send_lock))
        heartbeat = asyncio.create_task(_heartbeat_loop(websocket, bus, sub, send_lock))
        done, pending = await asyncio.wait(
            {sender, receiver, heartbeat}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, WebSocketDisconnect, Exception):
                await task
        # Retrieve exceptions from completed tasks so they are never "un-retrieved"
        # (a client disconnect surfaces here as WebSocketDisconnect — expected).
        for task in done:
            with contextlib.suppress(asyncio.CancelledError, WebSocketDisconnect, Exception):
                task.result()
    except WebSocketDisconnect:
        pass
    finally:
        bus.unregister(sub)
        with contextlib.suppress(Exception):
            if websocket.client_state != WebSocketState.DISCONNECTED:
                await websocket.close()


async def _sender_loop(
    websocket: WebSocket, bus: EventBus, sub: Subscriber, send_lock: asyncio.Lock
) -> None:
    """Drain the subscriber queue to the socket, honoring backpressure."""
    while True:
        env = await sub.get()
        async with send_lock:
            await websocket.send_json(env)
            # Emit any coalesced pty_output drop markers accumulated during overflow.
            for marker in sub.take_drop_markers():
                await websocket.send_json(marker)
        # A never-drop topic overflowed → clean disconnect for resync.
        if sub.must_disconnect:
            async with send_lock:
                with contextlib.suppress(Exception):
                    await websocket.send_json(
                        {
                            "v": PROTOCOL_VERSION,
                            "seq": None,
                            "ts": now_iso(),
                            "type": "error",
                            "payload": error_body(
                                "rate_limited", "Stream consumer too slow; reconnect and resync."
                            ),
                        }
                    )
            await websocket.close(code=1013)  # try-again-later
            return


async def _receiver_loop(
    websocket: WebSocket, bus: EventBus, sub: Subscriber, send_lock: asyncio.Lock
) -> None:
    """Handle client control frames: resume / subscribe / unsubscribe / ping."""
    while True:
        msg = await websocket.receive_json()
        if not isinstance(msg, dict):
            continue
        mtype = msg.get("type")
        if mtype == "ping":
            async with send_lock:
                await websocket.send_json(_heartbeat_frame(bus, pong=str(msg.get("id", ""))))
        elif mtype == "subscribe":
            sub.set_topics(_parse_topics(msg.get("topics")))
        elif mtype == "unsubscribe":
            current = set(sub.topics)
            for t in _parse_topics(msg.get("topics")):
                current.discard(t)
            sub.set_topics(frozenset(current))
        elif mtype == "resume":
            after = msg.get("after_seq", 0)
            try:
                after_seq = int(after)
            except (TypeError, ValueError):
                after_seq = 0
            truncated = bus.replay_into(sub, after_seq)
            if truncated:
                state = getattr(websocket.app.state, "v3", None)
                cstate = state.conductor_state() if state else "idle"
                async with send_lock:
                    await websocket.send_json(_hello_frame(bus, cstate, truncated=True))
        # Unknown control frames are ignored (additive-only tolerance).


async def _heartbeat_loop(
    websocket: WebSocket, bus: EventBus, sub: Subscriber, send_lock: asyncio.Lock
) -> None:
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL_S)
        async with send_lock:
            await websocket.send_json(_heartbeat_frame(bus))
            # Also flush any pending pty_output drop markers here: if the queue
            # drained right after an overflow burst and the stream went quiet, the
            # sender loop won't wake until the next event, so the "output truncated"
            # break would otherwise be withheld indefinitely (heartbeats bypass the
            # sender queue). Bounding the delay to one heartbeat closes that hole.
            for marker in sub.take_drop_markers():
                await websocket.send_json(marker)


__all__ = ["router"]
