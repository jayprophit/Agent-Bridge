"""Genesis client simulator (v0.4). ISOLATED mock consumer — NOT Genesis.

Uses ONLY the public runtime API/client SDK:
  client health -> capabilities -> create session -> submit task ->
  observe events -> handle approval -> status -> result ->
  independent file verification -> close session.

It MUST NOT import internal executor/policy classes. A static check in
tests enforces this (AST scan for forbidden imports).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

# Public interface only. (bridge/executor/policy must never appear here.)
from client import AgentRuntimeClient


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8471"
    workspace = sys.argv[2] if len(sys.argv) > 2 else "sandbox_genesis_sim"
    client = AgentRuntimeClient(base)
    print("1. health...")
    health = client.health()
    assert health["status"] in ("HEALTHY", "DEGRADED"), health
    print("   ", health["status"])
    print("2. capabilities...")
    caps = client.capabilities()
    assert "write" in caps["actions"] and "restore" in caps["actions"], caps
    print("   protocol", caps["protocol_version"], "| actions:", len(caps["actions"]))
    print("3. create session...")
    sess = client.create_session(workspace, mode="build")
    sid = sess["session_id"]
    print("   ", sid)
    print("4. submit task...")
    sub = client.submit_task(
        sid, "One JSON action per turn, ONE single line. "
        "1 write sim_ok.txt with content SIM_OK. "
        "2 read sim_ok.txt. "
        "3 finish.",
        idempotency_key="genesis-sim-001")
    tid = sub["task_id"]
    print("   ", tid)
    print("5/6. observe events + handle approvals...")
    seen: set[str] = set()
    approval_id = ""
    end = time.time() + 600
    final: dict = {}
    while time.time() < end:
        ev = client.events(sid)
        for e in ev["events"]:
            seen.add(str(e.get("event", e.get("bus_event", "?"))))
        st = client.session_status(sid)
        if st.get("pending_approvals"):
            approval_id = st["pending_approvals"][0]
            print("7. approving", approval_id)
            client.approve(sid, approval_id, "approve-once")
        tasks = st.get("tasks", {})
        if tasks.get(tid) in ("COMPLETED", "FAILED", "CANCELLED"):
            final = st
            break
        time.sleep(3)
    print("8. status:", final.get("status"))
    print("9. result + independent verification...")
    target = Path(workspace) / "sim_ok.txt"
    assert target.exists(), f"expected file missing: {target}"
    assert target.read_text(encoding="utf-8") == "SIM_OK", "content mismatch"
    print("   file verified:", target)
    print("10. close session...")
    try:
        client.delete_session(sid)
        print("    closed")
    except Exception as e:  # noqa: BLE001 - simulator must always finish cleanly
        print("    close note:", e)
    print("GENESIS_SIM_OK", "| events seen:", sorted(seen)[:8])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
