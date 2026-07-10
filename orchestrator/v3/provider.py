"""Conductor provider: the Claude routing call (key stays server-side only).

The provider turns an intent into a structured :class:`ProviderPlan`. Two
implementations:

* :class:`HttpxClaudeProvider` — real Anthropic Messages API call over httpx,
  with retry/backoff on ``429``/``5xx``/network (Addendum §A4). The key is read
  from the environment or a ``0600`` file and NEVER returned to any client
  (REQ-BE-060/062). The ``anthropic`` SDK is intentionally not a dependency.
* :class:`FallbackProvider` — a deterministic, offline heuristic that always
  yields a valid plan so the Conductor endpoint works (and is testable) with no
  key/network. It reports ``ready = False`` (no real provider).

:func:`make_default_provider` picks the real provider when a key is configured,
else the fallback.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import random
import re
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from .storage import StatePaths

DEFAULT_MODEL = os.environ.get("ARCHON_V3_CONDUCTOR_MODEL", "claude-sonnet-4-5")
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

_PLAN_SYSTEM = (
    "You are the Archon Conductor. Given a developer's intent for a single local "
    "project, produce a concise routing plan as STRICT JSON with keys: "
    "summary (string), proposed_session_count (int >= 1), "
    "actions (array of objects with keys kind, and kind-specific fields), and "
    "optionally estimated_tokens (int) and estimated_duration_s (int). "
    "Valid action kinds: spawn_session {cwd, prompt, card_ref, rationale}, "
    "create_card {column, title, priority}, update_card {card_id, ...}, "
    "move_card {card_id, to_column}, delete_card {card_id}, kill_session {session_id}, "
    "propose_memory_edit {scope_dir, filename, proposed_content}. "
    "Never write files; memory edits are proposals only. Return ONLY the JSON object."
)


class ProviderError(Exception):
    """Raised when the upstream provider fails after retries (→ ``provider_error``)."""


@dataclass
class ProviderPlan:
    """Structured routing plan returned by a provider."""

    summary: str
    proposed_session_count: int
    actions: list[dict[str, Any]]
    estimated_tokens: int | None = None
    estimated_duration_s: int | None = None
    warnings: list[str] = field(default_factory=list)


@runtime_checkable
class Provider(Protocol):
    ready: bool

    async def plan(self, *, text: str, context: dict[str, Any], ceiling: int) -> ProviderPlan:
        ...


def _read_key(paths: StatePaths | None) -> str | None:
    key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ARCHON_V3_PROVIDER_KEY")
    if key:
        return key.strip()
    key_file = os.environ.get("ARCHON_V3_PROVIDER_KEY_FILE")
    if key_file and Path(key_file).is_file():
        p = Path(key_file)
        st = p.stat()
        # Refuse a group/world-readable key file (parallels runtime.json).
        if st.st_mode & (stat.S_IRGRP | stat.S_IROTH):
            return None
        with contextlib.suppress(OSError):
            return p.read_text(encoding="utf-8").strip()
    return None


class FallbackProvider:
    """Offline heuristic planner — always returns a valid single-session plan."""

    ready = False

    async def plan(self, *, text: str, context: dict[str, Any], ceiling: int) -> ProviderPlan:
        active_dir = context.get("active_dir")
        slug = _slug(text) or "task"
        actions: list[dict[str, Any]] = [
            {
                "kind": "create_card",
                "column": "in_progress",
                "title": _title(text),
                "priority": "normal",
                "card_ref": f"new:{slug}",
            },
            {
                "kind": "spawn_session",
                "cwd": active_dir,
                "prompt": text,
                "card_ref": f"new:{slug}",
                "rationale": "Primary work for the stated intent.",
            },
        ]
        est_tokens = min(200_000, 4000 + len(text) * 8)
        return ProviderPlan(
            summary=f"One terminal for: {_title(text)}",
            proposed_session_count=1,
            actions=actions,
            estimated_tokens=est_tokens,
            estimated_duration_s=180,
            warnings=[],
        )


class HttpxClaudeProvider:
    """Real Anthropic Messages API planner (server-side key, retry/backoff)."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = DEFAULT_MODEL,
        max_retries: int = 3,
        timeout_s: float = 30.0,
    ) -> None:
        self._api_key = api_key
        self.model = model
        self.max_retries = max_retries
        self.timeout_s = timeout_s
        self.ready = True
        self._fallback = FallbackProvider()

    async def plan(self, *, text: str, context: dict[str, Any], ceiling: int) -> ProviderPlan:
        import httpx

        user = (
            f"Intent: {text}\n"
            f"Active directory: {context.get('active_dir')}\n"
            f"Selected card: {context.get('selected_card_id')}\n"
            f"Concurrency ceiling: {ceiling}\n"
            "Return the JSON plan now."
        )
        body = {
            "model": self.model,
            "max_tokens": 1500,
            "system": _PLAN_SYSTEM,
            "messages": [{"role": "user", "content": user}],
        }
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                    resp = await client.post(ANTHROPIC_URL, headers=headers, json=body)
                if resp.status_code == 429 or resp.status_code >= 500:
                    last_exc = ProviderError(f"HTTP {resp.status_code}")
                    await self._backoff(attempt)
                    continue
                if resp.status_code >= 400:
                    raise ProviderError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                return self._parse(resp.json(), text, context)
            except (ProviderError,) as exc:
                last_exc = exc
                await self._backoff(attempt)
            except Exception as exc:  # noqa: BLE001 - network/timeouts are retriable
                last_exc = exc
                await self._backoff(attempt)
        raise ProviderError(f"Provider failed after {self.max_retries} attempts: {last_exc}")

    async def _backoff(self, attempt: int) -> None:
        delay = min(8.0, (2 ** (attempt - 1)) * 0.5) + random.uniform(0, 0.25)
        await asyncio.sleep(delay)

    def _parse(self, data: dict[str, Any], text: str, context: dict[str, Any]) -> ProviderPlan:
        blocks = data.get("content") or []
        raw = ""
        for b in blocks:
            if isinstance(b, dict) and b.get("type") == "text":
                raw += b.get("text", "")
        obj = _extract_json(raw)
        if not obj:
            # Provider returned unparsable content → degrade to a valid plan.
            return self._fallback_sync(text, context)
        actions = obj.get("actions")
        if not isinstance(actions, list) or not actions:
            return self._fallback_sync(text, context)
        return ProviderPlan(
            summary=str(obj.get("summary", _title(text))),
            proposed_session_count=max(1, int(obj.get("proposed_session_count", 1))),
            actions=[a for a in actions if isinstance(a, dict)],
            estimated_tokens=_opt_int(obj.get("estimated_tokens")),
            estimated_duration_s=_opt_int(obj.get("estimated_duration_s")),
            warnings=[str(w) for w in obj.get("warnings", []) if w],
        )

    def _fallback_sync(self, text: str, context: dict[str, Any]) -> ProviderPlan:
        slug = _slug(text) or "task"
        return ProviderPlan(
            summary=f"One terminal for: {_title(text)}",
            proposed_session_count=1,
            actions=[
                {"kind": "create_card", "column": "in_progress", "title": _title(text),
                 "priority": "normal", "card_ref": f"new:{slug}"},
                {"kind": "spawn_session", "cwd": context.get("active_dir"), "prompt": text,
                 "card_ref": f"new:{slug}", "rationale": "Primary work."},
            ],
            estimated_tokens=8000,
            estimated_duration_s=180,
            warnings=["conductor returned unstructured output; used a default plan"],
        )


def make_default_provider(paths: StatePaths | None = None) -> Provider:
    """Return the real provider when a key is configured, else the fallback."""
    key = _read_key(paths)
    if key:
        return HttpxClaudeProvider(api_key=key)
    return FallbackProvider()


# -- small helpers ---------------------------------------------------------
def _extract_json(raw: str) -> dict[str, Any] | None:
    raw = raw.strip()
    with contextlib.suppress(json.JSONDecodeError, ValueError):
        return json.loads(raw)
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        with contextlib.suppress(json.JSONDecodeError, ValueError):
            return json.loads(match.group(0))
    return None


def _opt_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _title(text: str) -> str:
    t = " ".join(text.strip().split())
    return (t[:77] + "...") if len(t) > 80 else (t or "Untitled task")


def _slug(text: str) -> str:
    words = re.sub(r"[^a-z0-9\s-]", "", text.lower()).split()
    return "-".join(words[:4])[:40]


__all__ = [
    "Provider",
    "ProviderPlan",
    "ProviderError",
    "HttpxClaudeProvider",
    "FallbackProvider",
    "make_default_provider",
    "DEFAULT_MODEL",
]
