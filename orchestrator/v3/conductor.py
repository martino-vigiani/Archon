"""The Conductor: intent → plan → dry-run → confirm/execute (contract §2.4).

A single Claude routing call (Q31) turns an intent into a structured plan; the
call returns once the plan is assembled. A cheap, instantaneous dry-run estimate
is attached (Q14 — never blocks past 1.5 s; if it cannot be produced in time,
``estimate_ready=false`` and a later ``dry_run_result`` event may deliver it).
Confirm executes the plan's actions through the session/kanban/memory services;
memory edits are only ever *proposed*, never written (Addendum §A3). The
Conductor owns five of the six orb states (``listening`` is client-local) and is
resilient: provider failures surface as typed errors, enter the ``error`` state,
and never touch running terminals (Addendum §A4).
"""

from __future__ import annotations

import time
from typing import Any

from . import DRY_RUN_MAX_S, HARD_CEILING_DEFAULT
from .errors import ApiError
from .events import EventBus
from .ids import new_ulid
from .provider import Provider, ProviderError, ProviderPlan
from .storage import StatePaths

PLAN_TTL_S = 300.0
_IDEMPOTENCY_TTL_S = 600.0


class _StoredPlan:
    def __init__(self, plan: dict[str, Any], expires_at_monotonic: float) -> None:
        self.plan = plan
        self.expires_at_monotonic = expires_at_monotonic
        self.status = "pending"  # pending | executing | partial | cancelled | done


class Conductor:
    """Intent planning + plan execution, with the orb state machine."""

    def __init__(
        self,
        *,
        paths: StatePaths,
        bus: EventBus,
        sessions: Any,
        kanban: Any,
        memory: Any,
        provider: Provider,
        ceiling: int = HARD_CEILING_DEFAULT,
        dry_run_max_s: float = DRY_RUN_MAX_S,
    ) -> None:
        self.paths = paths
        self.bus = bus
        self.sessions = sessions
        self.kanban = kanban
        self.memory = memory
        self.provider = provider
        self.ceiling = ceiling
        self.dry_run_max_s = dry_run_max_s

        self._plans: dict[str, _StoredPlan] = {}
        self._planning_state = "idle"  # idle | thinking | spawning
        self._error_active = False
        self._by_request: dict[str, tuple[float, dict[str, Any]]] = {}
        # Confirm idempotency (contract §1.5): request_id → (monotonic_ts, result).
        # Kept separate from _by_request (which caches *plan* bodies) so a confirm
        # retry replays its execution result rather than re-running the plan.
        self._confirm_by_request: dict[str, tuple[float, dict[str, Any]]] = {}

    # -- orb state ---------------------------------------------------------
    def current_state(self) -> str:
        if self._error_active:
            return "error"
        try:
            if self.sessions is not None and self.sessions.live_count() > 0:
                return "streaming"
        except Exception:  # noqa: BLE001
            pass
        return self._planning_state

    async def _set_state(self, state: str, *, detail: str | None = None, plan_id: str | None = None,
                         intent_id: str | None = None) -> None:
        if state in ("idle", "thinking", "spawning"):
            self._planning_state = state
        self._error_active = state == "error"
        payload: dict[str, Any] = {"state": state}
        if detail is not None:
            payload["detail"] = detail
        if plan_id is not None:
            payload["plan_id"] = plan_id
        if intent_id is not None:
            payload["intent_id"] = intent_id
        await self.bus.publish("conductor_state", payload)

    # -- message → plan ----------------------------------------------------
    async def message(
        self,
        *,
        request_id: str | None = None,
        text: str,
        source: str = "text",
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = context or {}
        if not text or not text.strip():
            raise ApiError("validation_error", "Intent text must be non-empty")

        self._prune_expired()
        # Idempotency (REQ-ARCH-021): same request_id returns the same plan body.
        if request_id:
            cached = self._by_request.get(request_id)
            if cached and (time.monotonic() - cached[0]) < _IDEMPOTENCY_TTL_S:
                return cached[1]

        intent_id = new_ulid()
        await self._set_state("thinking", detail="Planning…", intent_id=intent_id)

        started = time.monotonic()
        try:
            provider_plan = await self.provider.plan(text=text, context=context, ceiling=self.ceiling)
        except ProviderError as exc:
            await self._emit_error("provider_error", str(exc))
            raise ApiError("provider_error", f"Conductor provider failed: {exc}") from exc
        except Exception as exc:  # noqa: BLE001 - unexpected provider fault
            await self._emit_error("orchestrator_error", str(exc))
            raise ApiError("orchestrator_error", f"Conductor failed: {exc}") from exc

        applied_cap = _opt_int(context.get("cap"))
        plan = self._assemble_plan(provider_plan, applied_cap)
        dry_run = self._dry_run(provider_plan, plan, elapsed=time.monotonic() - started)

        stored = _StoredPlan(plan, time.monotonic() + PLAN_TTL_S)
        self._plans[plan["plan_id"]] = stored
        expires_at = _iso_in(PLAN_TTL_S)

        await self._set_state(
            "thinking",
            detail=f"Planned {plan['final_count']} session(s): {plan['summary']}",
            plan_id=plan["plan_id"],
            intent_id=intent_id,
        )

        body = {"intent_id": intent_id, "plan": plan, "dry_run": dry_run, "expires_at": expires_at}
        if request_id:
            self._by_request[request_id] = (time.monotonic(), body)
        return body

    def _assemble_plan(self, pp: ProviderPlan, applied_cap: int | None) -> dict[str, Any]:
        proposed = max(1, int(pp.proposed_session_count))
        cap = applied_cap
        limit = self.ceiling if cap is None else min(cap, self.ceiling)
        final = min(proposed, limit)
        reduction_reason: str | None = None
        if final < proposed:
            reduction_reason = "user_cap" if (cap is not None and cap < proposed and cap <= self.ceiling) else "ceiling"

        actions: list[dict[str, Any]] = []
        spawn_seen = 0
        for a in pp.actions:
            kind = a.get("kind")
            if kind not in _ACTION_KINDS:
                continue
            action = dict(a)
            action["action_id"] = new_ulid()
            action.setdefault("destructive", kind in ("kill_session", "delete_card"))
            # Clamp the number of spawn_session actions to the final count.
            if kind == "spawn_session":
                spawn_seen += 1
                if spawn_seen > final:
                    continue
            actions.append(action)

        return {
            "plan_id": new_ulid(),
            "summary": pp.summary,
            "proposed_session_count": proposed,
            "applied_cap": cap,
            "ceiling": self.ceiling,
            "final_count": final,
            "reduction_reason": reduction_reason,
            "actions": actions,
        }

    def _dry_run(self, pp: ProviderPlan, plan: dict[str, Any], *, elapsed: float) -> dict[str, Any]:
        # The estimate is cheap/instant; if plan assembly already blew the budget
        # we still return (estimate_ready reflects whether figures are present).
        ready = elapsed <= self.dry_run_max_s and pp.estimated_tokens is not None
        warnings = list(pp.warnings)
        cap = plan["applied_cap"]
        if cap is not None and plan["proposed_session_count"] > cap:
            warnings.append(
                f"Conductor estimates {plan['proposed_session_count']} terminals needed; cap is {cap}"
            )
        if not ready:
            return {
                "estimate_ready": False,
                "estimated_session_count": None,
                "estimated_tokens": None,
                "estimated_duration_s": None,
                "warnings": warnings,
            }
        return {
            "estimate_ready": True,
            "estimated_session_count": plan["final_count"],
            "estimated_tokens": pp.estimated_tokens,
            "estimated_duration_s": pp.estimated_duration_s,
            "warnings": warnings,
        }

    # -- confirm → execute -------------------------------------------------
    async def confirm(
        self,
        plan_id: str,
        *,
        request_id: str | None = None,
        cap: int | None = None,
        auto_apply: bool = False,
    ) -> dict[str, Any]:
        # Idempotent replay (contract §1.5): the Swift APIClient marks confirmPlan
        # idempotent and auto-retries on transient 5xx/timeout. A completed confirm
        # for this request_id returns its ORIGINAL result — never a second
        # execution — even if the plan has since expired and been pruned. Checked
        # before the plan lookup below so a still-present expired plan yields
        # ``plan_expired`` (contract 410) rather than being pruned to ``not_found``.
        if request_id:
            cached = self._confirm_by_request.get(request_id)
            if cached and (time.monotonic() - cached[0]) < _IDEMPOTENCY_TTL_S:
                return cached[1]

        stored = self._plans.get(plan_id)
        if stored is None:
            raise ApiError("not_found", "Unknown plan", details={"plan_id": plan_id})
        if time.monotonic() > stored.expires_at_monotonic:
            raise ApiError("plan_expired", "Plan TTL elapsed before confirm", details={"plan_id": plan_id})
        if stored.status == "cancelled":
            raise ApiError("plan_expired", "Plan was cancelled", details={"plan_id": plan_id})
        # A plan executes at most once. A re-confirm with a *different* (or no)
        # request_id after the plan is already executing/executed is refused so a
        # retried/duplicated call can never spawn duplicate agent terminals or
        # cards (the same-request_id retry is handled by the cache above).
        if stored.status in ("executing", "partial", "done"):
            raise ApiError(
                "plan_already_confirmed",
                "Plan has already been confirmed",
                details={"plan_id": plan_id, "status": stored.status},
            )

        plan = stored.plan
        effective_cap = cap if cap is not None else plan["applied_cap"]
        limit = self.ceiling if effective_cap is None else min(effective_cap, self.ceiling)

        # Claim the plan synchronously — no await between the guard above and this
        # write — so two concurrent confirms cannot both pass the guard and run.
        stored.status = "executing"
        await self._set_state("spawning", detail="Executing plan", plan_id=plan_id)

        created_session_ids: list[str] = []
        created_card_ids: list[str] = []
        slug_to_card: dict[str, str] = {}
        action_results: list[dict[str, Any]] = []
        spawned = 0

        for action in plan["actions"]:
            aid = action.get("action_id")
            kind = action.get("kind")
            try:
                if kind == "create_card":
                    res = await self.kanban.create_card(
                        title=action.get("title", "Untitled"),
                        body=action.get("body", ""),
                        column=action.get("column", "queued"),
                        priority=action.get("priority", "normal"),
                        provenance="conductor",
                    )
                    cid = res["card"]["card_id"]
                    created_card_ids.append(cid)
                    ref = action.get("card_ref")
                    if isinstance(ref, str) and ref.startswith("new:"):
                        slug_to_card[ref[4:]] = cid
                    action_results.append({"action_id": aid, "ok": True})
                elif kind == "spawn_session":
                    if spawned >= limit:
                        action_results.append({"action_id": aid, "ok": False, "error": "cap_exceeded"})
                        continue
                    card_id = _resolve_card_ref(action.get("card_ref"), slug_to_card)
                    status_code, payload = await self.sessions.spawn(
                        cwd=action.get("cwd"),
                        card_id=card_id,
                        initiator="conductor",
                        prompt=action.get("prompt"),
                        cap=limit,
                    )
                    if status_code == 201:
                        sid = payload["session"]["session_id"]
                        created_session_ids.append(sid)
                        spawned += 1
                        if card_id:
                            await _safe_bind(self.kanban, card_id, sid)
                    action_results.append({"action_id": aid, "ok": status_code in (201, 202)})
                elif kind == "move_card":
                    await self.kanban.move_card(
                        action["card_id"],
                        to_column=action.get("to_column", "in_progress"),
                        to_ordinal=action.get("to_ordinal"),
                        provenance="conductor",
                    )
                    action_results.append({"action_id": aid, "ok": True})
                elif kind == "update_card":
                    await self.kanban.update_card(
                        action["card_id"], provenance="conductor",
                        title=action.get("title"), body=action.get("body"),
                        priority=action.get("priority"), status=action.get("status"),
                    )
                    action_results.append({"action_id": aid, "ok": True})
                elif kind == "delete_card":
                    await self.kanban.delete_card(action["card_id"], provenance="conductor")
                    action_results.append({"action_id": aid, "ok": True})
                elif kind == "kill_session":
                    await self.sessions.kill(action["session_id"])
                    action_results.append({"action_id": aid, "ok": True})
                elif kind == "propose_memory_edit":
                    # NEVER writes — surfaced as a proposal only (Addendum §A3).
                    action_results.append({"action_id": aid, "ok": True, "proposal": True})
                else:
                    action_results.append({"action_id": aid, "ok": False, "error": "unknown_kind"})
            except ApiError as exc:
                action_results.append({"action_id": aid, "ok": False, "error": exc.code})
            except Exception as exc:  # noqa: BLE001
                action_results.append({"action_id": aid, "ok": False, "error": str(exc)})

        any_failed = any(not r["ok"] for r in action_results)
        status = "partial" if any_failed else "executing"
        stored.status = "partial" if any_failed else "done"

        if created_session_ids:
            await self._set_state("streaming", detail="Sessions running", plan_id=plan_id)
        else:
            await self._set_state("idle", plan_id=plan_id)

        result: dict[str, Any] = {
            "plan_id": plan_id,
            "status": status,
            "created_session_ids": created_session_ids,
            "created_card_ids": created_card_ids,
            "applied_cap": effective_cap,
            "final_count": len(created_session_ids),
        }
        if any_failed:
            result["action_results"] = action_results
        if request_id:
            self._confirm_by_request[request_id] = (time.monotonic(), result)
        return result

    def _prune_expired(self) -> None:
        """Reclaim expired plans and stale idempotency records (bounded growth).

        TTLs remain authoritative on access; this only drops entries that can no
        longer be returned, so the in-memory maps don't grow unboundedly across
        an all-day session. A confirmed plan's result survives in
        ``_confirm_by_request`` for the full idempotency window even after the
        plan itself is pruned.
        """
        now = time.monotonic()
        # Keep expired plans for the idempotency window past their TTL so a confirm
        # shortly after expiry still returns ``plan_expired`` (410) rather than
        # ``not_found`` (404); only then reclaim them.
        for pid in [p for p, sp in self._plans.items()
                    if now > sp.expires_at_monotonic + _IDEMPOTENCY_TTL_S]:
            del self._plans[pid]
        for rid in [r for r, (ts, _b) in self._by_request.items() if now - ts >= _IDEMPOTENCY_TTL_S]:
            del self._by_request[rid]
        for rid in [r for r, (ts, _r) in self._confirm_by_request.items() if now - ts >= _IDEMPOTENCY_TTL_S]:
            del self._confirm_by_request[rid]

    async def cancel(self, plan_id: str) -> dict[str, Any]:
        stored = self._plans.get(plan_id)
        if stored is None:
            raise ApiError("not_found", "Unknown plan", details={"plan_id": plan_id})
        stored.status = "cancelled"
        await self._set_state("idle", detail="Planning cancelled", plan_id=plan_id)
        return {"plan_id": plan_id, "status": "cancelled"}

    async def shutdown(self) -> None:
        self._plans.clear()
        self._by_request.clear()
        self._confirm_by_request.clear()

    async def _emit_error(self, code: str, message: str) -> None:
        await self._set_state("error", detail=message)
        await self.bus.publish(
            "error",
            {"error": {"code": code, "message": message, "retriable": True, "details": {}}},
        )


_ACTION_KINDS = frozenset(
    {"spawn_session", "create_card", "update_card", "move_card", "delete_card", "kill_session", "propose_memory_edit"}
)


def _resolve_card_ref(ref: Any, slug_to_card: dict[str, str]) -> str | None:
    if not isinstance(ref, str):
        return None
    if ref.startswith("new:"):
        return slug_to_card.get(ref[4:])
    return ref  # an existing card_id


async def _safe_bind(kanban: Any, card_id: str, session_id: str) -> None:
    bind = getattr(kanban, "bind_session", None)
    if bind is not None:
        try:
            await bind(card_id, session_id, status="running")
        except Exception:  # noqa: BLE001
            pass


def _opt_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _iso_in(seconds: float) -> str:
    from datetime import datetime, timedelta, timezone

    return (
        (datetime.now(timezone.utc) + timedelta(seconds=seconds))
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


__all__ = ["Conductor", "PLAN_TTL_S"]
