"""Archon V3 backend package.

Implements ``API_CONTRACT_V3.md`` (frozen, normative): a single-project,
client-supervised FastAPI orchestrator exposing a ``/v3`` REST control plane and
a single ``/v3/stream`` WebSocket event stream. It reuses the existing
orchestrator machinery (config, PTY spawning conventions, auth-token pattern)
but lives entirely under ``orchestrator/v3/`` so the legacy modules and their
778 tests are never restructured.

Public entry points:

* :func:`orchestrator.v3.app.create_v3_app` — build the standalone ASGI app for
  a bound project directory (the primary, client-supervised deployment).
* :func:`orchestrator.v3.app.mount_v3` — mount the same routes under ``/v3`` on
  an existing FastAPI app (optional integration with the legacy dashboard).
"""

from __future__ import annotations

#: Protocol major version (``pv``). Minor changes are additive-only.
PROTOCOL_VERSION = 1

#: Reported orchestrator build version (``GET /v3/health.orchestrator_version``).
ORCHESTRATOR_VERSION = "3.0.0"

#: Default hard concurrency ceiling on live sessions (REQ-BE-004).
HARD_CEILING_DEFAULT = 8

#: In-memory replay ring bounds (Q12 / REQ-BE-043).
REPLAY_MAX_EVENTS = 2000
REPLAY_WINDOW_S = 60

#: Maximum synchronous dry-run budget in seconds (Q14 / REQ-UX-034).
DRY_RUN_MAX_S = 1.5

#: Supported agent provider for the MVP (Addendum A1).
SUPPORTED_PROVIDER = "claude_code"

__all__ = [
    "PROTOCOL_VERSION",
    "ORCHESTRATOR_VERSION",
    "HARD_CEILING_DEFAULT",
    "REPLAY_MAX_EVENTS",
    "REPLAY_WINDOW_S",
    "DRY_RUN_MAX_S",
    "SUPPORTED_PROVIDER",
]
