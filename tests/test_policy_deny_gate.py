"""P14-E2E-FAIL: failure paths around the MAT -> Bridge -> Genesis chain.

1. Policy-deny gate (P10-PA): an ungranted subject/capability is denied
   BEFORE execution; an explicit grant allows. Uses the shared bridge
   policy engine (default-deny).
2. MAT-unavailable path: an unknown symbol reports found=false (exit 0)
   so the chain never feeds garbage into an envelope/host call.

Skips cleanly when node or the MAT checkout is absent.
"""
import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

import sys
sys.path.insert(0, str(REPO_ROOT))

from aether_policy_bridge import (
    Grant,
    PermissionId,
    Subject,
    check_capability,
    evaluate_capability_request,
    get_policy_engine,
    reset_policy_engine,
)


def _mat_root() -> Path | None:
    env = os.environ.get("MAT_ROOT", "")
    candidates = []
    if env:
        candidates.append(Path(env))
    candidates.append(REPO_ROOT.parent / "Materials-Atlas-Table-Codex---MAT")
    for candidate in candidates:
        if (candidate / "scripts" / "mat-query-service.mjs").exists():
            return candidate
    return None


class PolicyDenyGateTests(unittest.TestCase):
    def setUp(self):
        reset_policy_engine()

    def tearDown(self):
        reset_policy_engine()

    def test_ungranted_capability_denied_before_execution(self):
        res = evaluate_capability_request(
            subject="service:agent-bridge",
            capability="filesystem:write",
            resource="/tmp/p14_proof.txt",
            context={"timestamp": 0},
        )
        self.assertFalse(res["allowed"])
        self.assertEqual(res["decision"], "deny")
        self.assertIn("policy_id", res)
        # Deny happens at evaluation time: caller must not execute.
        executed = False
        if res["allowed"]:
            executed = True
        self.assertFalse(executed)

    def test_explicit_grant_allows(self):
        engine = get_policy_engine()
        engine.add_grant(Grant(
            subject=Subject.service("agent-bridge"),
            permission=PermissionId("mat", "query"),
            resource="mat:MAT:0001",
            conditions=[],
            granted_by="owner",
            granted_at=0,
            expires_at=None,
        ))
        res = check_capability(
            subject="service:agent-bridge",
            capability="mat:query",
            resource="mat:MAT:0001",
        )
        self.assertTrue(res["allowed"])
        self.assertEqual(res["decision"], "allow")

    def test_deny_is_subject_scoped(self):
        # Grant covers agent-bridge only; a stranger is still denied.
        engine = get_policy_engine()
        engine.add_grant(Grant(
            subject=Subject.service("agent-bridge"),
            permission=PermissionId("mat", "query"),
            resource="mat:MAT:0001",
            conditions=[],
            granted_by="owner",
            granted_at=0,
            expires_at=None,
        ))
        res = check_capability(
            subject="service:stranger",
            capability="mat:query",
            resource="mat:MAT:0001",
        )
        self.assertFalse(res["allowed"])


class MatUnavailableTests(unittest.TestCase):
    def test_unknown_symbol_reports_not_found(self):
        if shutil.which("node") is None:
            self.skipTest("node unavailable")
        mat = _mat_root()
        if mat is None:
            self.skipTest("MAT checkout absent")
        query = subprocess.run(
            ["node", "scripts/mat-query-service.mjs",
             "--symbol", "Xx", "--property", "ionization.first"],
            capture_output=True, text=True, timeout=120, cwd=str(mat))
        self.assertEqual(query.returncode, 0, query.stderr[:300])
        response = json.loads(query.stdout)
        self.assertFalse(response["found"])
        # No results: nothing may be packaged into an envelope.
        self.assertEqual(response.get("results", []), [])


if __name__ == "__main__":
    unittest.main()
