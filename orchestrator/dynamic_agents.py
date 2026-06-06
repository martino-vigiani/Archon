"""
Dynamic agents: derive a task-shaped roster of workers instead of the fixed
T1..T5 personalities.

The legacy model hardcodes five named personalities (Craftsman, Architect, Narrator,
Strategist, Skeptic). This module derives a *dynamic* roster from the actual goal:
each worker gets an opaque id (``w1``, ``w2``, ...), a ``focus`` synthesized from what
the goal needs, a relevant subset of the local subagent pool, and an
:class:`~orchestrator.execution.ExecutionProfile` (model tier + effort) matched to the
kind of work — with no fixed name or personality.

Token note: each worker's curated subagent set is referenced *by name* in its system
prompt (the ``claude`` CLI auto-discovers ``.claude/agents/*.md`` lazily, which is
cheap). Full agent bodies are NOT dumped via ``--agents`` on every task — that would
re-send entire prompts each call. ``--agents`` JSON is reserved for genuinely ad-hoc
agents the orchestrator defines on the fly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .execution import (
    Effort,
    ExecutionProfile,
    TaskKind,
    profile_for_kind,
)


# A "capability lane" is a slice of work a worker can own. Lanes are derived from the
# goal text; the roster size flexes with what the goal actually needs (1..N), unlike
# the fixed five. Each lane maps to a TaskKind (for tiering) + subagent affinity.
@dataclass(frozen=True)
class Lane:
    key: str
    kind: TaskKind
    focus: str
    keywords: tuple[str, ...]
    subagent_affinity: tuple[str, ...]  # substrings matched against pool agent names


# Ordered by priority — earlier lanes are preferred when capping the roster size.
LANES: tuple[Lane, ...] = (
    Lane(
        key="architecture",
        kind=TaskKind.ARCHITECTURE,
        focus="system architecture, data model, performance and reliability",
        keywords=(
            "architecture",
            "backend",
            "database",
            "schema",
            "api",
            "performance",
            "scalab",
            "concurrency",
            "migration",
            "infrastructure",
            "auth",
            "security",
        ),
        subagent_affinity=("architect", "database", "swiftdata", "node", "python", "ml-engineer"),
    ),
    Lane(
        key="ui",
        kind=TaskKind.UI,
        focus="user interface and interaction design",
        keywords=(
            "ui",
            "ux",
            "interface",
            "view",
            "screen",
            "component",
            "design",
            "css",
            "tailwind",
            "swiftui",
            "react",
            "animation",
            "theme",
            "responsive",
            "layout",
        ),
        subagent_affinity=("crafter", "stylist", "design-system", "web-ui", "dashboard"),
    ),
    Lane(
        key="code",
        kind=TaskKind.CODE,
        focus="feature implementation and integration",
        keywords=(
            "implement",
            "feature",
            "function",
            "logic",
            "endpoint",
            "service",
            "fix",
            "integrate",
            "wire",
            "build",
        ),
        subagent_affinity=("architect", "toolsmith", "database"),
    ),
    Lane(
        key="qa",
        kind=TaskKind.QA,
        focus="testing, verification and quality gates",
        keywords=("test", "qa", "verify", "validate", "lint", "coverage", "regression"),
        subagent_affinity=("test", "architect"),
    ),
    Lane(
        key="docs",
        kind=TaskKind.DOCS,
        focus="documentation and developer enablement",
        keywords=("doc", "readme", "guide", "tutorial", "changelog", "comment", "onboarding"),
        subagent_affinity=("tech-writer", "marketing"),
    ),
    Lane(
        key="strategy",
        kind=TaskKind.STRATEGY,
        focus="product strategy, scope and monetization",
        keywords=(
            "strategy",
            "roadmap",
            "mvp",
            "pricing",
            "monetiz",
            "market",
            "feature priority",
            "product",
            "research",
        ),
        subagent_affinity=("product-thinker", "monetization", "marketing", "prompt-craftsman"),
    ),
)


@dataclass
class AgentSpec:
    """A dynamically derived worker. No fixed personality — identity is its capability."""

    id: str  # opaque, e.g. "w1"
    lane: str  # capability lane key
    kind: TaskKind
    focus: str
    subagents: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    profile: ExecutionProfile = field(default_factory=ExecutionProfile)

    def system_prompt(self) -> str:
        """Synthesize a concise, role-free persona for this worker.

        Kept short on purpose (token efficiency); it states the focus, the preferred
        subagents by name (auto-discovered), and the execution posture.
        """
        subs = ", ".join(self.subagents) if self.subagents else "any relevant subagent"
        effort = self.profile.effort.value if self.profile.effort is not Effort.INHERIT else "high"
        return (
            f"You are worker {self.id}, a dynamic agent focused on: {self.focus}.\n"
            f"You have no fixed role — own whatever advances the goal in your focus area, "
            f"and coordinate with other workers via the shared .orchestra state.\n"
            f"Preferred subagents (delegate to them via the Task tool when they fit): {subs}.\n"
            f"When you delegate to a subagent, name it explicitly in your summary "
            f"(e.g. 'delegated to python-architect') so the orchestrator can track it.\n"
            f"Work at {effort} effort. Be concise; do not restate context. "
            f"Return a short structured summary of artifacts, what you provide to others, "
            f"and what you need from others."
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "lane": self.lane,
            "kind": self.kind.value,
            "focus": self.focus,
            "subagents": list(self.subagents),
            "keywords": list(self.keywords),
            "profile": self.profile.to_dict(),
            "mode_badge": self.profile.badge(),
        }


def _select_subagents(lane: Lane, available: list[str], limit: int = 4) -> list[str]:
    """Pick the pool subagents most relevant to a lane (by name substring affinity)."""
    chosen: list[str] = []
    for affinity in lane.subagent_affinity:
        for name in available:
            if affinity in name and name not in chosen:
                chosen.append(name)
                if len(chosen) >= limit:
                    return chosen
    return chosen


def derive_agents(
    goal: str,
    *,
    available_subagents: list[str] | None = None,
    max_agents: int = 5,
    include_testing: bool = True,
    tiering: bool = True,
) -> list[AgentSpec]:
    """Derive a dynamic worker roster from the goal.

    Lanes present in the goal text become workers; ``code`` is always included as the
    implementation backbone, and ``qa`` is included (unless ``include_testing`` is
    False) so quality is owned. The roster is capped at ``max_agents`` by lane
    priority. Each worker gets a tiered :class:`ExecutionProfile`.
    """
    available = available_subagents or []
    text = goal.lower()

    present: list[Lane] = []
    for lane in LANES:
        hit = any(kw in text for kw in lane.keywords)
        if lane.key == "code":
            hit = True  # implementation backbone is always present
        if lane.key == "qa" and include_testing:
            hit = True
        if lane.key == "qa" and not include_testing:
            hit = False
        if hit:
            present.append(lane)

    if not present:  # pathological: nothing matched — at least give a code worker
        present = [next(lane for lane in LANES if lane.key == "code")]

    # Cap the roster, but RESERVE slots for the forced backbone lanes (code, and qa when
    # testing is on) so a small max_agents can never slice them out — while preserving
    # the original priority order of whatever survives.
    forced_keys = {"code"} | ({"qa"} if include_testing else set())
    forced = [lane for lane in present if lane.key in forced_keys]
    others = [lane for lane in present if lane.key not in forced_keys]
    keep_forced = forced[:max_agents]
    keep_others = others[: max(0, max_agents - len(keep_forced))]
    kept_ids = {id(lane) for lane in keep_forced} | {id(lane) for lane in keep_others}
    present = [lane for lane in present if id(lane) in kept_ids]

    roster: list[AgentSpec] = []
    for i, lane in enumerate(present, start=1):
        profile = profile_for_kind(lane.kind, tiering=tiering)
        # Architecture/QA do a longer, deeper run; give them more headroom.
        if lane.kind in (TaskKind.ARCHITECTURE, TaskKind.QA):
            profile = profile.merged(timeout=900.0)
        roster.append(
            AgentSpec(
                id=f"w{i}",
                lane=lane.key,
                kind=lane.kind,
                focus=lane.focus,
                subagents=_select_subagents(lane, available),
                keywords=list(lane.keywords),
                profile=profile,
            )
        )
    return roster


def route_to_agent(task_text: str, roster: list[AgentSpec], default_id: str | None = None) -> str:
    """Route a task to the best-matching dynamic worker by keyword score.

    Falls back to ``default_id`` (or the first worker) when nothing scores.
    """
    text = task_text.lower()
    best_id = default_id or (roster[0].id if roster else "w1")
    best_score = 0
    for spec in roster:
        score = sum(1 for kw in spec.keywords if kw in text)
        if score > best_score:
            best_score = score
            best_id = spec.id
    return best_id


def build_adhoc_agents_json(specs: list[dict[str, str]]) -> dict[str, Any]:
    """Build a ``--agents`` JSON object for genuinely ad-hoc agents.

    Each spec is ``{"name", "description", "prompt"}``. Use sparingly — embedding full
    prompts inflates every CLI call; prefer auto-discovered project subagents by name.
    """
    out: dict[str, Any] = {}
    for s in specs:
        name = s["name"]
        out[name] = {
            "description": s.get("description", ""),
            "prompt": s.get("prompt", ""),
        }
    return out
