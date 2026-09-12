"""Genesis Simulator V2 (v0.5): behaves like a future application.

Discovery -> health -> model inventory -> workspace/mode selection ->
task submission -> SSE/poll events -> approvals -> status -> diff ->
manifest -> scorecard -> final result -> optional rollback.
PUBLIC SDK/API ONLY (AST-enforced in tests).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

# Public interface only.
from client import AgentRuntimeClient


def wait_done(client: AgentRuntimeClient, sid: str, tid: str,
              timeout: float = 900.0) -> dict:
    end = time.time() + timeout
    last: dict = {}
    while time.time() < end:
        st = client.session_status(sid)
        last = st
        for aid in st.get("pending_approvals", []) or []:
            client.approve(sid, aid, "deny")  # simulator policy: deny unknowns
        tasks = st.get("tasks", {}) or {}
        if tasks.get(tid) in ("COMPLETED", "FAILED", "CANCELLED",
                              "ROLLED_BACK", "INTERRUPTED"):
            return st
        time.sleep(3)
    return last


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8471"
    workspace = sys.argv[2] if len(sys.argv) > 2 else "sandbox_simv2"
    client = AgentRuntimeClient(base)
    print("DISCOVERY", base)
    health = client.health()
    assert health["status"] in ("HEALTHY", "DEGRADED"), health
    print("HEALTH", health["status"], "| Ollama:",
          health["checks"].get("ollama", {}).get("status"))
    inv = client.models()
    names = [m.get("name") for m in inv.get("models", [])]
    print("INVENTORY", len(names), "local model(s)")
    assert names, "need at least one local model"
    caps = client.capabilities()
    print("PROTOCOL", caps.get("protocol_version"), "| MODES", caps.get("modes"))
    sess = client.create_session(workspace, mode="build")
    sid = sess["session_id"]
    print("SESSION", sid)
    sub = client.submit_task(
        sid, "One JSON action per turn, ONE single line. "
        "1 write notes_app.py with 5 flat lines: line1 import json, "
        "line2 NOTES equals empty list, line3 def add_note(t):, "
        "line4 4-space NOTES dot append open-paren t close-paren, "
        "line5 a print statement showing NOTES_OK. "
        "2 write check_notes.py with 4 flat lines: line1 import notes_app, "
        "line2 notes_app dot add_note open-paren hello close-paren, "
        "line3 assert notes_app dot NOTES equals list containing hello, "
        "line4 a print statement showing CHECK_OK. "
        "Python code must contain only statements starting with import, "
        "assert, def, return, or print, with string literals in single "
        "quotes. "
        "3 test ONLY with command python check_notes.py and repeat it until "
        "it passes, fixing check_notes.py itself when the error names that "
        "file. "
        "4 finish.")
    tid = sub["task_id"]
    print("TASK", tid)
    st = wait_done(client, sid, tid)
    assert st.get("tasks", {}).get(tid) == "COMPLETED", st.get("tasks")
    print("STATUS COMPLETED")
    d = client.diff(sid)
    assert "notes_app" in d.get("diff", ""), "diff should show the app"
    print("DIFF ok")
    man = client.manifest(sid)
    paths = [c.get("path") for c in man.get("changes", [])]
    assert any("notes_app" in p for p in paths), paths
    print("MANIFEST ok:", len(paths), "entries")
    sc = client.scorecard(sid)
    print("SCORECARD:", {k: v.get("status") for k, v in
                         sc.get("scorecard", {}).get("categories", {}).items()})
    tl = client.timeline(sid)
    assert len(tl.get("timeline", [])) > 3
    print("TIMELINE entries:", len(tl["timeline"]))
    target = Path(workspace) / "notes_app.py"
    assert target.exists(), "notes utility missing"
    import subprocess
    p = subprocess.run(["python", str(target)], capture_output=True, text=True,
                       timeout=60)
    assert p.returncode == 0, p  # module imports cleanly (prints on call)
    check = Path(workspace) / "check_notes.py"
    p2 = subprocess.run(["python", str(check)], capture_output=True, text=True,
                        timeout=60)
    assert p2.returncode == 0 and "CHECK_OK" in p2.stdout, p2
    assert "NOTES_OK" in p2.stdout, p2  # app's own marker via the check
    print("INDEPENDENT VERIFY ok")
    try:
        client.delete_session(sid)
    except Exception as e:  # noqa: BLE001
        print("close note:", e)
    print("GENESIS_SIM_V2_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
