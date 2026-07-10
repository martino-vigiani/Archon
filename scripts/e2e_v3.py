#!/usr/bin/env python3
"""Archon V3 — end-to-end integration harness (real processes, real sockets).

This proves the client⇄orchestrator seams that unit tests never touch: the
supervisor's *actual* launch config, the ``0600`` runtime handshake, the live
WebSocket stream (hello + heartbeat + gap-free resume), kanban CRUD with event
fan-out, the memory provenance guard, the PTY session lifecycle + kill, and the
hard zero-footprint guarantee (Addendum §A3).

It boots the orchestrator EXACTLY the way ``OrchestratorSupervisor`` does —
``<venv>/python -m orchestrator.v3 --project <canonical>`` with the supervisor's
env — plus ``ARCHON_V3_ADAPTER=sleep`` so the PTY lifecycle can be exercised
deterministically and offline (no ``claude`` binary / OAuth, and the stub writes
nothing to the project tree, keeping the zero-footprint proof clean).

Rerunnable: ``<venv>/bin/python scripts/e2e_v3.py``. Exit 0 = all PASS.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import websockets

REPO = Path("/Users/martinovigiani/lab/Archon")
VENV_PY = REPO / ".venv" / "bin" / "python"
SCRATCH = Path("/tmp/archon-e2e-project")
ORCH_LOG = Path("/tmp/archon-e2e-orch.log")
PV = 1

# ---------------------------------------------------------------------------
# result table
# ---------------------------------------------------------------------------
RESULTS: list[tuple[str, str, str]] = []  # (step, PASS/FAIL, detail)


def record(step: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((step, "PASS" if ok else "FAIL", detail))
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {step} — {detail}", flush=True)


class StepFail(Exception):
    pass


def check(step: str, cond: bool, detail: str = "") -> None:
    record(step, bool(cond), detail)
    if not cond:
        raise StepFail(step)


# ---------------------------------------------------------------------------
# identity / paths (mirror ids.py + storage.py)
# ---------------------------------------------------------------------------
def canonical(path: Path) -> str:
    return os.path.realpath(os.path.abspath(str(path)))


def project_id_for(path: Path) -> str:
    return hashlib.sha256(canonical(path).encode("utf-8")).hexdigest()


def support_root() -> Path:
    return Path.home() / "Library" / "Application Support" / "Archon"


def state_dir_for(path: Path) -> Path:
    return support_root() / "projects" / project_id_for(path)


# ---------------------------------------------------------------------------
# scratch project + snapshot manifest
# ---------------------------------------------------------------------------
SRC_FILES = {
    "CLAUDE.md": "# archon-e2e scratch project\n\nGuidance for agents working here.\n",
    "README.md": "# scratch\n\nA tiny repo used by the Archon V3 E2E harness.\n",
    "src/main.py": "def main():\n    print('hello from scratch')\n\n\nif __name__ == '__main__':\n    main()\n",
    "src/util.py": "def add(a, b):\n    return a + b\n",
    "pkg/api/CLAUDE.md": "# api package guidance\n\nnested memory file.\n",
}


def setup_scratch_project() -> None:
    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)
    SCRATCH.mkdir(parents=True)
    for rel, content in SRC_FILES.items():
        p = SCRATCH / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "E2E",
        "GIT_AUTHOR_EMAIL": "e2e@archon.local",
        "GIT_COMMITTER_NAME": "E2E",
        "GIT_COMMITTER_EMAIL": "e2e@archon.local",
    }
    run = lambda *a: subprocess.run(a, cwd=SCRATCH, env=env, check=True,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    run("git", "init", "-q")
    run("git", "add", "-A")
    run("git", "commit", "-q", "-m", "initial scratch commit")


def manifest(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            fp = Path(dirpath) / name
            rel = str(fp.relative_to(root))
            try:
                out[rel] = hashlib.sha256(fp.read_bytes()).hexdigest()
            except OSError:
                out[rel] = "UNREADABLE"
    return out


def diff_manifest(before: dict[str, str], after: dict[str, str]) -> tuple[set[str], set[str], set[str]]:
    b, a = set(before), set(after)
    added = a - b
    removed = b - a
    changed = {k for k in (a & b) if before[k] != after[k]}
    return added, removed, changed


# ---------------------------------------------------------------------------
# orchestrator boot (mirror OrchestratorSupervisor.launchAndConnect)
# ---------------------------------------------------------------------------
def clean_state() -> None:
    sd = state_dir_for(SCRATCH)
    if sd.exists():
        shutil.rmtree(sd)


def boot_orchestrator() -> subprocess.Popen:
    canonical_project = canonical(SCRATCH)
    sd = state_dir_for(SCRATCH)
    env = {
        **os.environ,
        # exactly what OrchestratorSupervisor sets:
        "ARCHON_V3": "1",
        "ARCHON_PROJECT_DIR": canonical_project,
        "ARCHON_STATE_DIR": str(sd),
        "PYTHONUNBUFFERED": "1",
        # E2E-only: deterministic offline PTY stub (writes nothing to the project).
        "ARCHON_V3_ADAPTER": "sleep",
        "ARCHON_V3_STUB_HOLD_S": "2.0",
    }
    log = ORCH_LOG.open("w")
    proc = subprocess.Popen(
        [str(VENV_PY), "-m", "orchestrator.v3", "--project", canonical_project],
        cwd=str(REPO),
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    return proc


def wait_for_runtime(timeout_s: float = 20.0) -> dict[str, Any]:
    rt = state_dir_for(SCRATCH) / "runtime.json"
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if rt.is_file():
            try:
                return json.loads(rt.read_text())
            except (OSError, ValueError):
                pass
        time.sleep(0.1)
    raise StepFail("runtime.json did not appear")


# ---------------------------------------------------------------------------
# REST helpers
# ---------------------------------------------------------------------------
def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Archon-Protocol-Version": "1"}


# ---------------------------------------------------------------------------
# WS helper
# ---------------------------------------------------------------------------
class WS:
    def __init__(self, port: int, token: str):
        self.uri = f"ws://127.0.0.1:{port}/v3/stream?token={token}&pv={PV}"
        self.ws = None

    async def __aenter__(self):
        self.ws = await websockets.connect(self.uri, open_timeout=10)
        return self

    async def __aexit__(self, *exc):
        if self.ws is not None:
            await self.ws.close()

    async def recv(self, timeout: float = 5.0) -> dict[str, Any]:
        raw = await asyncio.wait_for(self.ws.recv(), timeout=timeout)
        return json.loads(raw)

    async def send(self, obj: dict[str, Any]) -> None:
        await self.ws.send(json.dumps(obj))

    async def recv_until(self, pred, timeout: float = 8.0, collect=None) -> list[dict[str, Any]]:
        """Collect frames until ``pred(frame)`` is true; return all frames seen."""
        got: list[dict[str, Any]] = []
        deadline = time.time() + timeout
        while time.time() < deadline:
            frame = await self.recv(timeout=max(0.1, deadline - time.time()))
            if collect is None or collect(frame):
                got.append(frame)
            if pred(frame):
                return got
        raise StepFail("recv_until timed out")


# ===========================================================================
# steps
# ===========================================================================
async def run_all() -> None:
    canonical_project = canonical(SCRATCH)
    sd = state_dir_for(SCRATCH)

    # --- Step 3: bootstrap handshake ---------------------------------------
    rt = wait_for_runtime()
    rt_path = sd / "runtime.json"
    mode = stat.S_IMODE(rt_path.stat().st_mode)
    check("3.runtime_0600", mode == 0o600, f"runtime.json mode={oct(mode)}")
    check("3.runtime_fields",
          rt.get("pv") == PV and "token" in rt and "port" in rt
          and rt.get("project_id") == project_id_for(SCRATCH),
          f"pv={rt.get('pv')} port={rt.get('port')} project_id_matches")
    port, token = rt["port"], rt["token"]

    async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}/v3", headers=headers(token), timeout=15) as cx:
        # health (token works)
        h = await cx.get("/health")
        hj = h.json()
        check("3.health_ok", h.status_code == 200 and hj.get("status") in ("ok", "degraded", "starting")
              and hj.get("pv") == PV, f"status={hj.get('status')} pv={hj.get('pv')}")
        # health without token → 401
        no = await cx.get("/health", headers={"Archon-Protocol-Version": "1", "Authorization": ""})
        check("3.health_no_token_401", no.status_code == 401, f"status={no.status_code}")
        # project returns the scratch dir
        pj = (await cx.get("/project")).json()
        check("3.project_path", canonical(Path(pj["path"])) == canonical_project,
              f"path={pj.get('path')} is_repo={pj.get('git', {}).get('is_repo')}")

        # --- Step 4: WS hello + heartbeat + resume gap-free replay ---------
        # 4a hello + heartbeat (via ping→pong)
        async with WS(port, token) as ws:
            hello = await ws.recv()
            check("4.hello", hello.get("type") == "hello" and hello["payload"].get("pv") == PV
                  and hello["payload"].get("resume_supported") is True,
                  f"current_seq={hello['payload'].get('current_seq')}")
            await ws.send({"type": "ping", "id": "c-1"})
            hb = await ws.recv_until(lambda f: f.get("type") == "heartbeat")
            hbf = hb[-1]
            check("4.heartbeat", hbf.get("type") == "heartbeat" and hbf["payload"].get("pong") == "c-1"
                  and "current_seq" in hbf["payload"], f"pong ok current_seq={hbf['payload'].get('current_seq')}")

        # 4b force disconnect + resume(after_seq) → gap-free replay
        async with WS(port, token) as ws_a:
            hello_a = await ws_a.recv()
            base_seq = hello_a["payload"]["current_seq"]
            # generate 3 real events (kanban creates) on this socket
            created_ids = []
            for i in range(3):
                r = await cx.post("/kanban/cards", json={"title": f"resume-card-{i}", "column": "queued"})
                created_ids.append(r.json()["card"]["card_id"])
            evs_a = await ws_a.recv_until(
                lambda f: f.get("type") == "kanban_updated" and f["payload"].get("card", {}).get("card_id") == created_ids[-1],
                collect=lambda f: f.get("type") == "kanban_updated",
            )
            seqs_a = [e["seq"] for e in evs_a]
        # WS_A is now force-closed. Reconnect and resume from base_seq.
        async with WS(port, token) as ws_b:
            await ws_b.recv()  # hello
            await ws_b.send({"type": "resume", "after_seq": base_seq})
            replay = await ws_b.recv_until(
                lambda f: f.get("type") == "kanban_updated" and f["payload"].get("card", {}).get("card_id") == created_ids[-1],
                collect=lambda f: f.get("type") == "kanban_updated" and f.get("seq") is not None,
            )
            replay_seqs = [e["seq"] for e in replay]
        gap_free = replay_seqs == list(range(replay_seqs[0], replay_seqs[0] + len(replay_seqs)))
        covers = set(seqs_a).issubset(set(replay_seqs)) and all(s > base_seq for s in replay_seqs)
        check("4.resume_gapfree", gap_free and covers,
              f"live_seqs={seqs_a} replay_seqs={replay_seqs} base={base_seq}")

        # --- Step 5: kanban CRUD with live event assertions ----------------
        async with WS(port, token) as ws:
            await ws.recv()  # hello

            async def next_kanban(op_expected: str, card_id_expected: str | None = None):
                def match(f):
                    if f.get("type") != "kanban_updated":
                        return False
                    p = f["payload"]
                    if p.get("op") != op_expected:
                        return False
                    if card_id_expected is not None:
                        cid = p.get("card_id") or p.get("card", {}).get("card_id")
                        return cid == card_id_expected
                    return True
                frames = await ws.recv_until(match, collect=lambda f: f.get("type") == "kanban_updated")
                return frames[-1]

            # create
            c1 = (await cx.post("/kanban/cards", json={"title": "C1", "column": "queued"})).json()["card"]
            ev = await next_kanban("created", c1["card_id"])
            check("5.create", ev["payload"]["op"] == "created", f"card_id={c1['card_id']} col={c1['column']}")
            # move queued→in_progress
            mv = (await cx.post(f"/kanban/cards/{c1['card_id']}/move",
                                json={"base_revision": c1["revision"], "to_column": "in_progress"})).json()
            ev = await next_kanban("moved", c1["card_id"])
            check("5.move", ev["payload"]["to"]["column"] == "in_progress",
                  f"{ev['payload']['from']['column']}→{ev['payload']['to']['column']}")
            c1r = mv["card"]["revision"]
            # second card in in_progress, then reorder c1
            c2 = (await cx.post("/kanban/cards", json={"title": "C2", "column": "in_progress"})).json()["card"]
            await next_kanban("created", c2["card_id"])
            ro = (await cx.post(f"/kanban/cards/{c1['card_id']}/move",
                                json={"base_revision": c1r, "to_column": "in_progress", "to_ordinal": 1})).json()
            ev = await next_kanban("moved", c1["card_id"])
            check("5.reorder", ev["payload"]["to"]["column"] == "in_progress" and ev["payload"]["card"]["ordinal"] == 1,
                  f"ordinal={ev['payload']['card']['ordinal']}")
            # delete c2
            de = await cx.request("DELETE", f"/kanban/cards/{c2['card_id']}",
                                  json={"base_revision": c2["revision"]})
            ev = await next_kanban("deleted", c2["card_id"])
            check("5.delete", de.status_code == 200 and ev["payload"]["op"] == "deleted",
                  f"deleted card_id={c2['card_id']}")

        # SQLite lives under state dir, NOT in the project
        kdb = sd / "kanban.sqlite3"
        in_project = list(SCRATCH.rglob("*.sqlite3")) + list(SCRATCH.rglob("kanban.db"))
        check("5.sqlite_location", kdb.is_file() and not in_project,
              f"db={kdb} exists={kdb.is_file()} in_project={in_project}")

        # --- Step 6: memory list/read/write + provenance guard -------------
        mem = (await cx.get("/memory")).json()
        scope_dirs = {s["scope_dir"]: s for s in mem["scopes"]}
        root_scope = scope_dirs.get(canonical_project)
        root_files = [f["filename"] for f in (root_scope["files"] if root_scope else [])]
        found_claude = root_scope and any(f["filename"] == "CLAUDE.md" for f in root_scope["files"])
        check("6.list_discovers_claude", bool(found_claude),
              f"scopes={list(scope_dirs)} root_files={root_files}")
        # No internal state files (runtime.json / *.sqlite3 / meta) may leak as memory files.
        leaked = [f for f in root_files if f in ("runtime.json", "kanban.sqlite3", "memory-meta.json")
                  or f.endswith((".sqlite3", ".tmp"))]
        check("6.no_state_leak", not leaked, f"leaked={leaked}")
        rd = (await cx.get("/memory/file", params={"scope_dir": canonical_project, "filename": "CLAUDE.md"})).json()
        check("6.read", rd["file"]["filename"] == "CLAUDE.md" and "content" in rd,
              f"revision={rd['file']['revision']} size={rd['file']['size']}")
        # write with initiator:user → 200
        new_content = rd["content"] + "\n<!-- e2e user edit -->\n"
        wr = await cx.put("/memory/file", json={
            "scope_dir": canonical_project, "filename": "CLAUDE.md", "content": new_content,
            "base_revision": rd["file"]["revision"], "base_checksum": rd["file"]["checksum"],
            "initiator": "user",
        })
        check("6.write_user_ok", wr.status_code == 200 and wr.json()["file"]["revision"] == rd["file"]["revision"] + 1,
              f"status={wr.status_code} new_rev={wr.json().get('file', {}).get('revision')}")
        # write with initiator:conductor → 403 conductor_write_forbidden
        cf = await cx.put("/memory/file", json={
            "scope_dir": canonical_project, "filename": "CLAUDE.md", "content": new_content + "x",
            "initiator": "conductor",
        })
        cfj = cf.json()
        check("6.write_conductor_403",
              cf.status_code == 403 and cfj.get("error", {}).get("code") == "conductor_write_forbidden",
              f"status={cf.status_code} code={cfj.get('error', {}).get('code')}")

        # --- Step 7: PTY session lifecycle + kill --------------------------
        async with WS(port, token) as ws:
            await ws.recv()  # hello
            # 7a lifecycle: spawn → session_spawned + pty_output(base64) → session_state(completed/done)
            sp = await cx.post("/sessions", json={
                "cwd": canonical_project, "initiator": "user", "prompt": "e2e-lifecycle",
            })
            spj = sp.json()
            sid = spj["session"]["session_id"]
            check("7.spawn", sp.status_code == 201 and spj["session"]["state"] in ("spawning", "running"),
                  f"session_id={sid} state={spj['session']['state']}")

            saw_spawned = saw_pty = False
            pty_decoded = ""
            completed = None
            deadline = time.time() + 12
            while time.time() < deadline:
                f = await ws.recv(timeout=max(0.1, deadline - time.time()))
                if f.get("session_id") != sid:
                    continue
                t = f.get("type")
                if t == "session_spawned":
                    saw_spawned = True
                elif t == "pty_output":
                    p = f["payload"]
                    if p.get("encoding") == "base64" and p.get("bytes"):
                        saw_pty = True
                        pty_decoded += base64.b64decode(p["bytes"]).decode("utf-8", "replace")
                elif t == "session_state":
                    if f["payload"].get("state") in ("completed", "failed", "killed"):
                        completed = f["payload"]
                        break
            check("7.spawned_event", saw_spawned, "session_spawned received over WS")
            check("7.pty_output_base64", saw_pty and "archon-e2e ready" in pty_decoded,
                  f"decoded={pty_decoded!r}")
            check("7.completed", completed is not None and completed.get("state") == "completed"
                  and completed.get("status") == "done" and completed.get("exit_reason") == "normal",
                  f"terminal={completed}")

            # 7b kill a genuinely-live PTY session (sleep stub holds 2s)
            sp2 = (await cx.post("/sessions", json={
                "cwd": canonical_project, "initiator": "user", "prompt": "e2e-kill",
            })).json()
            sid2 = sp2["session"]["session_id"]
            # wait until it is running, then kill within the hold window
            await asyncio.sleep(0.3)
            kr = await cx.post(f"/sessions/{sid2}/kill", json={"grace_ms": 1000, "force": True})
            check("7.kill_accepted", kr.status_code == 202 and kr.json().get("accepted") is True,
                  f"status={kr.status_code} {kr.json()}")
            killed = None
            deadline = time.time() + 8
            while time.time() < deadline:
                f = await ws.recv(timeout=max(0.1, deadline - time.time()))
                if f.get("session_id") == sid2 and f.get("type") == "session_state" \
                        and f["payload"].get("state") in ("killed", "completed", "failed"):
                    killed = f["payload"]
                    break
            check("7.killed", killed is not None and killed.get("state") == "killed"
                  and killed.get("exit_reason") == "killed",
                  f"terminal={killed}")


# ===========================================================================
# main
# ===========================================================================
def print_table() -> None:
    print("\n================ E2E RESULT TABLE ================")
    width = max((len(s) for s, _, _ in RESULTS), default=10)
    for step, status, detail in RESULTS:
        print(f"  {status:4}  {step.ljust(width)}  {detail}")
    passed = sum(1 for _, s, _ in RESULTS if s == "PASS")
    print(f"  -----> {passed}/{len(RESULTS)} PASS")
    print("=================================================\n")


def main() -> int:
    print(f"venv={VENV_PY}\nscratch={SCRATCH}\nstate_dir={state_dir_for(SCRATCH)}\n", flush=True)
    setup_scratch_project()
    clean_state()
    before = manifest(SCRATCH)
    print(f"snapshot(before): {len(before)} files", flush=True)

    proc = boot_orchestrator()
    zero_ok = False
    try:
        try:
            asyncio.run(run_all())
        except StepFail as e:
            print(f"\n!! step failed: {e}", flush=True)

        # --- Step 8: zero-footprint proof ---------------------------------
        after = manifest(SCRATCH)
        added, removed, changed = diff_manifest(before, after)
        # allowed: CLAUDE.md changed by the user-initiated memory write (§A3 b)
        allowed_changed = {"CLAUDE.md"}
        zero_ok = (added == set() and removed == set() and changed <= allowed_changed)
        record("8.zero_footprint", zero_ok,
               f"added={sorted(added)} removed={sorted(removed)} changed={sorted(changed)} (allowed={sorted(allowed_changed)})")
        # explicit: no .archon anywhere
        stray = list(SCRATCH.rglob(".archon"))
        record("8.no_dot_archon", not stray, f"stray={stray}")
    finally:
        # --- Step 10: teardown --------------------------------------------
        if proc.poll() is None:
            proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(timeout=6)
            except subprocess.TimeoutExpired:
                proc.kill()
        # runtime.json removed on clean shutdown
        rt_gone = not (state_dir_for(SCRATCH) / "runtime.json").is_file()
        record("10.runtime_cleanup", rt_gone, "runtime.json removed on shutdown")

    print_table()
    ok = all(s == "PASS" for _, s, _ in RESULTS)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
