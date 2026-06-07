"""
Execution profiles: the per-task "human modes" the orchestrator can switch.

Each task is realized as a single non-interactive ``claude --print`` (or
``codex exec``) subprocess. In an interactive Claude Code session a human toggles
things by hand: which model to use, the effort/reasoning level (e.g. ``ultracode``),
plan mode, which subagents/agents are available, which tools are allowed, and
token/RAM-saving flags. ``ExecutionProfile`` bundles all of those switches into one
data object so the orchestrator can flip them per task. ``Config.build_llm_command``
is the single place that composes a profile into concrete CLI flags.

Design goals:
- **Mode switching**: model tier, effort, permission/plan mode, dynamic ``--agents``,
  tool allow/deny — all selectable per task.
- **Token + RAM efficiency**: cheap model tiers for cheap work, ``--bare`` to skip
  hooks/LSP/auto-memory/CLAUDE.md discovery, prompt-cache friendly flags, and a
  cacheable system prompt instead of re-sending it inline every task.
- **No fixed roles**: profiles are derived from the *kind* of work, not from a fixed
  T1..T5 personality.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any


class ModelTier(str, Enum):
    """Semantic model tiers, mapped to concrete model aliases at command-build time.

    Using tiers (not raw model ids) keeps token policy declarative: cheap work runs
    on a fast/cheap model, deep reasoning reserves the strongest model.
    """

    CHEAP = "cheap"  # fast, low token cost — docs, parsing, chat, routing
    STANDARD = "standard"  # balanced — most UI/code work
    DEEP = "deep"  # strongest reasoning — architecture, QA, hard problems
    INHERIT = "inherit"  # fall back to Config.llm_model / CLI default


# Tier -> CLI ``--model`` alias. The Claude CLI resolves these short aliases.
MODEL_TIER_ALIAS: dict[ModelTier, str] = {
    ModelTier.CHEAP: "haiku",
    ModelTier.STANDARD: "sonnet",
    ModelTier.DEEP: "opus",
}


class Effort(str, Enum):
    """Reasoning effort dial — maps to ``claude --effort``.

    ``MAX`` is the "ultracode"-grade setting; ``LOW``/``MEDIUM`` save reasoning tokens
    on mechanical work.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"
    MAX = "max"
    INHERIT = "inherit"


class PermissionMode(str, Enum):
    """Maps to ``claude --permission-mode``.

    ``PLAN`` makes the subprocess produce a plan instead of editing files — used for a
    plan-first pass on risky/architectural work. ``BYPASS`` is the autonomous default
    for worker runs (equivalent to ``--dangerously-skip-permissions``).
    """

    DEFAULT = "default"
    PLAN = "plan"
    ACCEPT_EDITS = "acceptEdits"
    DONT_ASK = "dontAsk"
    BYPASS = "bypassPermissions"


class TaskKind(str, Enum):
    """The kind of work, used to derive a sensible default profile (model tier +
    effort) without any fixed personality."""

    DOCS = "docs"
    STRATEGY = "strategy"
    UI = "ui"
    CODE = "code"
    ARCHITECTURE = "architecture"
    QA = "qa"
    PLANNING = "planning"
    PARSE = "parse"  # internal: structured-output extraction (utility call)
    CHAT = "chat"  # internal: manager-chat Q&A
    GENERIC = "generic"


@dataclass
class ExecutionProfile:
    """A bundle of switchable per-task execution modes.

    All fields default to "inherit"/off so an empty profile reproduces the legacy
    behavior (``Config.build_llm_command`` with no profile).
    """

    model_tier: ModelTier = ModelTier.INHERIT
    model_override: str | None = None  # explicit model id, wins over tier
    effort: Effort = Effort.INHERIT
    permission_mode: PermissionMode = PermissionMode.BYPASS
    agents: dict[str, Any] | None = None  # dynamic --agents JSON (subagent defs)
    append_system_prompt: str | None = None
    allowed_tools: list[str] = field(default_factory=list)
    disallowed_tools: list[str] = field(default_factory=list)
    add_dirs: list[str] = field(default_factory=list)
    bare: bool = False  # --bare: skip hooks/LSP/auto-memory/CLAUDE.md (RAM+token saver)
    cache_friendly: bool = False  # --exclude-dynamic-system-prompt-sections
    max_turns: int | None = None
    fallback_model: str | None = None
    timeout: float | None = None  # per-task timeout override (seconds)

    # ---- serialization -----------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        """Serialize for status snapshots / persistence (enum values as strings)."""
        return {
            "model_tier": self.model_tier.value,
            "model_override": self.model_override,
            "effort": self.effort.value,
            "permission_mode": self.permission_mode.value,
            "agents": self.agents,
            "append_system_prompt": self.append_system_prompt,
            "allowed_tools": list(self.allowed_tools),
            "disallowed_tools": list(self.disallowed_tools),
            "add_dirs": list(self.add_dirs),
            "bare": self.bare,
            "cache_friendly": self.cache_friendly,
            "max_turns": self.max_turns,
            "fallback_model": self.fallback_model,
            "timeout": self.timeout,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ExecutionProfile:
        """Rebuild from a dict (tolerant of missing/extra keys, and of non-dict input
        arriving from the file-based control channel)."""
        if not isinstance(data, dict):
            return cls()

        def _enum(enum_cls, value, default):
            if value is None:
                return default
            try:
                return enum_cls(value)
            except ValueError:
                return default

        return cls(
            model_tier=_enum(ModelTier, data.get("model_tier"), ModelTier.INHERIT),
            model_override=data.get("model_override"),
            effort=_enum(Effort, data.get("effort"), Effort.INHERIT),
            permission_mode=_enum(
                PermissionMode, data.get("permission_mode"), PermissionMode.BYPASS
            ),
            agents=data.get("agents"),
            append_system_prompt=data.get("append_system_prompt"),
            allowed_tools=list(data.get("allowed_tools") or []),
            disallowed_tools=list(data.get("disallowed_tools") or []),
            add_dirs=list(data.get("add_dirs") or []),
            bare=bool(data.get("bare", False)),
            cache_friendly=bool(data.get("cache_friendly", False)),
            max_turns=data.get("max_turns"),
            fallback_model=data.get("fallback_model"),
            timeout=data.get("timeout"),
        )

    # ---- helpers -----------------------------------------------------------
    def resolved_model(self, default: str | None = None) -> str | None:
        """Return the concrete ``--model`` value, or None to inherit the CLI default."""
        if self.model_override:
            return self.model_override
        if self.model_tier is ModelTier.INHERIT:
            return default
        return MODEL_TIER_ALIAS.get(self.model_tier, default)

    def merged(self, **overrides: Any) -> ExecutionProfile:
        """Return a copy with the given fields overridden (immutable-style update)."""
        return replace(self, **overrides)

    def badge(self) -> str:
        """Compact one-line summary for the dashboard, e.g. ``opus·max·plan·3 agents``."""
        parts: list[str] = []
        model = self.model_override or (
            self.model_tier.value if self.model_tier is not ModelTier.INHERIT else None
        )
        if model:
            parts.append(model)
        if self.effort is not Effort.INHERIT:
            parts.append(self.effort.value)
        if self.permission_mode is PermissionMode.PLAN:
            parts.append("plan")
        if self.agents:
            n = len(self.agents)
            parts.append(f"{n} agent{'s' if n != 1 else ''}")
        if self.bare:
            parts.append("bare")
        return " · ".join(parts) if parts else "default"


# ---------------------------------------------------------------------------
# Task classification + tiering policy (local, no LLM, zero token cost)
# ---------------------------------------------------------------------------

# Keyword -> TaskKind. Ordered roughly by specificity; first strong hit wins.
_KIND_KEYWORDS: dict[TaskKind, tuple[str, ...]] = {
    TaskKind.QA: ("test", "qa", "verify", "validate", "lint", "compile", "build pass", "coverage"),
    TaskKind.ARCHITECTURE: (
        "architecture",
        "refactor",
        "schema",
        "data model",
        "migration",
        "system design",
        "scalab",
        "concurrency",
        "performance",
        "infrastructure",
    ),
    TaskKind.DOCS: ("doc", "readme", "guide", "tutorial", "changelog", "comment", "explain"),
    TaskKind.STRATEGY: (
        "strategy",
        "roadmap",
        "mvp",
        "pricing",
        "monetiz",
        "market",
        "competitor",
        "ideation",
        "product vision",
        "user story",
    ),
    TaskKind.UI: (
        "ui",
        "ux",
        "interface",
        "view",
        "screen",
        "component",
        "layout",
        "style",
        "css",
        "tailwind",
        "swiftui",
        "react",
        "animation",
        "design system",
        "theme",
        "responsive",
    ),
    TaskKind.CODE: (
        "implement",
        "feature",
        "function",
        "endpoint",
        "api",
        "logic",
        "service",
        "handler",
        "fix bug",
        "integrate",
        "wire",
    ),
}


def classify_task(title: str, description: str = "") -> TaskKind:
    """Cheap local heuristic mapping a task's text to a :class:`TaskKind`.

    Returns the kind with the most keyword hits; ``GENERIC`` if nothing matches.
    """
    text = f"{title}\n{description}".lower()
    best_kind = TaskKind.GENERIC
    best_score = 0
    for kind, keywords in _KIND_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > best_score:
            best_score = score
            best_kind = kind
    return best_kind


# Per-kind default (model tier, effort). Tuned so cheap/mechanical work uses a cheap
# model + low effort and hard reasoning reserves the deep tier + high effort.
_KIND_POLICY: dict[TaskKind, tuple[ModelTier, Effort]] = {
    TaskKind.DOCS: (ModelTier.CHEAP, Effort.LOW),
    TaskKind.STRATEGY: (ModelTier.STANDARD, Effort.MEDIUM),
    TaskKind.UI: (ModelTier.STANDARD, Effort.HIGH),
    TaskKind.CODE: (ModelTier.STANDARD, Effort.HIGH),
    TaskKind.ARCHITECTURE: (ModelTier.DEEP, Effort.XHIGH),
    TaskKind.QA: (ModelTier.DEEP, Effort.HIGH),
    TaskKind.PLANNING: (ModelTier.STANDARD, Effort.MEDIUM),
    TaskKind.PARSE: (ModelTier.CHEAP, Effort.LOW),
    TaskKind.CHAT: (ModelTier.CHEAP, Effort.LOW),
    TaskKind.GENERIC: (ModelTier.STANDARD, Effort.HIGH),
}


def profile_for_kind(
    kind: TaskKind,
    *,
    tiering: bool = True,
    plan_first: bool = False,
    **overrides: Any,
) -> ExecutionProfile:
    """Build a default :class:`ExecutionProfile` for a task kind.

    Args:
        kind: the classified task kind.
        tiering: when False, leave model/effort to inherit (single-model mode).
        plan_first: force plan permission mode (a plan-only pass).
        overrides: any :class:`ExecutionProfile` field to override.
    """
    model_tier, effort = _KIND_POLICY.get(kind, (ModelTier.STANDARD, Effort.HIGH))
    if not tiering:
        model_tier, effort = ModelTier.INHERIT, Effort.INHERIT

    profile = ExecutionProfile(model_tier=model_tier, effort=effort)
    if plan_first:
        profile = profile.merged(permission_mode=PermissionMode.PLAN)
    if overrides:
        profile = profile.merged(**overrides)
    return profile


# Lightweight, always-cheap profile for internal utility calls (report parsing,
# manager-chat Q&A): cheap model, low effort, no tools needed.
#
# NOTE: ``bare`` is intentionally False. ``claude --bare`` forces Anthropic auth to
# ANTHROPIC_API_KEY/apiKeyHelper and never reads OAuth/keychain, which would break
# subscription (OAuth) auth used by most Archon runs. Enable ``bare`` only when an
# API key is configured. ``cache_friendly`` is OAuth-safe and kept on.
def utility_profile() -> ExecutionProfile:
    """Profile for internal, token-sensitive helper LLM calls (report parsing, chat)."""
    return ExecutionProfile(
        model_tier=ModelTier.CHEAP,
        effort=Effort.LOW,
        permission_mode=PermissionMode.DEFAULT,
        cache_friendly=True,
    )


def agents_json_str(profile: ExecutionProfile) -> str | None:
    """Serialize the profile's dynamic agents to the compact JSON the CLI expects."""
    if not profile.agents:
        return None
    return json.dumps(profile.agents, separators=(",", ":"))


# ---------------------------------------------------------------------------
# F7 — Skill / MCP creation policy (the "use, don't create" deny-set)
# ---------------------------------------------------------------------------
#
# The subprocess only sees the tools that ``Config.build_llm_command`` lets through
# (``--allowedTools`` / ``--disallowedTools``). We never emit ``--disable-slash-commands``
# (would kill skills) nor ``--strict-mcp-config`` (would kill all installed MCP servers,
# incl. XcodeBuildMCP), so *using* installed skills and MCP tools stays enabled by default.
#
# What we DO want to block is *creation* of new skills / MCP servers / plugins, which
# happens through two channels:
#   1. CLI subcommands: ``claude mcp ...``, ``claude plugin ...`` (run via Bash).
#   2. Writing the config / manifest files that register them: ``.mcp.json``,
#      ``SKILL.md``, and anything under a ``.claude/skills`` or ``.claude/plugins`` dir.
#
# These patterns use Claude Code's tool-spec syntax: ``Tool(specifier)`` where Bash
# specifiers are command-prefix globs and Write/Edit specifiers are file globs. Normal
# Bash / Write / Edit (anything not matching these specifiers) stays usable.
SKILL_MCP_DENY_TOOLS: list[str] = [
    # --- block create via CLI subcommands (leave normal Bash usable) ---
    "Bash(claude mcp:*)",
    "Bash(claude mcp add:*)",
    "Bash(claude mcp remove:*)",
    "Bash(claude plugin:*)",
    "Bash(claude plugin install:*)",
    "Bash(claude plugin marketplace:*)",
    # --- block writing MCP server config files ---
    "Write(.mcp.json)",
    "Write(**/.mcp.json)",
    "Edit(.mcp.json)",
    "Edit(**/.mcp.json)",
    # --- block writing/editing skill manifests + skills dirs ---
    "Write(**/SKILL.md)",
    "Edit(**/SKILL.md)",
    "Write(**/.claude/skills/**)",
    "Edit(**/.claude/skills/**)",
    # --- block writing/editing plugin dirs ---
    "Write(**/.claude/plugins/**)",
    "Edit(**/.claude/plugins/**)",
]


def mcp_allow_patterns() -> list[str]:
    """Return ``--allowedTools`` patterns that surface installed MCP tools.

    Installed MCP servers (XcodeBuildMCP, Context7, etc.) expose tools named
    ``mcp__<server>__<tool>``. The Claude CLI does **not** accept a blanket
    ``mcp__*`` allow pattern — it errors with *"Wildcard tool name mcp__* is not
    supported in allow rules; globs are permitted only after a literal
    ``mcp__<server>__`` prefix"* and silently ignores the rule. Since we can't
    enumerate servers generically, we emit no MCP allow pattern: workers reach MCP
    tools via the run's permission mode (the orchestrator launches with
    ``--dangerously-skip-permissions`` by default), and creating new MCP servers
    stays blocked by :data:`SKILL_MCP_DENY_TOOLS`.

    Returns:
        An empty list (no valid blanket MCP allow pattern exists).
    """
    return []


# ---------------------------------------------------------------------------
# F6 — Per-model base reasoning effort
# ---------------------------------------------------------------------------
#
# When the effort dial is on but a task profile left effort as INHERIT, the effort is
# derived from the resolved model/tier. Stronger models default to more reasoning effort.
# Keys are matched case-insensitively against substrings of the resolved model/tier name
# (so concrete aliases like ``opus``, dated ids like ``claude-opus-4-...`` and tier names
# like ``deep``/``cheap`` all resolve correctly).
DEFAULT_BASE_EFFORT_TABLE: dict[str, str] = {
    "opus": Effort.HIGH.value,
    "sonnet": Effort.MEDIUM.value,
    "haiku": Effort.LOW.value,
    # tier names (in case a tier string is passed instead of a model alias)
    "deep": Effort.HIGH.value,
    "standard": Effort.MEDIUM.value,
    "cheap": Effort.LOW.value,
    # explicit catch-all
    "default": Effort.INHERIT.value,
}


def base_effort_for(
    model_or_tier: str | None,
    table: dict[str, str] | None = None,
) -> Effort:
    """Map a resolved model or tier name to a base :class:`Effort`.

    Pure and deterministic (no I/O). Matching is case-insensitive and substring-based,
    so concrete aliases (``opus``), dated model ids (``claude-opus-4-...``) and tier
    names (``deep``) all resolve. Unknown / empty input falls back to
    :attr:`Effort.INHERIT` (meaning "emit no ``--effort`` flag").

    Args:
        model_or_tier: the resolved ``--model`` value or tier name (may be ``None``).
        table: optional override mapping of (lowercase) key substrings to effort value
            strings; merged over :data:`DEFAULT_BASE_EFFORT_TABLE`. Values may be
            :class:`Effort` members or their string values.

    Returns:
        The derived :class:`Effort` (``Effort.INHERIT`` when nothing matches).
    """
    if not model_or_tier:
        return Effort.INHERIT

    merged: dict[str, str] = dict(DEFAULT_BASE_EFFORT_TABLE)
    if table:
        for key, value in table.items():
            if key is None or value is None:
                continue
            merged[str(key).lower()] = value.value if isinstance(value, Effort) else str(value)

    name = str(model_or_tier).lower()

    # 1) exact match wins (e.g. "default", or a precise tier/alias).
    if name in merged:
        return _coerce_effort(merged[name])

    # 2) substring match, longest key first so "opus" beats a generic catch-all.
    for key in sorted((k for k in merged if k != "default"), key=len, reverse=True):
        if key and key in name:
            return _coerce_effort(merged[key])

    # 3) explicit default entry, else INHERIT.
    if "default" in merged:
        return _coerce_effort(merged["default"])
    return Effort.INHERIT


def _coerce_effort(value: str) -> Effort:
    """Coerce a string/Effort value to an :class:`Effort` (INHERIT on bad input)."""
    if isinstance(value, Effort):
        return value
    try:
        return Effort(str(value).lower())
    except ValueError:
        return Effort.INHERIT
