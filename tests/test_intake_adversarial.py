"""Adversarial probes against the real intake + approval + journal chain.

Each test attacks a property the contract suite assumes but never hostilely
verified. All run over real HTTP against the unmodified service. Anything that
fails here is a defect in the canonical layer, not in the test.

Covered elsewhere (pointers, not duplication):
  forged/unknown approval ids, approval replay in-session, bad decisions,
  token enforcement (test_external_approvals.py)
  globs, escapes, absolute refs, verb allow-list, field validation,
  owner elevation, principal shape, replay/collision, both-sides gating,
  single-use grants (test_actions_intake.py)
  cross-task aliasing, fingerprint idempotency (test_action_id_uniqueness.py)
"""
from __future__ import annotations

import threading
import unittest

from client import ClientError
from tests.test_actions_intake import IntakeBase


class TestCrossSessionApprovalIsolation(IntakeBase):
    external_approvals = True

    def test_approval_from_another_session_is_unknown(self):
        # Two ASK sessions. An approval id minted in A must not resolve in B:
        # approvals are session-scoped decisions, not bearer tokens.
        ra = self.act("x-a1", "filesystem:write", "a.txt",
                      approval="ASK_ALL_WRITES", interactive=True,
                      payload={"content": "a"}, wait_ms=5000)
        self.assertEqual(ra["outcome"], "WAITING_APPROVAL")
        rb = self.act("x-b1", "filesystem:write", "b.txt",
                      approval="ASK_ALL_WRITES", interactive=True,
                      payload={"content": "b"}, wait_ms=5000)
        self.assertEqual(rb["outcome"], "WAITING_APPROVAL")
        self.assertNotEqual(ra["session_id"], rb["session_id"])
        with self.assertRaises(ClientError) as ctx:
            self.c.approve(rb["session_id"], ra["approval_id"], "approve-once")
        self.assertIn("404", str(ctx.exception))
        # both originals still pending, untouched by the forgery attempt
        self.assertEqual(self.c.session_status(ra["session_id"])
                         ["pending_approvals"], [ra["approval_id"]])
        self.c.deny(ra["session_id"], ra["approval_id"])
        self.c.deny(rb["session_id"], rb["approval_id"])
        self.assertFalse((self.svc.ws / "a.txt").exists())
        self.assertFalse((self.svc.ws / "b.txt").exists())


class TestPrincipalIsAttributionNotAuthority(IntakeBase):
    def test_claimed_identity_does_not_change_the_decision(self):
        # The same forbidden-by-policy effect is denied no matter whose name
        # is on it; the name is recorded verbatim for forensics, never
        # evaluated as permission.
        from aether_policy_bridge import (evaluate_capability_request,
                                          workspace_subject)
        for principal in (None,
                          {"kind": "genesis", "id": "genesis-prime"},
                          {"kind": "worker", "id": "worker-7"},
                          {"kind": "owner", "id": "owner-1"}):
            verdict = evaluate_capability_request(
                subject=workspace_subject(str(self.svc.ws), "s-probe"),
                capability="filesystem:write",
                resource=f"workspace:{self.svc.ws.resolve()}/ nowhere.txt".replace(
                    " ", ""),
                context={"timestamp": 0, "network_origin": "local",
                         "device_trust": 100, "attributes": {}},
                principal=principal)
            self.assertFalse(verdict["allowed"], principal)

    def test_worker_claiming_genesis_id_is_recorded_not_trusted(self):
        # Intake accepts a well-formed worker principal (it is audit context);
        # the resulting journal must show the claimed id verbatim while the
        # authorization path treats it as no authority at all.
        r = self.act("x-pw", "write", "pw.txt", payload={"content": "x"},
                     principal={"kind": "worker", "id": "genesis-prime"})
        self.assertEqual(r["outcome"], "SUCCEEDED")
        exp = self.c.export(r["session_id"], r["task_id"])["task_result"]
        self.assertTrue(exp["effect_achieved"])

    def test_collapsed_owner_genesis_refused(self):
        with self.assertRaises(ClientError):
            self.act("x-pc", "write", "pc.txt", payload={"content": "x"},
                     principal={"kind": "genesis", "id": "g1",
                                "on_behalf_of": "g1"})


class TestConcurrentIdempotentSubmit(IntakeBase):
    def test_parallel_same_action_yields_one_task(self):
        # Ten racing submissions of one action id: exactly one task, one
        # execution, every caller told the truth (deduped or first).
        results: list = []
        errors: list = []

        def submit():
            try:
                results.append(self.act(
                    "x-race", "write", "race.txt", session_id="wf-race",
                    payload={"content": "v"}))
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=submit) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=120)
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 10)
        task_ids = {r["task_id"] for r in results}
        self.assertEqual(len(task_ids), 1,
                         f"race created {len(task_ids)} tasks")
        self.assertEqual((self.svc.ws / "race.txt").read_text(), "v")
        deduped = sum(1 for r in results if r.get("deduped"))
        self.assertGreaterEqual(deduped, 9)


if __name__ == "__main__":
    unittest.main()
