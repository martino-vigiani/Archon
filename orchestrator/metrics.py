"""Pure metric and prompt-adherence computation (F9, F11).

This module computes fresh run metrics and a heuristic prompt-adherence
confidence signal from state the caller has *already loaded*. Everything here is
a pure, deterministic function with **no I/O** — callers pass plain dicts/strings
and receive plain dicts/floats back.

Design notes (binding contract §6):
    * Tokens and cost are intentionally **omitted**: they are not available when
      workers run via ``claude --print`` text mode, so there is no reliable
      source to derive them from. The metrics block exposes only counts,
      percentages, throughput and elapsed time.
    * Functions never raise on malformed input. Missing or wrong-typed fields
      degrade gracefully to neutral defaults (``0`` / ``0.0`` / ``{}``) so a
      single bad value can never crash the caller's status-update loop.
    * Only ``elapsed_sec`` reflects wall-clock time; the caller decides whether
      it enters any state hash used for dashboard de-duplication.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

__all__ = ["compute_metrics", "adherence_for"]


def _to_float(value: Any, default: float = 0.0) -> float:
    """Coerce ``value`` to ``float``, returning ``default`` on failure.

    Args:
        value: Arbitrary value to coerce.
        default: Fallback returned when coercion is impossible.

    Returns:
        The coerced float, or ``default`` if ``value`` is ``None`` or not
        numeric.
    """
    if value is None:
        return default
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    # Guard against NaN / inf leaking into the dashboard payload.
    if result != result or result in (float("inf"), float("-inf")):
        return default
    return result


def _to_int(value: Any, default: int = 0) -> int:
    """Coerce ``value`` to a non-negative ``int``, returning ``default`` on failure.

    Args:
        value: Arbitrary value to coerce.
        default: Fallback returned when coercion is impossible.

    Returns:
        The coerced int (never negative), or ``default`` if coercion fails.
    """
    coerced = _to_float(value, float(default))
    try:
        as_int = int(coerced)
    except (TypeError, ValueError, OverflowError):
        return default
    return as_int if as_int >= 0 else default


def _parse_iso(value: Any) -> datetime | None:
    """Parse an ISO-8601 timestamp string into a ``datetime``.

    Args:
        value: An ISO-8601 string (e.g. produced by ``datetime.isoformat()``),
            or any non-string value.

    Returns:
        The parsed ``datetime``, or ``None`` if ``value`` is not a parseable
        ISO-8601 string.
    """
    if not isinstance(value, str) or not value:
        return None
    text = value.strip()
    # ``datetime.fromisoformat`` accepts a trailing ``Z`` only on 3.11+, but be
    # defensive and normalise it regardless.
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except (ValueError, TypeError):
        return None


def _elapsed_seconds(started_at: str | None, now: str) -> int:
    """Compute elapsed whole seconds between ``started_at`` and ``now``.

    Args:
        started_at: ISO-8601 start timestamp, or ``None`` if unknown.
        now: ISO-8601 "current" timestamp supplied by the caller.

    Returns:
        Non-negative elapsed seconds. Returns ``0`` when either timestamp is
        missing/unparseable, or when ``now`` precedes ``started_at``.
    """
    start_dt = _parse_iso(started_at)
    now_dt = _parse_iso(now)
    if start_dt is None or now_dt is None:
        return 0
    # Mixed aware/naive datetimes would raise on subtraction; drop tzinfo so the
    # comparison is always well-defined and the result stays a plain duration.
    if start_dt.tzinfo is not None:
        start_dt = start_dt.replace(tzinfo=None)
    if now_dt.tzinfo is not None:
        now_dt = now_dt.replace(tzinfo=None)
    delta = (now_dt - start_dt).total_seconds()
    if delta < 0:
        return 0
    return int(delta)


def _task_counts(tasks: Any) -> tuple[int, int, int, int, int]:
    """Extract task counts from a task-status summary dict.

    Accepts the dict produced by ``TaskQueue.get_status_summary`` (keys like
    ``pending_count``, ``in_progress_count``, ``completed_count``,
    ``failed_count``, ``total_count``) and tolerates partial/alternate shapes.

    Args:
        tasks: The task-status dict (or any value).

    Returns:
        A 5-tuple ``(in_progress, pending, completed, failed, total)`` of
        non-negative ints. ``total`` is derived from the parts when not given.
    """
    if not isinstance(tasks, dict):
        return (0, 0, 0, 0, 0)

    in_progress = _to_int(tasks.get("in_progress_count"))
    pending = _to_int(tasks.get("pending_count"))
    completed = _to_int(tasks.get("completed_count"))
    failed = _to_int(tasks.get("failed_count"))

    total = _to_int(tasks.get("total_count"))
    derived_total = in_progress + pending + completed + failed
    # ``total_count`` includes failed tasks in get_status_summary, so the derived
    # sum should match; prefer the explicit value but never report below the sum.
    if derived_total > total:
        total = derived_total

    return (in_progress, pending, completed, failed, total)


def _per_worker(status: Any) -> dict[str, dict[str, float]]:
    """Build the per-worker progress/quality map from a status dict.

    Args:
        status: The orchestrator status dict, whose ``"terminals"`` key maps
            worker ids to per-worker state (with ``quality_level``).

    Returns:
        Mapping of worker id → ``{"progress_pct": float, "quality": float}``.
        ``progress_pct`` is the worker's current-task quality expressed as a
        percentage (0–100); ``quality`` is the same quality on the 0–1 gradient.
        Empty dict when no terminals are present.
    """
    if not isinstance(status, dict):
        return {}
    terminals = status.get("terminals")
    if not isinstance(terminals, dict):
        return {}

    per_worker: dict[str, dict[str, float]] = {}
    for wid, state in terminals.items():
        quality = _to_float(state.get("quality_level")) if isinstance(state, dict) else 0.0
        # Clamp to the documented 0..1 gradient.
        quality = max(0.0, min(1.0, quality))
        per_worker[str(wid)] = {
            "progress_pct": round(quality * 100.0, 1),
            "quality": round(quality, 3),
        }
    return per_worker


def compute_metrics(
    status: dict,
    tasks: dict,
    started_at: str | None,
    now: str,
) -> dict:
    """Compute the live metrics block for a run (F9).

    Aggregates task counts, completion percentage, throughput and elapsed time
    from already-loaded state. Pure and deterministic for fixed inputs.

    Tokens and cost are deliberately **not** reported: they are unavailable in
    ``claude --print`` text mode, so there is no trustworthy source for them.

    Args:
        status: Orchestrator status dict; its ``"terminals"`` key (if present)
            drives the ``per_worker`` block.
        tasks: Task-status summary dict (``TaskQueue.get_status_summary`` shape)
            providing ``pending_count`` / ``in_progress_count`` /
            ``completed_count`` / ``failed_count`` / ``total_count``.
        started_at: ISO-8601 run start timestamp, or ``None`` if unknown.
        now: ISO-8601 "current" timestamp; the caller controls what enters any
            state hash, since this is the only wall-clock-derived field.

    Returns:
        A dict with keys ``completion_pct`` (float 0–100), ``in_progress``,
        ``pending``, ``completed``, ``failed`` (ints), ``throughput_per_min``
        (float, completed tasks per minute), ``elapsed_sec`` (int) and
        ``per_worker`` (worker id → ``{"progress_pct", "quality"}``). Never
        raises; malformed inputs yield neutral zeros.
    """
    in_progress, pending, completed, failed, total = _task_counts(tasks)

    # Completion % over all known tasks. A run with no tasks is 0% complete.
    completion_pct = round((completed / total) * 100.0, 1) if total > 0 else 0.0
    # Clamp defensively in case of count drift between fields.
    completion_pct = max(0.0, min(100.0, completion_pct))

    elapsed_sec = _elapsed_seconds(started_at, now)

    # Throughput = completed tasks per minute of elapsed wall-clock time.
    throughput_per_min = round(completed / (elapsed_sec / 60.0), 2) if elapsed_sec > 0 else 0.0

    return {
        "completion_pct": completion_pct,
        "in_progress": in_progress,
        "pending": pending,
        "completed": completed,
        "failed": failed,
        "throughput_per_min": throughput_per_min,
        "elapsed_sec": elapsed_sec,
        "per_worker": _per_worker(status),
    }


# Phrases that signal a worker honoured the standard 6-point output format. The
# heuristic looks for any of these markers (case-insensitive) in the output.
_OUTPUT_FORMAT_MARKERS: tuple[str, ...] = (
    "summary",
    "files created",
    "files modified",
    "components",
    "provides",
    "dependencies",
    "next steps",
    "blockers",
)

# Tokens shorter than this are ignored when matching task-title keywords, so
# stop-words like "a"/"to"/"the" don't inflate the score.
_MIN_KEYWORD_LEN = 4

# Common words that carry no signal even when long enough to pass the length
# filter; excluded from title-keyword matching.
_KEYWORD_STOPWORDS: frozenset[str] = frozenset(
    {
        "with",
        "from",
        "this",
        "that",
        "your",
        "into",
        "make",
        "using",
        "build",
        "create",
        "task",
        "should",
        "would",
        "their",
        "them",
        "then",
        "than",
        "have",
        "will",
    }
)

_WORD_RE = re.compile(r"[a-z0-9]+")


def _keywords(text: str) -> list[str]:
    """Extract significant lowercase keyword tokens from ``text``.

    Args:
        text: Source text (e.g. a task title or description).

    Returns:
        De-duplicated list of lowercase tokens at least ``_MIN_KEYWORD_LEN``
        chars long that are not stop-words, preserving first-seen order.
    """
    seen: dict[str, None] = {}
    for token in _WORD_RE.findall(text.lower()):
        if len(token) < _MIN_KEYWORD_LEN or token in _KEYWORD_STOPWORDS:
            continue
        seen.setdefault(token, None)
    return list(seen.keys())


def _deliverable_terms(task: dict) -> list[str]:
    """Collect required-deliverable terms declared on a task.

    Looks at common places where a task may pin concrete deliverables: explicit
    ``deliverables`` / ``required`` fields and any ``metadata`` mirror of them.

    Args:
        task: The task dict.

    Returns:
        Lowercase, whitespace-stripped, non-empty deliverable strings. Empty
        list when none are declared.
    """
    terms: list[str] = []

    def _ingest(value: Any) -> None:
        if isinstance(value, str):
            cleaned = value.strip().lower()
            if cleaned:
                terms.append(cleaned)
        elif isinstance(value, (list, tuple, set)):
            for item in value:
                _ingest(item)

    for key in ("deliverables", "required", "required_deliverables"):
        _ingest(task.get(key))

    metadata = task.get("metadata")
    if isinstance(metadata, dict):
        for key in ("deliverables", "required", "required_deliverables"):
            _ingest(metadata.get(key))

    return terms


def adherence_for(
    prompt_record: dict | None,
    output_text: str,
    task: dict,
) -> float:
    """Heuristic prompt-adherence confidence for a worker's output (F11).

    Estimates how well ``output_text`` honours the task it was given, combining
    three signals: (1) coverage of the task's required deliverables, (2) presence
    of the standard 6-point output-format markers, and (3) overlap with keywords
    from the task title. Pure, deterministic, no I/O.

    Args:
        prompt_record: The captured prompt record for the run (as written by the
            prompt-capture path), or ``None``. Its ``"body"`` text, when
            present, augments the deliverable/keyword corpus the output is
            checked against. Tolerant of any shape.
        output_text: The worker's raw output text.
        task: The task dict (uses ``title``, optional ``description`` and any
            declared deliverables).

    Returns:
        A confidence score in ``[0.0, 1.0]`` rounded to 3 decimals. Returns
        ``0.0`` for empty output; never raises.
    """
    if not isinstance(output_text, str) or not output_text.strip():
        return 0.0

    output_lower = output_text.lower()
    task = task if isinstance(task, dict) else {}

    # --- Signal 1: required-deliverable coverage -------------------------------
    deliverables = _deliverable_terms(task)
    if deliverables:
        hit = sum(1 for term in deliverables if term in output_lower)
        deliverable_score = hit / len(deliverables)
    else:
        # No explicit deliverables declared → this signal is neutral (excluded
        # from the weighting below rather than penalising the worker).
        deliverable_score = None

    # --- Signal 2: 6-point output-format markers -------------------------------
    marker_hits = sum(1 for marker in _OUTPUT_FORMAT_MARKERS if marker in output_lower)
    # Treat ~half the markers as "fully formatted" so a complete-but-terse report
    # still scores 1.0 on this axis.
    target_markers = max(1, len(_OUTPUT_FORMAT_MARKERS) // 2)
    format_score = min(1.0, marker_hits / target_markers)

    # --- Signal 3: task-title (+ prompt body) keyword overlap ------------------
    corpus = str(task.get("title", ""))
    description = task.get("description")
    if isinstance(description, str):
        corpus += " " + description
    if isinstance(prompt_record, dict):
        body = prompt_record.get("body")
        if isinstance(body, str):
            corpus += " " + body
    keywords = _keywords(corpus)
    if keywords:
        kw_hit = sum(1 for kw in keywords if kw in output_lower)
        keyword_score = kw_hit / len(keywords)
    else:
        keyword_score = None

    # --- Weighted blend over the signals that are actually present -------------
    weighted: list[tuple[float, float]] = [(format_score, 0.4)]
    if deliverable_score is not None:
        weighted.append((deliverable_score, 0.4))
    if keyword_score is not None:
        weighted.append((keyword_score, 0.2))

    total_weight = sum(weight for _, weight in weighted)
    if total_weight <= 0:
        return 0.0
    score = sum(value * weight for value, weight in weighted) / total_weight

    return round(max(0.0, min(1.0, score)), 3)
