"""Human-gate E2E: BEFORE_COMPLETE holds a live Ollama task at
WAITING_FINAL_APPROVAL (no fabricated completion); accept -> COMPLETED."""
import os
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from runtime import AgentRuntime, RuntimeConfig
from tests.helpers import FakeProvider  # noqa: F401

ws = Path("sandbox_gate")
ws.mkdir(exist_ok=True)

rt = AgentRuntime(RuntimeConfig(
    allowed_workspace_roots=[str(ws.resolve())],
    human_gate="BEFORE_COMPLETE", gate_timeout_s=300))
sess = rt.create_session(str(ws), mode="build")
tid = sess.submit_task(
    "One JSON action per turn, ONE single line. "
    "1 write gate_ok.txt with content GATE_OK. "
    "2 finish.")

# wait for the gate (task thread runs the live model meanwhile)
end = time.time() + 900
held = False
while time.time() < end:
    st = sess.status_dashboard()
    if st.get("pending_final"):
        held = True
        break
    if sess.tasks[tid].status not in ("QUEUED", "PLANNING", "EXECUTING",
                                      "TESTING", "REVIEWING", "REVISING",
                                      "WAITING_APPROVAL"):
        break
    time.sleep(3)
assert held, "gate never engaged"
# held: short wait reports pending (never a fabricated completion)
pending = sess.wait_task(tid, timeout=5)
assert pending.get("pending") and pending.get("status") == "WAITING_FINAL_APPROVAL", pending
print("GATE_HELD ok")
out = sess.resolve_final(tid, "accept")
assert out["ok"]
res = sess.wait_task(tid, timeout=300)
assert res.get("status") == "COMPLETED", res
assert (ws / "gate_ok.txt").read_text() == "GATE_OK"
print("GATE_E2E_OK")
