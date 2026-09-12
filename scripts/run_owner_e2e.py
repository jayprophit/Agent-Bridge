"""Owner-mode E2E driver (supervisor side, public client only).

v0.6 public API -> Qwen worker (OWNER_FULL_ACCESS) -> owner test area.
Every worker operation carries action IDs + runtime evidence.
Independent verification follows the run.
"""
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from client import AgentRuntimeClient  # noqa: E402  public SDK only

BASE = "http://127.0.0.1:8474"
AREA = os.path.join(tempfile.gettempdir(), "ab_owner_e2e")

TASK = (
    "One JSON action per turn, each action ONE single line, no line breaks "
    "inside strings. "
    "1 capabilities action: {\"action\":\"capabilities\"}. "
    "2 mkdir task_a (exists already, must still succeed). "
    "3 write owner_tool.py with 3 flat lines: line1 import platform, "
    "line2 print platform dot system open-paren close-paren, "
    "line3 print single-quoted OWNER_TOOL_OK. "
    "4 shell with command python owner_tool.py. "
    "5 net get with url https://example.com . "
    "JSON shape: {\"action\":\"net\",\"op\":\"get\",\"url\":\"https://example.com\"}. "
    "6 browser open the same page then read its title. "
    "Shapes: {\"action\":\"browser\",\"op\":\"open\",\"url\":\"https://example.com\"} "
    "then {\"action\":\"browser\",\"op\":\"title\"}. "
    "7 write report.txt with 2 flat lines: line1 the page title you observed, "
    "line2 single-quoted REPORT_OK. "
    "8 test ONLY with command python owner_tool.py. "
    "9 status action. "
    "10 finish listing files created and evidence observed."
)


def main() -> int:
    t0 = time.time()
    c = AgentRuntimeClient(BASE, timeout=60)
    h = c.health()
    assert h["status"] in ("HEALTHY", "DEGRADED"), h
    print("SUPERVISOR: runtime", h["status"], flush=True)
    s = c.create_session(AREA, mode="build", profile="OWNER_FULL_ACCESS",
                         owner_authorized=True)
    sid = s["session_id"]
    print("SUPERVISOR: owner session", sid, flush=True)
    tid = c.submit_task(sid, TASK)["task_id"]
    end = time.time() + 1500
    final: dict = {}
    while time.time() < end:
        st = c.session_status(sid)
        status = (st.get("tasks", {}) or {}).get(tid)
        if status in ("COMPLETED", "FAILED", "CANCELLED", "ROLLED_BACK",
                      "INTERRUPTED"):
            final = st
            break
        time.sleep(5)
    dur = round(time.time() - t0, 1)
    out = {"session_id": sid, "task_id": tid, "duration_s": dur,
           "status": final, "scorecard": c.scorecard(sid),
           "timeline": c.timeline(sid).get("timeline", []),
           "manifest": c.manifest(sid),
           "events_tail": c.events(sid).get("events", [])[-40:]}
    _out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reports", "v0.8", "owner_e2e_result.json")
    with open(os.path.normpath(_out), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, default=str)
    print("SUPERVISOR: terminal",
          (final.get("tasks", {}) or {}).get(tid), f"after {dur}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
