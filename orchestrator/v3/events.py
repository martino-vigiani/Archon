"""Event bus, global sequencing, replay ring, and per-connection fan-out.

Server→client is a single globally-ordered event stream (contract §3.1):

* Every emitted envelope gets a **single, connection-independent, monotonic,
  gap-free** ``seq`` assigned under a lock. That ``seq`` is the replay cursor.
* An in-memory replay ring retains the last **2000 events / 60 s** (Q12,
  REQ-BE-043) for ``resume`` and ``GET /v3/events``.
* Each live WebSocket registers a :class:`Subscriber` with a bounded queue and a
  topic filter. Backpressure policy (contract §3.5) is enforced here:
  ``pty_output`` coalesces then **drops-with-marker**; ``kanban``/``conductor``/
  ``memory``/``policy`` are **never dropped** — a hopelessly slow consumer is
  flagged for disconnect so the stream layer can close it with ``rate_limited``.

Feature modules never touch WebSockets: they call :meth:`EventBus.publish` and
the bus records + fans out the envelope.
"""

from __future__ import annotations

import asyncio
import collections
import threading
import time
from typing import Any

from . import PROTOCOL_VERSION, REPLAY_MAX_EVENTS, REPLAY_WINDOW_S
from .util import now_iso

#: Mapping of event ``type`` → subscribable topic (contract §3.3 topic set).
TYPE_TOPIC: dict[str, str] = {
    "hello": "session",
    "heartbeat": "session",
    "session_spawned": "session",
    "session_state": "session",
    "pty_output": "pty_output",
    "kanban_updated": "kanban",
    "conductor_state": "conductor",
    "memory_changed": "memory",
    "dry_run_result": "conductor",
    "policy_spawn_decision": "policy",
    "policy_spawn_deferred": "policy",
    "error": "conductor",
}

#: Topics whose events must never be silently dropped (contract §3.5).
NEVER_DROP_TOPICS = frozenset({"kanban", "conductor", "memory", "policy", "session"})

#: All valid subscribe topics.
ALL_TOPICS = frozenset(
    {"session", "pty_output", "kanban", "conductor", "memory", "policy"}
)


def topic_for(event_type: str) -> str:
    """Return the subscribable topic for an event ``type`` (default ``session``)."""
    return TYPE_TOPIC.get(event_type, "session")


class Subscriber:
    """A single WebSocket's bounded delivery queue with a topic filter.

    The stream layer awaits :meth:`get` to drain envelopes to the socket. When
    the queue overflows, :meth:`offer` applies the §3.5 backpressure policy:
    droppable ``pty_output`` is coalesced to a truncation marker; any other topic
    overflow sets :attr:`must_disconnect` so the socket is closed and resynced.
    """

    def __init__(self, maxsize: int = 512, topics: frozenset[str] | None = None) -> None:
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=maxsize)
        self.topics: frozenset[str] = topics if topics is not None else ALL_TOPICS
        self.must_disconnect = False
        self.disconnect_reason: str | None = None
        #: Per-session count of coalesced/dropped pty_output frames pending a marker.
        self._dropped_bytes: dict[str, int] = {}

    def wants(self, event_type: str) -> bool:
        return topic_for(event_type) in self.topics

    def set_topics(self, topics: frozenset[str]) -> None:
        self.topics = topics & ALL_TOPICS

    def offer(self, envelope: dict[str, Any]) -> None:
        """Enqueue ``envelope`` applying backpressure when the queue is full."""
        if not self.wants(envelope.get("type", "")):
            return
        try:
            self._queue.put_nowait(envelope)
            return
        except asyncio.QueueFull:
            pass

        etype = envelope.get("type")
        topic = topic_for(etype or "")
        if topic == "pty_output":
            # Coalesce: drop this chunk, remember its bytes for a marker frame.
            sid = envelope.get("session_id") or "?"
            payload = envelope.get("payload") or {}
            approx = 0
            b = payload.get("bytes")
            if isinstance(b, str):
                # base64 chars → ~3/4 bytes; good enough for a marker estimate.
                approx = (len(b) * 3) // 4
            self._dropped_bytes[sid] = self._dropped_bytes.get(sid, 0) + max(approx, 1)
        else:
            # Never-drop topic overflowed → force a clean resync.
            self.must_disconnect = True
            self.disconnect_reason = "rate_limited"

    def take_drop_markers(self) -> list[dict[str, Any]]:
        """Return synthetic ``pty_output`` marker frames for coalesced drops.

        Called by the stream layer after draining; produces one marker per
        affected session with ``dropped: true`` and the accumulated
        ``dropped_bytes`` so the client can render an "output truncated" break.
        Note: these carry no global ``seq`` (they are connection-local repair
        frames, not part of the replayable stream).
        """
        if not self._dropped_bytes:
            return []
        markers: list[dict[str, Any]] = []
        for sid, nbytes in self._dropped_bytes.items():
            markers.append(
                {
                    "v": PROTOCOL_VERSION,
                    "seq": None,
                    "ts": now_iso(),
                    "type": "pty_output",
                    "session_id": sid,
                    "payload": {
                        "stream_seq": None,
                        "encoding": "base64",
                        "bytes": "",
                        "dropped": True,
                        "dropped_bytes": nbytes,
                    },
                }
            )
        self._dropped_bytes.clear()
        return markers

    async def get(self) -> dict[str, Any]:
        return await self._queue.get()

    def get_nowait(self) -> dict[str, Any]:
        return self._queue.get_nowait()

    def empty(self) -> bool:
        return self._queue.empty()


class EventBus:
    """Global sequencer + replay ring + subscriber fan-out.

    Thread-safe for ``seq`` assignment and ring mutation; fan-out to
    subscribers happens on the event loop (subscribers use asyncio queues).
    ``publish`` is ``async`` for a uniform call site but never blocks on I/O.
    """

    def __init__(
        self,
        *,
        replay_max_events: int = REPLAY_MAX_EVENTS,
        replay_window_s: int = REPLAY_WINDOW_S,
    ) -> None:
        self._lock = threading.Lock()
        self._seq = 0
        self._ring: collections.deque[dict[str, Any]] = collections.deque(maxlen=replay_max_events)
        # Monotonic append-times aligned 1:1 with ``_ring`` (same maxlen → they
        # evict in lockstep). Age-pruning compares these floats instead of
        # re-parsing each envelope's ISO ``ts`` on every publish (hot path).
        self._ring_mono: collections.deque[float] = collections.deque(maxlen=replay_max_events)
        self._replay_window_s = replay_window_s
        self._subscribers: set[Subscriber] = set()

    # -- sequencing / ring -------------------------------------------------
    def current_seq(self) -> int:
        with self._lock:
            return self._seq

    def _next_envelope(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        session_id: str | None,
        task_id: str | None,
        plan_id: str | None,
    ) -> dict[str, Any]:
        with self._lock:
            self._seq += 1
            seq = self._seq
            env: dict[str, Any] = {
                "v": PROTOCOL_VERSION,
                "seq": seq,
                "ts": now_iso(),
                "type": event_type,
                "payload": payload,
            }
            if session_id is not None:
                env["session_id"] = session_id
            if task_id is not None:
                env["task_id"] = task_id
            if plan_id is not None:
                env["plan_id"] = plan_id
            self._ring.append(env)
            self._ring_mono.append(time.monotonic())
            self._prune_locked()
            return env

    def _prune_locked(self) -> None:
        """Drop ring entries older than the replay window (best-effort, lock held).

        The deque already bounds by count (``maxlen``); this additionally bounds
        by age. Timestamps are the monotonic floats captured at append time, so
        this compares numbers rather than importing datetime and parsing an ISO
        ``ts`` on every publish (the hot path shared by all sessions' output).
        """
        horizon = time.monotonic() - self._replay_window_s
        while self._ring_mono and self._ring_mono[0] < horizon:
            self._ring_mono.popleft()
            self._ring.popleft()

    async def publish(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        session_id: str | None = None,
        task_id: str | None = None,
        plan_id: str | None = None,
    ) -> dict[str, Any]:
        """Record an event in the ring and fan it out to all subscribers."""
        env = self._next_envelope(
            event_type, payload, session_id=session_id, task_id=task_id, plan_id=plan_id
        )
        self._fanout(env)
        return env

    def _fanout(self, envelope: dict[str, Any]) -> None:
        for sub in list(self._subscribers):
            sub.offer(envelope)

    # -- replay ------------------------------------------------------------
    def snapshot_since(self, after_seq: int, limit: int = 500) -> tuple[list[dict[str, Any]], bool]:
        """Return buffered events with ``seq > after_seq`` (in order) + truncated flag.

        ``truncated`` is True when ``after_seq`` predates the oldest retained
        event (and is behind the current seq), meaning the caller must do a full
        REST snapshot resync (REQ-ARCH-008).
        """
        with self._lock:
            events = [e for e in self._ring if e["seq"] > after_seq]
            oldest = self._ring[0]["seq"] if self._ring else self._seq
            truncated = after_seq < (oldest - 1) and after_seq < self._seq
        return events[:limit], truncated

    def replay_into(self, sub: Subscriber, after_seq: int) -> bool:
        """Push buffered events with ``seq > after_seq`` into ``sub``.

        Returns the ``truncated`` flag (True → the client should full-resync).
        """
        events, truncated = self.snapshot_since(after_seq, limit=len(self._ring) or 1)
        for env in events:
            sub.offer(env)
        return truncated

    # -- subscriber management --------------------------------------------
    def register(self, topics: frozenset[str] | None = None, maxsize: int = 512) -> Subscriber:
        sub = Subscriber(maxsize=maxsize, topics=topics)
        self._subscribers.add(sub)
        return sub

    def unregister(self, sub: Subscriber) -> None:
        self._subscribers.discard(sub)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)


__all__ = [
    "EventBus",
    "Subscriber",
    "TYPE_TOPIC",
    "ALL_TOPICS",
    "NEVER_DROP_TOPICS",
    "topic_for",
]
