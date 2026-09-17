"""ONE live delegated runtime-closure run (evidence script, not unit test).

Task: fix an off-by-one bug via the wired run_bridge. Records the full
§4 evidence set: task ID, plan version, supervisor, Bridge, worker, model,
provider, execution mode, bounded unit, result, verification,
re-evaluation, adaptation decision, checkpoint, final status.
"""
import json
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from bridge import BridgeConfig, run_bridge
from config import ContextSettings

WORKSPACE = Path(__file__).parent
FIX_DIR = WORKSPACE / "delegation_test_fixtures"
FIX_DIR.mkdir(exist_ok=True)
FIXTURE = FIX_DIR / "closure_task.py"
FIXTURE.write_text(
    '"""Live closure fixture: off-by-one bug for the worker to fix."""\n'
    "\n"
    "def total(items):\n"
    '    """Sum a list - INTENTIONAL BUG for worker to fix."""\n'
    "    s = 0\n"
    "    for i in range(len(items) - 1):  # BUG: skips last element\n"
    "        s += items[i]\n"
    "    return s\n"
    "\n"
    "\n"
    "def test_total():\n"
    "    assert total([]) == 0\n"
    "    assert total([4]) == 4  # FAILS with bug\n"
    "    assert total([1, 2, 3]) == 6  # FAILS with bug\n"
    '    return "ALL_TESTS_PASS"\n',
    encoding="utf-8")

TASK = (
    "Fix the off-by-one bug in delegation_test_fixtures/closure_task.py "
    "using the edit action with exact old/new strings. "
    "The function total(items) has the bug "
    "'for i in range(len(items) - 1):' which skips the last element; "
    "change it to 'for i in range(len(items)):'. "
    "Do NOT use the write action on existing files (it will be denied); "
    "use edit with exact anchors. "
    "Then create delegation_test_fixtures/run_check.py with content "
    "'from closure_task import total\\nassert total([1, 2, 3]) == 6\\n"
    "assert total([4]) == 4\\nprint(1)\\n' using the write action "
    "(new file), then run the test action "
    "'python delegation_test_fixtures/run_check.py' to verify, "
    "then finish."
)

cfg = BridgeConfig(
    model="qwen2.5-coder:3b-instruct-q4_K_M",
    mode="hybrid",
    approval="AUTO_SAFE",
    workspace=WORKSPACE,
    ollama_url="http://127.0.0.1:11434",
    request_timeout_s=180,
    context=ContextSettings(budget_chars=8000, keep_recent_results=3),
    enable_reviewer=False,
    shell_profile="dev",
    non_interactive=True,
    dry_run=False,
    session_id="closure-" + uuid.uuid4().hex[:8],
    task_id="task-closure-1",
    max_steps=16,
)

t0 = time.time()
out = run_bridge(cfg, TASK)
dur = round(time.time() - t0, 1)

executed = [h for h in out.get("history", []) if h.get("executed")]
mutations = [h for h in executed
             if (h.get("action", {}) or {}).get("action")
             in ("write", "edit", "patch", "copy", "move", "test", "shell")]
passing = [h for h in executed
           if (h.get("action", {}) or {}).get("action") == "test"
           and (h.get("result") or {}).get("ok")]
models = {h.get("model") for h in executed if h.get("model")}

evidence = {
    "task_id": cfg.task_id,
    "session_id": out.get("session_id"),
    "plan_version": (out.get("contract") or {}).get("plan_version"),
    "supervisor": "opencode",
    "bridge": "run_bridge wired runtime",
    "selected_worker": sorted(models),
    "model": cfg.model,
    "provider": "ollama",
    "execution_mode": "DELEGATED",
    "bounded_units": len(mutations),
    "steps": out.get("steps"),
    "result": out.get("message", "")[:300],
    "verification": (out.get("contract") or {}).get("state"),
    "passing_tests": len(passing),
    "adaptation_decision": "COMPLETE" if out.get("finished") else "BLOCKED",
    "checkpoint": str(WORKSPACE / ".bridge" / "sessions" / out.get("session_id", "")
                      / "contract.json"),
    "final_status": out.get("status"),
    "finished": out.get("finished"),
    "duration_s": dur,
    "contract": out.get("contract"),
}
cert_dir = WORKSPACE / ".bridge" / "delegation_cert"
cert_dir.mkdir(parents=True, exist_ok=True)
(evidence_path := cert_dir / "RUNTIME_CLOSURE_EVIDENCE.json").write_text(
    json.dumps(evidence, indent=2, default=str), encoding="utf-8")

print(json.dumps({k: v for k, v in evidence.items() if k != "contract"},
                 indent=2))
print("contract state:", (out.get("contract") or {}).get("state"))
print("evidence:", evidence_path)
if not out.get("finished"):
    print("LIVE RUN DID NOT FINISH")
    sys.exit(1)
if (out.get("contract") or {}).get("state") != "COMPLETE":
    print("CONTRACT NOT COMPLETE")
    sys.exit(1)
print("LIVE CLOSURE OK")
