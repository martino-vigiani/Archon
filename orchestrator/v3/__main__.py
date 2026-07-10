"""Run the V3 orchestrator standalone, bound to one project directory.

Usage::

    python -m orchestrator.v3 --project /path/to/project [--port 0] [--host 127.0.0.1]

Binds loopback only (contract §1.1). With ``--port 0`` an ephemeral port is
chosen and printed; the ``0600`` ``runtime.json`` handshake is written under
``~/Library/Application Support/Archon/projects/<project_id>/`` so a supervising
client can read the port + token. ``--bare`` is intentionally not exposed
(breaks OAuth).
"""

from __future__ import annotations

import argparse
import socket
import sys
from pathlib import Path

import uvicorn

from .app import create_v3_app


def _pick_port(host: str, requested: int) -> int:
    if requested and requested > 0:
        return requested
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((host, 0))
        return sock.getsockname()[1]
    finally:
        sock.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m orchestrator.v3")
    parser.add_argument("--project", required=True, help="Absolute path to the bound project directory")
    parser.add_argument("--host", default="127.0.0.1", help="Loopback host (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=0, help="Port (0 = ephemeral)")
    args = parser.parse_args(argv)

    project = Path(args.project).expanduser()
    if not project.is_dir():
        print(f"error: project directory not found: {project}", file=sys.stderr)
        return 2
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print(f"error: refusing non-loopback host {args.host!r}", file=sys.stderr)
        return 2

    port = _pick_port(args.host, args.port)
    app = create_v3_app(str(project), port=port, write_runtime=True)
    state = app.state.v3
    print(f"Archon V3 orchestrator: project={state.project_path}")
    print(f"  project_id={state.project_id}")
    print(f"  http://{args.host}:{port}/v3  ws://{args.host}:{port}/v3/stream")
    print(f"  runtime.json={state.paths.runtime_file}")

    uvicorn.run(app, host=args.host, port=port, log_level="info")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
