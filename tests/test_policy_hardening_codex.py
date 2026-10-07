"""Dedicated regression tests for the five Codex-review policy findings.

Each finding is pinned by the behavior that fixed it, not by the commit that
fixed it. A future change may refactor the policy layer freely; it may not
reintroduce any of these five failures without turning this suite red:

1. Prefix grants are boundary-aware after lexical traversal resolution.
2. Session-bound subjects isolate concurrent sessions sharing one workspace.
3. Bridge and executor use one shared action-to-capability mapping.
4. Approval-driven modes grant baseline reads only; approvals authorize the rest.
5. Delete/restore are workspace-scoped policy grants, not an approval bypass.
"""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from aether_policy_bridge import (
    ACTION_CAPABILITY,
    EvalContext,
    Grant,
    PermissionId,
    PolicyEngine,
    ResourceId,
    Subject,
    action_to_capability,
    evaluate_capability_request,
    issue_session_workspace_grants,
    reset_policy_engine,
    workspace_subject,
)


def decide(engine: PolicyEngine, resource: str) -> str:
    return engine.evaluate(EvalContext(
        subject=Subject(kind="service", value="repo"),
        resource=resource,
        action=PermissionId("filesystem", "read"),
    ))


class CodexPolicyHardeningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ab_codex_policy_"))
        self.ws = self.tmp / "ws"
        self.ws.mkdir()
        reset_policy_engine()

    def tearDown(self):
        reset_policy_engine()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_prefix_grants_are_boundary_aware_after_traversal_resolution(self):
        engine = PolicyEngine()
        engine.add_grant(Grant(
            subject=Subject(kind="service", value="repo"),
            permission=PermissionId("filesystem", "read"),
            resource=ResourceId("workspace:C:/repo/**"),
            conditions=[],
            granted_by="fixture",
            granted_at=0,
            expires_at=None,
        ))
        self.assertEqual(decide(engine, "workspace:C:/repo"), "allow")
        self.assertEqual(decide(engine, "workspace:C:/repo/file.txt"), "allow")
        # A sibling name sharing the prefix is not inside the granted root.
        self.assertEqual(decide(engine, "workspace:C:/repo-other/file.txt"), "deny")
        # Traversal is resolved lexically before matching, so it cannot climb
        # out and then back in under a different name.
        self.assertEqual(decide(engine, "workspace:C:/repo/../repo-other/file.txt"), "deny")
        self.assertEqual(decide(engine, "workspace:C:/repo/sub/../file.txt"), "allow")

    def test_session_bound_grants_do_not_leak_across_sessions(self):
        issue_session_workspace_grants("session-a", str(self.ws), "AUTO_SAFE")
        target = f"workspace:{self.ws}/a.txt".replace("\\", "/")
        allowed = evaluate_capability_request(
            subject=workspace_subject(str(self.ws), "session-a"),
            capability="filesystem:write",
            resource=target,
        )
        denied = evaluate_capability_request(
            subject=workspace_subject(str(self.ws), "session-b"),
            capability="filesystem:write",
            resource=target,
        )
        self.assertTrue(allowed["allowed"], allowed)
        self.assertFalse(denied["allowed"], denied)

    def test_bridge_and_executor_share_one_action_capability_map(self):
        self.assertEqual(
            {action: (cap.service, cap.action) for action, cap in
             ((name, action_to_capability(name)) for name in ACTION_CAPABILITY)},
            ACTION_CAPABILITY,
        )
        self.assertEqual((action_to_capability("test").service, action_to_capability("test").action),
                         ("shell", "execute"))
        for action in ("read", "list", "search", "exists", "stat", "diff", "capabilities", "status"):
            self.assertEqual(action_to_capability(action).service, "filesystem")

    def test_approval_driven_modes_grant_baseline_reads_only(self):
        for mode in ("ASK_ALL_WRITES", "ASK_RISKY", "REQUIRE_APPROVAL"):
            with self.subTest(mode=mode):
                reset_policy_engine()
                issue_session_workspace_grants("session-ask", str(self.ws), mode)
                subject = workspace_subject(str(self.ws), "session-ask")
                root = f"workspace:{self.ws}".replace("\\", "/")
                for capability in ("filesystem:read", "filesystem:list"):
                    result = evaluate_capability_request(
                        subject=subject, capability=capability, resource=f"{root}/a.txt")
                    self.assertTrue(result["allowed"], (mode, capability, result))
                for capability in ("filesystem:write", "filesystem:edit",
                                   "filesystem:delete", "shell:execute"):
                    result = evaluate_capability_request(
                        subject=subject, capability=capability, resource=f"{root}/a.txt")
                    self.assertFalse(result["allowed"], (mode, capability, result))

    def test_delete_and_restore_are_workspace_scoped_policy_grants(self):
        issue_session_workspace_grants("session-a", str(self.ws), "AUTO_SAFE")
        subject = workspace_subject(str(self.ws), "session-a")
        root = f"workspace:{self.ws}".replace("\\", "/")
        for capability in ("filesystem:delete", "filesystem:restore"):
            inside = evaluate_capability_request(
                subject=subject, capability=capability, resource=f"{root}/victim.txt")
            outside = evaluate_capability_request(
                subject=subject, capability=capability, resource=f"{root}-other/victim.txt")
            self.assertTrue(inside["allowed"], (capability, inside))
            self.assertFalse(outside["allowed"], (capability, outside))


if __name__ == "__main__":
    unittest.main()
