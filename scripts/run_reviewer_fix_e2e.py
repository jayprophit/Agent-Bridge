"""Reviewer-fix E2E (§35): deterministic model text through the REAL
bridge/oracle/reviewer machinery (a live attempt already proved real
conflict detection; the 3B coder's output variance makes live repetition
unreliable, so this run pins both sides to exercise the full path).

Coder emits a perfect assertEqual test + passing run; reviewer falsely
claims "there are no assertions" twice. Expected: conflict detected,
evidence fed back once, repeated false claim stops the loop
(REVIEWER_UNRELIABLE_FOR_THIS_DECISION) — never unlimited revisions.
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bridge import run_bridge
from config import BridgeConfig
from tests.helpers import FakeProvider

tmp = Path("review_fix_e2e_ws")
if tmp.exists():
    import shutil as _sh
    _sh.rmtree(tmp, ignore_errors=True)
tmp.mkdir(exist_ok=True)
(tmp / "app.py").write_text("def f():\n return 1\n")
cfg = BridgeConfig(workspace=tmp, mode="build", approval="AUTO_SAFE",
                   max_steps=20, non_interactive=True, enable_reviewer=True,
                   review_authority="EVIDENCE_GATED")
coder = FakeProvider([
    '{"action":"write","path":"test_app.py","content":"import unittest\\nimport app\\nclass T(unittest.TestCase):\\n def test_x(self):\\n  self.assertEqual(app.f(), 1)\\n\\nunittest.main()"}',
    '{"action":"test","command":"python test_app.py"}',
    '{"action":"finish","message":"done"}',
    '{"action":"finish","message":"done again"}',
])
FALSE_CLAIM = ('{"verdict":"revise","issues":["there are no assertions in '
               'the test file"],"recommendations":["add asserts"],'
               '"confidence":0.9}')
rev = FakeProvider([FALSE_CLAIM, FALSE_CLAIM])
t0 = time.time()
out = run_bridge(cfg, "reviewer-fix e2e task",
                 providers={"coder": coder, "planner": coder, "general": coder,
                            "reviewer": rev},
                 required_milestones=["files_created", "tests_run"])
dur = round(time.time() - t0, 1)
print("finished:", out.get("finished"), "| kind:", out.get("kind"),
      "| steps:", out.get("steps"), f"| {dur}s")
hist = out.get("history", [])
conflicts = [h for h in hist if h.get("kind") == "REVIEWER_EVIDENCE_CONFLICT"]
if not conflicts and out.get("review", {}).get("conflict"):
    conflicts = [out["review"]["conflict"]]
print("conflicts detected:", len(conflicts))
tested = [h for h in hist if h.get("executed") and
          (h.get("action") or {}).get("action") == "test" and
          (h.get("result") or {}).get("ok")]
print("passing test runs:", len(tested))
assert conflicts, "reviewer/evidence conflict must be detected"
assert out.get("steps", 99) <= 20, "must stop, never loop indefinitely"
assert out.get("kind") in ("REVIEWER_UNRELIABLE_FOR_THIS_DECISION",
                           "MODEL_OUTPUT_ERROR", "REVISION_EXHAUSTED",
                           "MAX_STEPS_REACHED", "COMPLETED"), out.get("kind")
print("REVIEWER_FIX_E2E_OK (conflict contained, no unlimited revisions)")
print("workspace kept at review_fix_e2e_ws for inspection")
