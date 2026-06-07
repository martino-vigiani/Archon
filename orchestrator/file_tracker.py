"""File provenance and workspace-graph derivation (F12, F13).

This module is read-only over a single session's ``.orchestra`` tree. It never
mutates state and never changes the report-capture format: it consumes the
narration-derived ``Report.files_created`` / ``Report.files_modified`` lists that
the report manager already persists under ``reports/<worker_id>/*.json``.

Two public functions:

* :func:`collect_file_events` flattens every worker report into a deduplicated
  timeline of file events (``created`` / ``modified``), newest action winning per
  path.
* :func:`build_workspace_graph` assembles a node/edge graph (agents + files) that
  the dashboard's workspace view renders. Agent nodes are derived from the live
  roster (``status.json``) and the report directories on disk; ``creates`` edges
  link an agent to each file it touched; ``provides`` / ``depends`` edges are read
  from any interface ``contracts/*.json``.

Every function is robust to missing directories, missing files, and malformed
JSON: it degrades to empty results rather than raising into its callers.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

__all__ = ["collect_file_events", "build_workspace_graph"]

# Directory names under ``reports/`` that are NOT worker report folders and must
# be skipped when deriving worker ids from disk.
_NON_WORKER_REPORT_DIRS = frozenset({"summary"})


def _load_json(path: Path) -> Any | None:
    """Load a JSON file, returning ``None`` on any I/O or parse failure.

    Args:
        path: File to read.

    Returns:
        The decoded JSON value, or ``None`` if the file is missing or invalid.
    """
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _iter_report_files(reports_dir: Path) -> list[tuple[str, Path]]:
    """Yield ``(worker_id, report_path)`` pairs for every worker report file.

    Worker ids are the report subdirectory names (``reports/<worker_id>/*.json``),
    excluding bookkeeping folders such as ``summary``. Worker ids are derived from
    what is on disk — no hardcoded ``t1``-``t5`` assumptions.

    Args:
        reports_dir: The ``reports`` directory inside a session tree.

    Returns:
        A list of ``(worker_id, path)`` tuples. Empty if the directory is absent.
    """
    pairs: list[tuple[str, Path]] = []
    try:
        worker_dirs = sorted(p for p in reports_dir.iterdir() if p.is_dir())
    except (OSError, ValueError):
        return pairs
    for worker_dir in worker_dirs:
        worker_id = worker_dir.name
        if worker_id in _NON_WORKER_REPORT_DIRS:
            continue
        try:
            report_files = sorted(worker_dir.glob("*.json"))
        except (OSError, ValueError):
            continue
        for report_path in report_files:
            pairs.append((worker_id, report_path))
    return pairs


def collect_file_events(session_dir: Path) -> list[dict[str, Any]]:
    """Build a deduplicated file-event timeline from worker reports.

    Reads only ``session_dir/reports/<worker_id>/*.json`` and consumes each
    report's ``files_created`` / ``files_modified`` lists (the existing narration
    capture format — unchanged here). For every referenced path an event is
    produced; when the same path appears in multiple reports, the newest action
    wins (by report ``timestamp``, then by report id ordering).

    Args:
        session_dir: The per-session ``.orchestra`` directory (e.g.
            ``<base>/.orchestra/runs/<session_id>`` or the legacy ``.orchestra``).

    Returns:
        A list of event dicts, each shaped as
        ``{"path": str, "worker": str, "action": "created"|"modified",
        "ts": str}``, sorted by timestamp ascending. Empty when nothing is found.
    """
    reports_dir = Path(session_dir) / "reports"
    # path -> winning event; later iteration overwrites only when strictly newer.
    latest: dict[str, dict[str, Any]] = {}

    for worker_id, report_path in _iter_report_files(reports_dir):
        data = _load_json(report_path)
        if not isinstance(data, dict):
            continue

        worker = data.get("terminal_id") or worker_id
        ts = data.get("timestamp") or ""

        for action, key in (("created", "files_created"), ("modified", "files_modified")):
            raw = data.get(key)
            if not isinstance(raw, list):
                continue
            for entry in raw:
                if not isinstance(entry, str):
                    continue
                path = entry.strip()
                if not path:
                    continue
                candidate: dict[str, Any] = {
                    "path": path,
                    "worker": worker,
                    "action": action,
                    "ts": ts,
                }
                existing = latest.get(path)
                # Newest action wins per path. Compare ISO timestamps lexically
                # (ISO-8601 sorts chronologically); ties keep the later-seen one,
                # which is the later report given the sorted iteration order.
                if existing is None or str(candidate["ts"]) >= str(existing["ts"]):
                    latest[path] = candidate

    events = list(latest.values())
    events.sort(key=lambda e: (str(e.get("ts", "")), str(e.get("path", ""))))
    return events


def _roster_from_status(session_dir: Path) -> list[dict[str, Any]]:
    """Read the live roster from ``status.json``, if present.

    The orchestrator writes ``"roster"`` as a list of ``AgentSpec.to_dict()``
    entries. This tolerates a missing key, a missing file, or unexpected shapes.

    Args:
        session_dir: The per-session ``.orchestra`` directory.

    Returns:
        A list of roster-entry dicts (possibly empty).
    """
    status = _load_json(Path(session_dir) / "status.json")
    if not isinstance(status, dict):
        return []
    roster = status.get("roster")
    if not isinstance(roster, list):
        return []
    return [entry for entry in roster if isinstance(entry, dict)]


def _agent_label(entry: dict[str, Any], worker_id: str) -> str:
    """Derive a human-friendly label for an agent node.

    Args:
        entry: A roster entry dict (may be empty for disk-only workers).
        worker_id: The worker id fallback.

    Returns:
        A non-empty label string.
    """
    focus = entry.get("focus")
    lane = entry.get("lane")
    if isinstance(focus, str) and focus.strip():
        return focus.strip()
    if isinstance(lane, str) and lane.strip():
        return lane.strip()
    return worker_id


def _iter_contracts(session_dir: Path) -> list[dict[str, Any]]:
    """Load every interface contract under ``contracts/*.json``.

    Args:
        session_dir: The per-session ``.orchestra`` directory.

    Returns:
        A list of contract dicts (possibly empty). Robust to a missing directory.
    """
    contracts_dir = Path(session_dir) / "contracts"
    contracts: list[dict[str, Any]] = []
    try:
        files = sorted(contracts_dir.glob("*.json"))
    except (OSError, ValueError):
        return contracts
    for contract_path in files:
        data = _load_json(contract_path)
        if isinstance(data, dict):
            contracts.append(data)
    return contracts


def build_workspace_graph(session_dir: Path) -> dict[str, Any]:
    """Assemble the agent/file workspace graph for the workspace view.

    Nodes:
        * Agent nodes — derived from the live roster (``status.json``) merged with
          any worker directory found under ``reports/`` (so workers that produced
          output but are not in the roster snapshot still appear). Worker ids come
          from disk; no fixed ``t1``-``t5`` helper is used.
        * File nodes — one per distinct path in :func:`collect_file_events`.

    Edges:
        * ``creates`` — agent → file, one per file event.
        * ``provides`` — contract owner → contract node (interface offered).
        * ``depends`` — contract consumer → contract node (interface required).

    Args:
        session_dir: The per-session ``.orchestra`` directory.

    Returns:
        ``{"nodes": [...], "edges": [...]}`` where each node is
        ``{"id": str, "type": "file"|"agent"|"contract", "worker": str|None,
        "label": str}`` and each edge is
        ``{"from": str, "to": str, "kind": "creates"|"provides"|"depends"}``.
        Returns an empty graph (``{"nodes": [], "edges": []}``) on any failure.
    """
    session_dir = Path(session_dir)
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    node_ids: set[str] = set()

    def _add_node(node_id: str, node_type: str, worker: str | None, label: str) -> None:
        if node_id in node_ids:
            return
        node_ids.add(node_id)
        nodes.append(
            {"id": node_id, "type": node_type, "worker": worker, "label": label}
        )

    # --- Agent nodes: roster snapshot first, then any worker seen on disk. ------
    roster = _roster_from_status(session_dir)
    seen_workers: set[str] = set()
    for entry in roster:
        worker_id = entry.get("id")
        if not isinstance(worker_id, str) or not worker_id.strip():
            continue
        worker_id = worker_id.strip()
        agent_node_id = f"agent:{worker_id}"
        _add_node(agent_node_id, "agent", worker_id, _agent_label(entry, worker_id))
        seen_workers.add(worker_id)

    # --- File events: file nodes + agent nodes for any worker that produced them.
    events = collect_file_events(session_dir)
    for event in events:
        worker_id = str(event.get("worker", "")).strip()
        if worker_id and worker_id not in seen_workers:
            _add_node(f"agent:{worker_id}", "agent", worker_id, worker_id)
            seen_workers.add(worker_id)

    for event in events:
        path = str(event.get("path", "")).strip()
        if not path:
            continue
        file_node_id = f"file:{path}"
        label = Path(path).name or path
        _add_node(file_node_id, "file", None, label)

        worker_id = str(event.get("worker", "")).strip()
        if worker_id:
            edges.append(
                {"from": f"agent:{worker_id}", "to": file_node_id, "kind": "creates"}
            )

    # --- Contract nodes + provides/depends edges. ------------------------------
    for contract in _iter_contracts(session_dir):
        name = contract.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        name = name.strip()
        contract_node_id = f"contract:{name}"
        _add_node(contract_node_id, "contract", None, name)

        owner = contract.get("owner")
        if isinstance(owner, str) and owner.strip():
            owner = owner.strip()
            _add_node(f"agent:{owner}", "agent", owner, owner)
            edges.append(
                {"from": f"agent:{owner}", "to": contract_node_id, "kind": "provides"}
            )

        consumers = contract.get("consumers")
        if isinstance(consumers, list):
            for consumer in consumers:
                if not isinstance(consumer, str) or not consumer.strip():
                    continue
                consumer = consumer.strip()
                _add_node(f"agent:{consumer}", "agent", consumer, consumer)
                edges.append(
                    {
                        "from": f"agent:{consumer}",
                        "to": contract_node_id,
                        "kind": "depends",
                    }
                )

    return {"nodes": nodes, "edges": edges}
