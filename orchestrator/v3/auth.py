"""Authentication, origin guard, and protocol-version negotiation (contract §1.3/§1.4).

Both planes authenticate with the single bearer token from the ``0600``
``runtime.json`` file:

* **REST** — ``Authorization: Bearer <token>`` on *every* ``/v3`` request
  (including ``GET /v3/health``). Comparison is constant-time.
* **WebSocket** — ``?token=<token>`` (or the ``Authorization`` header). The WS
  upgrade ``Origin``, if present, must be loopback; otherwise close ``1008``.

Protocol version: a present-but-mismatched ``Archon-Protocol-Version`` major →
``409 incompatible_version`` on mutating calls (health still answers 200 so the
client can read ``pv``).
"""

from __future__ import annotations

import hmac
from typing import TYPE_CHECKING, Any

from fastapi import Depends, Request

from . import PROTOCOL_VERSION
from .errors import ApiError

if TYPE_CHECKING:  # pragma: no cover - typing only
    from starlette.websockets import WebSocket

    from .state import V3State

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}


def get_state(request: Request) -> "V3State":
    """FastAPI dependency: return the app's bound :class:`V3State`."""
    state = getattr(request.app.state, "v3", None)
    if state is None:
        raise ApiError("orchestrator_error", "V3 state not initialized")
    return state


def _extract_bearer(request: Request) -> str | None:
    header = request.headers.get("authorization")
    if header and header.lower().startswith("bearer "):
        return header[7:].strip()
    return None


def tokens_match(presented: str | None, expected: str) -> bool:
    """Constant-time bearer comparison; empty/None presented never matches."""
    if not presented or not expected:
        return False
    return hmac.compare_digest(str(presented), str(expected))


async def require_token(request: Request, state: "V3State" = Depends(get_state)) -> None:
    """Reject requests lacking a valid bearer token (401 ``unauthorized``)."""
    if not tokens_match(_extract_bearer(request), state.token):
        raise ApiError("unauthorized", "Missing or invalid bearer token")


def _check_version_header(raw: str | None) -> None:
    if raw is None:
        return  # header optional; absence is tolerated (additive-only policy)
    try:
        major = int(raw)
    except (TypeError, ValueError):
        raise ApiError("incompatible_version", f"Malformed protocol version {raw!r}")
    if major != PROTOCOL_VERSION:
        raise ApiError(
            "incompatible_version",
            f"Client protocol major {major} != server {PROTOCOL_VERSION}",
        )


async def require_version(request: Request) -> None:
    """Reject a mismatched ``Archon-Protocol-Version`` major (409)."""
    _check_version_header(request.headers.get("archon-protocol-version"))


#: Dependency lists for routers.
TOKEN_ONLY = [Depends(require_token)]
AUTHORIZED = [Depends(require_token), Depends(require_version)]


def _origin_ok(origin: str | None) -> bool:
    if origin is None:
        return True  # header-less non-browser clients are allowed past the origin check
    try:
        from urllib.parse import urlparse

        host = urlparse(origin).hostname
    except Exception:  # noqa: BLE001
        return False
    return host in _LOOPBACK_HOSTS


def ws_auth_check(websocket: "WebSocket", state: "V3State") -> tuple[bool, int, str]:
    """Validate a WebSocket upgrade before it is usable.

    Returns ``(ok, close_code, reason)``. On failure the stream layer closes the
    socket with ``close_code`` (always ``1008`` policy-violation per contract).
    """
    origin = websocket.headers.get("origin")
    if not _origin_ok(origin):
        return False, 1008, "bad_origin"

    presented = websocket.query_params.get("token") or _ws_header_bearer(websocket)
    if not tokens_match(presented, state.token):
        return False, 1008, "unauthorized"

    raw_pv = websocket.query_params.get("pv") or websocket.headers.get("archon-protocol-version")
    if raw_pv is not None:
        try:
            if int(raw_pv) != PROTOCOL_VERSION:
                return False, 1008, "incompatible_version"
        except (TypeError, ValueError):
            return False, 1008, "incompatible_version"

    return True, 1000, "ok"


def _ws_header_bearer(websocket: "WebSocket") -> str | None:
    header = websocket.headers.get("authorization")
    if header and header.lower().startswith("bearer "):
        return header[7:].strip()
    return None


__all__ = [
    "get_state",
    "require_token",
    "require_version",
    "tokens_match",
    "ws_auth_check",
    "TOKEN_ONLY",
    "AUTHORIZED",
    "PROTOCOL_VERSION",
    "Any",
]
