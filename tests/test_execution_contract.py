"""Phase 1.1 hard-enforcement tests: the policy itself, not helpers.

Covers all 19 required scenarios (§16). Fail-closed is asserted by
provoking each bypass and requiring ExecutionPolicyViolation.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from execution_contract import (
    ADAPT_PLAN, BLOCK_WITH_EVIDENCE, COMPLETE, CONTINUE_CURRENT_PLAN,
    CREATE_NEW_SUBTASK, EXECUTING, FAILED, ILLEGAL_TRANSITION,
    OWNER_REVIEW_REQUIRED, PLAN_MISSING, RECEIVED, REEVALUATION_MISSING,
    REEVALUATING, RETRY_WITH_CHANGE, ROUTE_TO_DIFFERENT_MODEL, VERIFIED,
    VERIFICATION_MISSING, BuilderAdapter, ExecutionContract,
    ExecutionPolicyViolation, GenesisAdapter, REEVALUATION_QUESTIONS,
    ScriptedBuilderAdapter,
)

LIGHT = {"objective": "o", "change": "c", "expected_result": "e",
         "verify": "v"}
FULLPLAN = {"objective": "o", "current_state": "s", "requirements": "r",
            "constraints": "c", "dependencies": "d", "risks": "r",
            "unknowns": "u", "steps": "s", "evidence_requirements": "e",
            "acceptance": "a"}


def _findings(decision_hint: str = "no") -> dict[str, str]:
    return {q: decision_hint for q in REEVALUATION_QUESTIONS}


def _drive(c: ExecutionContract, tid: str, verdict: str,
           decision: str, author: str = "t") -> None:
    c.recover_context(tid)
    c.plan(tid, dict(LIGHT), depth="LIGHTWEIGHT", author=author)
    c.mark_ready(tid)
    c.begin_execute(tid)
    c.capture_result(tid, "result")
    c.begin_verify(tid)
    c.record_verification(tid, verdict, ["e1"], verifier="tester")
    c.begin_reevaluate(tid)
    c.record_reevaluation(tid, _findings(), decision, ["e1"], author=author)


class TestFailClosed(unittest.TestCase):
    def test_01_no_plan_no_execute(self):
        c = ExecutionContract()
        t = c.receive()
        c.recover_context(t)
        with self.assertRaises(ExecutionPolicyViolation) as ctx:
            c.begin_execute(t)
        self.assertEqual(ctx.exception.reason, PLAN_MISSING)

    def test_02_lightweight_plan_for_tiny_task(self):
        c = ExecutionContract()
        t = c.receive(substantive=False)
        c.recover_context(t)
        plan = c.plan(t, dict(LIGHT))  # depth auto: LIGHTWEIGHT
        self.assertEqual(plan.depth, "LIGHTWEIGHT")
        self.assertEqual(plan.version, 1)

    def test_02b_substantive_requires_full_plan_fields(self):
        c = ExecutionContract()
        t = c.receive(substantive=True)
        c.recover_context(t)
        # substantive default depth is FULL; a thin field set is rejected
        with self.assertRaises(ExecutionPolicyViolation) as ctx:
            c.plan(t, dict(LIGHT))
        self.assertEqual(ctx.exception.reason, PLAN_MISSING)
        # a complete FULL plan is accepted
        plan = c.plan(t, dict(FULLPLAN))
        self.assertEqual(plan.depth, "FULL")

    def test_03_execution_produces_result(self):
        c = ExecutionContract()
        t = c.receive()
        _drive(c, t, VERIFIED, CONTINUE_CURRENT_PLAN)
        rec = c.reevaluations[-1]
        self.assertEqual(rec.decision, CONTINUE_CURRENT_PLAN)
        self.assertEqual(c.state_of(t), CONTINUE_CURRENT_PLAN)

    def test_04_no_completion_without_verification(self):
        c = ExecutionContract()
        t = c.receive()
        c.recover_context(t)
        c.plan(t, dict(LIGHT), depth="LIGHTWEIGHT")
        c.mark_ready(t)
        c.begin_execute(t)
        c.capture_result(t, "r")
        # skip verification -> COMPLETE decision must be rejected
        c.begin_verify(t)
        c.record_verification(t, FAILED, ["e1"])
        c.begin_reevaluate(t)
        with self.assertRaises(ExecutionPolicyViolation) as ctx:
            c.record_reevaluation(t, _findings(), COMPLETE, ["e1"])
        self.assertEqual(ctx.exception.reason, VERIFICATION_MISSING)

    def test_05_verification_requires_reevaluation(self):
        c = ExecutionContract()
        t = c.receive()
        _drive(c, t, VERIFIED, CONTINUE_CURRENT_PLAN)
        # finalize() without a COMPLETE decision is rejected...
        with self.assertRaises(ExecutionPolicyViolation) as ctx:
            c.finalize(t)
        self.assertEqual(ctx.exception.reason, REEVALUATION_MISSING)

    def test_06_failed_test_triggers_reevaluation(self):
        c = ExecutionContract()
        t = c.receive()
        c.recover_context(t)
        c.plan(t, dict(LIGHT), depth="LIGHTWEIGHT")
        c.mark_ready(t)
        c.begin_execute(t)
        c.capture_result(t, "r")
        c.begin_verify(t)
        c.record_verification(t, FAILED, ["trace"])
        self.assertTrue(c.pending_reevaluation(t))
        c.begin_reevaluate(t)
        rec = c.record_reevaluation(t, _findings("yes"), RETRY_WITH_CHANGE)
        self.assertEqual(rec.decision, RETRY_WITH_CHANGE)

    def test_07_success_still_requires_reevaluation(self):
        c = ExecutionContract()
        t = c.receive()
        c.recover_context(t)
        c.plan(t, dict(LIGHT), depth="LIGHTWEIGHT")
        c.mark_ready(t)
        c.begin_execute(t)
        c.capture_result(t, "r")
        c.begin_verify(t)
        c.record_verification(t, VERIFIED, ["e1"])
        self.assertTrue(c.pending_reevaluation(t))

    def test_08_new_evidence_modifies_plan(self):
        c = ExecutionContract()
        t = c.receive()
        _drive(c, t, VERIFIED, ADAPT_PLAN)
        v2 = c.plan(t, dict(LIGHT, change="c2"))
        self.assertEqual(v2.version, 2)
        self.assertTrue(v2.supersedes)
        hist = c.plan_history(t)
        self.assertEqual([p.version for p in hist], [1, 2])

    def test_09_owner_amendment_new_plan_version(self):
        c = ExecutionContract()
        t = c.receive(substantive=False)
        c.recover_context(t)
        c.plan(t, dict(LIGHT), author="worker")
        c.mark_ready(t)
        v2 = c.plan(t, dict(LIGHT, change="owner scope change"),
                    author="owner")
        self.assertEqual(v2.version, 2)
        self.assertEqual(len(c.plan_history(t)), 2)

    def test_10_timeout_triggers_adaptive_decision(self):
        c = ExecutionContract()
        t = c.receive()
        _drive(c, t, FAILED, ROUTE_TO_DIFFERENT_MODEL)
        self.assertEqual(c.telemetry.snapshot()["reroutes"], 1)
        self.assertEqual(c.state_of(t), ROUTE_TO_DIFFERENT_MODEL)

    def test_11_model_change_keeps_plan_state(self):
        c = ExecutionContract()
        t = c.receive()
        _drive(c, t, FAILED, ROUTE_TO_DIFFERENT_MODEL)
        v2 = c.plan(t, dict(LIGHT, change="retry on qwen3"))
        self.assertEqual(v2.version, 2)
        self.assertEqual(c.plan_history(t)[0].fields["change"], "c")

    def test_12_direct_execution_follows_lifecycle(self):
        c = ExecutionContract()
        t = c.receive()
        adapter = BuilderAdapter(c, execute_fn=lambda tid, plan: "direct edit")
        adapter.contract.recover_context(t)
        rec = adapter.run_unit(t, dict(LIGHT), _findings(), CONTINUE_CURRENT_PLAN,
                               depth="LIGHTWEIGHT")
        self.assertEqual(rec.decision, CONTINUE_CURRENT_PLAN)

    def test_13_delegated_execution_follows_lifecycle(self):
        c = ExecutionContract()
        t = c.receive()
        adapter = ScriptedBuilderAdapter(
            c, {"result": "worker diff", "verdict": VERIFIED,
                "evidence": ["diff-hash"]})
        adapter.contract.recover_context(t)
        rec = adapter.run_unit(t, dict(LIGHT), _findings(), COMPLETE,
                               depth="LIGHTWEIGHT", evidence=["diff-hash"])
        self.assertEqual(rec.decision, COMPLETE)
        self.assertEqual(c.finalize(t), COMPLETE)

    def test_14_restart_preserves_stage(self):
        tmp = Path(tempfile.mkdtemp(prefix="ec_"))
        try:
            path = tmp / "contract.json"
            c = ExecutionContract(path)
            t = c.receive()
            c.recover_context(t)
            c.plan(t, dict(LIGHT), depth="LIGHTWEIGHT")
            c.mark_ready(t)
            c.begin_execute(t)
            c2 = ExecutionContract(path)
            self.assertEqual(c2.state_of(t), EXECUTING)
            self.assertEqual(c2.current_plan(t).version, 1)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_15_504_preserves_stage(self):
        tmp = Path(tempfile.mkdtemp(prefix="ec504_"))
        try:
            path = tmp / "contract.json"
            c = ExecutionContract(path)
            t = c.receive()
            c.recover_context(t)
            c.plan(t, dict(LIGHT), depth="LIGHTWEIGHT")
            before = c.to_dict()
            path.write_text("{corrupt", encoding="utf-8")  # simulated 504 body
            c.load()
            self.assertEqual(c.to_dict(), before)
            self.assertEqual(c.state_of(t), "PLANNED")
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_16_external_builder_cannot_bypass(self):
        c = ExecutionContract()
        t = c.receive()
        adapter = ScriptedBuilderAdapter(c, {"result": "x"})
        with self.assertRaises(ExecutionPolicyViolation):
            adapter.execute_unit(t)  # no context, no plan
        # verify() without result is also rejected
        with self.assertRaises(ExecutionPolicyViolation):
            adapter.verify(t)

    def test_17_genesis_adapter_same_contract(self):
        c = ExecutionContract()
        t = c.receive()
        g = GenesisAdapter(
            c,
            execute_fn=lambda tid, plan: "genesis unit",
            verify_fn=lambda tid, res: (VERIFIED, ["e1"]),
            cognition_fn=lambda tid, ctx: dict(FULLPLAN))
        g.contract.recover_context(t)
        plan = g.propose_plan(t, {"goal": "x"})
        self.assertEqual(plan.author, "genesis-cognition")
        g.contract.mark_ready(t)
        g.execute_unit(t)
        g.verify(t)
        rec = g.reevaluate(t, _findings(), CONTINUE_CURRENT_PLAN)
        self.assertEqual(rec.decision, CONTINUE_CURRENT_PLAN)
        # no cognition -> no plan -> fail closed
        c2 = ExecutionContract()
        t2 = c2.receive()
        g2 = GenesisAdapter(c2)
        c2.recover_context(t2)
        with self.assertRaises(ExecutionPolicyViolation):
            g2.propose_plan(t2, {})

    def test_18_superseded_task_not_executed(self):
        c = ExecutionContract()
        t = c.receive()
        _drive(c, t, FAILED, BLOCK_WITH_EVIDENCE, )
        self.assertEqual(c.state_of(t), BLOCK_WITH_EVIDENCE)
        with self.assertRaises(ExecutionPolicyViolation):
            c.begin_execute(t)

    def test_19_blocked_allows_independent_tasks(self):
        c = ExecutionContract()
        blocked = c.receive()
        free = c.receive()
        _drive(c, blocked, FAILED, BLOCK_WITH_EVIDENCE)
        _drive(c, free, VERIFIED, COMPLETE, )
        self.assertEqual(c.finalize(free), COMPLETE)
        self.assertEqual(c.state_of(blocked), BLOCK_WITH_EVIDENCE)

    def test_illegal_skips_rejected(self):
        c = ExecutionContract()
        t = c.receive()
        with self.assertRaises(ExecutionPolicyViolation) as ctx:
            c._guarded(t, EXECUTING)  # RECEIVED -> EXECUTING
        self.assertEqual(ctx.exception.reason, ILLEGAL_TRANSITION)
        self.assertGreaterEqual(
            c.telemetry.snapshot()["unresolved_bypasses"], 1)

    def test_telemetry_shape(self):
        c = ExecutionContract()
        snap = c.telemetry.snapshot()
        for key in ("planned_ok", "violations",
                    "completions_without_verification",
                    "missing_reevaluations", "adaptations",
                    "unchanged_continuations", "reroutes", "blocked",
                    "unresolved_bypasses"):
            self.assertIn(key, snap)


class TestRealBridgeCompatibility(unittest.TestCase):
    """The contract accepts real Agent Bridge delegation behavior.

    Replays the recorded REAL_DELEGATION_CERTIFICATION through the loop:
    the Bridge's read->edit->finish history maps onto plan->execute->
    verify->reevaluate with zero violations. This is the Bridge
    demonstration: same contract, real evidence.
    """

    def test_recorded_delegation_replays_clean(self):
        import json as _json
        from pathlib import Path as _P
        cert = _json.loads((_P(__file__).resolve().parent.parent
                            / ".bridge" / "delegation_cert"
                            / "REAL_DELEGATION_CERTIFICATION.json")
                           .read_text(encoding="utf-8"))
        verified = [r for r in cert["results"]
                    if r.get("final_status") == "VERIFIED"]
        self.assertGreaterEqual(len(verified), 1)
        for ev in verified:
            c = ExecutionContract()
            t = c.receive()
            c.recover_context(t)
            c.plan(t, {"objective": str(ev.get("task_description", ""))[:200],
                       "change": "worker-applied file edit",
                       "expected_result": "test assertions pass",
                       "verify": "run module tests"},
                   depth="LIGHTWEIGHT", author=ev.get("coder_model", ""))
            c.mark_ready(t)
            c.begin_execute(t)
            c.capture_result(
                t, f"file_changed={ev.get('file_changed')} "
                   f"steps={ev.get('steps_executed')}")
            c.begin_verify(t)
            c.record_verification(
                t, VERIFIED if ev.get("test_passed") else FAILED,
                [ev.get("bridge_session_id", "")],
                verifier=ev.get("reviewer_model", ""))
            c.begin_reevaluate(t)
            rec = c.record_reevaluation(t, _findings(), CONTINUE_CURRENT_PLAN,
                                        [ev.get("bridge_session_id", "")])
            self.assertEqual(rec.decision, CONTINUE_CURRENT_PLAN)
            snap = c.telemetry.snapshot()
            self.assertEqual(snap["planned_ok"], 1)
            self.assertEqual(snap["unresolved_bypasses"], 0)


class TestLoopDisplay(unittest.TestCase):
    def test_taskcenter_loop_state(self):
        from taskcenter import TaskCenter
        tc = TaskCenter()
        n = tc.add("profiler", assigned_model="m", execution_mode="DELEGATED")
        tc.set_loop_state(n.task_id, stage="VERIFYING", action="video probe",
                          result="metadata contradicts runtime",
                          verification="PARTIAL", reevaluation="REQUIRED",
                          next_action="run real video probe")
        node = tc.get(n.task_id)
        self.assertEqual(node.current_stage, "VERIFYING")
        self.assertEqual(node.verification, "PARTIAL")
        tree = tc.expand(n.task_id)
        self.assertEqual(tree["current_stage"], "VERIFYING")
        self.assertEqual(tree["verification"], "PARTIAL")
        html = tc.render_html(n.task_id)
        self.assertIn("VERIFYING", html)
        self.assertIn("PARTIAL", html)


if __name__ == "__main__":
    unittest.main()
