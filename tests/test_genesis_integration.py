"""Genesis 2.2 integration tests: cognition → adapter → contract lifecycle.

Tests the complete Genesis cognition pipeline:
  1. GenesisCognition produces plan fields from context
  2. GenesisAdapter routes cognition through the execution contract
  3. Full lifecycle: plan → execute → verify → reevaluate with real cognition
  4. ProblemMemory recall integration
  5. Adaptive depth selection (LIGHTWEIGHT vs FULL)
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from execution_contract import (
    CONTINUE_CURRENT_PLAN, COMPLETE, FAILED, BLOCK_WITH_EVIDENCE,
    FULL, FULL_FIELDS, LIGHTWEIGHT, LIGHTWEIGHT_FIELDS, PLAN_MISSING,
    ExecutionContract, ExecutionPolicyViolation, GenesisAdapter,
)
from genesis_cognition import GenesisCognition, CognitionMemory


# -- Test helpers -----------------------------------------------------------

LIGHT = {"objective": "o", "change": "c", "expected_result": "e",
         "verify": "v"}


def _findings(**overrides: str) -> dict[str, str]:
    base = {
        "what_changed": "test",
        "behaviour_matched_expected": "yes",
        "tests_passed": "1/1",
        "new_information": "none",
        "performance_or_resource_change": "none",
        "assumptions_correct": "yes",
        "dependencies_affected": "none",
        "next_action_still_valid": "yes",
        "plan_should_change": "no",
    }
    base.update(overrides)
    return base


def _drive_adapter(adapter: GenesisAdapter, task_id: str,
                   findings: dict[str, str] | None = None,
                   decision: str = CONTINUE_CURRENT_PLAN) -> None:
    """Drive adapter through one full bounded loop."""
    adapter.contract.mark_ready(task_id)
    adapter.execute_unit(task_id)
    adapter.verify(task_id)
    adapter.reevaluate(task_id, findings or _findings(), decision)


# -- GenesisCognition unit tests --------------------------------------------

class TestGenesisCognitionUnit(unittest.TestCase):
    """Unit tests for the cognition function itself."""

    def setUp(self):
        self.cog = GenesisCognition()

    def test_think_returns_plan_fields(self):
        result = self.cog.think("t1", {"goal": "simple task"})
        self.assertIn("objective", result)
        self.assertIn("_genesis_depth", result)
        self.assertNotIn("_genesis_depth", LIGHTWEIGHT_FIELDS)

    def test_think_lightweight_for_simple_goal(self):
        result = self.cog.think("t1", {"goal": "fix typo"})
        self.assertEqual(result["_genesis_depth"], LIGHTWEIGHT)
        self.assertIn("objective", result)
        self.assertIn("change", result)
        self.assertIn("expected_result", result)
        self.assertIn("verify", result)

    def test_think_full_for_complex_goal(self):
        result = self.cog.think("t1", {
            "goal": "implement a comprehensive error handling system with "
                     "retry logic, circuit breakers, and fallback chains",
            "current_state": "no error handling exists",
            "constraints": "must be backward compatible",
            "dependencies": "task_dag, providers, routing",
        })
        self.assertEqual(result["_genesis_depth"], FULL)
        for field in ("objective", "current_state", "requirements",
                      "constraints", "dependencies", "risks", "unknowns",
                      "steps", "evidence_requirements", "acceptance"):
            self.assertIn(field, result)

    def test_think_counts_thoughts(self):
        self.assertEqual(self.cog.thought_count, 0)
        self.cog.think("t1", {"goal": "a"})
        self.assertEqual(self.cog.thought_count, 1)
        self.cog.think("t2", {"goal": "b"})
        self.assertEqual(self.cog.thought_count, 2)

    def test_think_defaults_empty_goal(self):
        result = self.cog.think("t1", {})
        self.assertIn("objective", result)
        self.assertEqual(result["_genesis_depth"], LIGHTWEIGHT)

    def test_think_uses_objective_fallback(self):
        result = self.cog.think("t1", {"objective": "fallback goal"})
        self.assertEqual(result["objective"], "fallback goal")

    def test_lightweight_plan_has_required_fields(self):
        result = self.cog.think("t1", {"goal": "tiny"})
        depth = result.pop("_genesis_depth")
        self.assertEqual(depth, LIGHTWEIGHT)
        for field in LIGHTWEIGHT_FIELDS:
            self.assertIn(field, result)
            self.assertTrue(result[field], f"{field} should not be empty")

    def test_full_plan_has_required_fields(self):
        result = self.cog.think("t1", {
            "goal": "comprehensive system with multiple components",
            "current_state": "design phase",
            "constraints": "time and resource limits",
            "dependencies": "external APIs",
        })
        depth = result.pop("_genesis_depth")
        self.assertEqual(depth, FULL)
        for field in FULL_FIELDS:
            self.assertIn(field, result)
            self.assertTrue(result[field], f"{field} should not be empty")


class TestGenesisCognitionMemory(unittest.TestCase):
    """Tests for cognition recall from ProblemMemory."""

    def test_recall_without_memory(self):
        cog = GenesisCognition(problem_memory=None)
        result = cog.think("t1", {"goal": "task"})
        self.assertIn("objective", result)

    def test_recall_with_mock_memory(self):
        mock_memory = MagicMock()
        mock_record = MagicMock()
        mock_record.problem_id = "p1"
        mock_record.error = "connection timeout"
        mock_record.workaround = "retry with backoff"
        mock_record.model = "qwen2.5-coder:3b"
        mock_memory.query.return_value = [mock_record]

        cog = GenesisCognition(problem_memory=mock_memory)
        result = cog.think("t1", {"goal": "task", "project": "agent-bridge"})
        self.assertIn("objective", result)
        mock_memory.query.assert_called_once_with(
            project="agent-bridge", error_contains="")

    def test_recall_incorporates_patterns(self):
        mock_memory = MagicMock()
        mock_record = MagicMock()
        mock_record.problem_id = "p1"
        mock_record.error = "error"
        mock_record.workaround = "use workaround X"
        mock_record.model = "model"
        mock_memory.query.return_value = [mock_record]

        cog = GenesisCognition(problem_memory=mock_memory)
        result = cog.think("t1", {"goal": "task"})
        verify = result.get("verify", "")
        self.assertIn("workaround X", verify)

    def test_recall_handles_query_failure(self):
        mock_memory = MagicMock()
        mock_memory.query.side_effect = RuntimeError("db error")

        cog = GenesisCognition(problem_memory=mock_memory)
        result = cog.think("t1", {"goal": "task"})
        self.assertIn("objective", result)


class TestGenesisCognitionDepthAssessment(unittest.TestCase):

    def setUp(self):
        self.cog = GenesisCognition()

    def test_short_goal_is_lightweight(self):
        result = self.cog.think("t1", {"goal": "fix"})
        self.assertEqual(result["_genesis_depth"], LIGHTWEIGHT)

    def test_long_goal_with_state_is_full(self):
        result = self.cog.think("t1", {
            "goal": "a" * 130,
            "current_state": "initial",
        })
        self.assertEqual(result["_genesis_depth"], FULL)

    def test_constraints_push_to_full(self):
        result = self.cog.think("t1", {
            "goal": "a" * 70,
            "constraints": "must not break API",
        })
        self.assertEqual(result["_genesis_depth"], FULL)


# -- GenesisAdapter integration tests ---------------------------------------

class TestGenesisAdapterIntegration(unittest.TestCase):
    """Tests for GenesisAdapter wiring through the contract."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="genesis_22_"))
        self.cx = ExecutionContract(self.tmp / "contract.json")
        self.cog = GenesisCognition()
        self.adapter = GenesisAdapter(
            self.cx,
            execute_fn=lambda tid, plan: "genesis execution result",
            verify_fn=lambda tid, res: ("VERIFIED", ["e1"]),
            cognition_fn=self.cog.think,
        )

    def test_propose_plan_uses_cognition(self):
        t = self.cx.receive()
        self.cx.recover_context(t)
        plan = self.adapter.propose_plan(t, {"goal": "test"})
        self.assertEqual(plan.author, "genesis-cognition")
        self.assertIn(plan.depth, (LIGHTWEIGHT, FULL))

    def test_propose_plan_without_cognition_fails_closed(self):
        cx2 = ExecutionContract()
        adapter2 = GenesisAdapter(cx2)
        t = cx2.receive()
        cx2.recover_context(t)
        with self.assertRaises(ExecutionPolicyViolation) as ctx:
            adapter2.propose_plan(t, {"goal": "test"})
        self.assertEqual(ctx.exception.reason, PLAN_MISSING)

    def test_full_lifecycle_lightweight(self):
        t = self.cx.receive()
        self.cx.recover_context(t)
        self.adapter.propose_plan(t, {"goal": "tiny task"})
        _drive_adapter(self.adapter, t)
        self.assertEqual(self.cx.state_of(t), CONTINUE_CURRENT_PLAN)

    def test_full_lifecycle_full_plan(self):
        t = self.cx.receive()
        self.cx.recover_context(t)
        self.adapter.propose_plan(t, {
            "goal": "comprehensive implementation with multiple aspects",
            "current_state": "needs work",
            "constraints": "must pass tests",
            "dependencies": "module A",
        })
        _drive_adapter(self.adapter, t)
        self.assertEqual(self.cx.state_of(t), CONTINUE_CURRENT_PLAN)

    def test_execute_unit_calls_execute_fn(self):
        t = self.cx.receive()
        self.cx.recover_context(t)
        self.adapter.propose_plan(t, {"goal": "test"})
        self.adapter.contract.mark_ready(t)
        result = self.adapter.execute_unit(t)
        self.assertEqual(result, "genesis execution result")

    def test_verify_uses_verify_fn(self):
        t = self.cx.receive()
        self.cx.recover_context(t)
        self.adapter.propose_plan(t, {"goal": "test"})
        self.adapter.contract.mark_ready(t)
        self.adapter.execute_unit(t)
        rec = self.adapter.verify(t)
        self.assertEqual(rec.verdict, "VERIFIED")
        self.assertIn("e1", rec.evidence)

    def test_reevaluate_records_decision(self):
        t = self.cx.receive()
        self.cx.recover_context(t)
        self.adapter.propose_plan(t, {"goal": "test"})
        # First cycle: plan → execute → verify → reevaluate(CONTINUE)
        _drive_adapter(self.adapter, t)
        self.assertEqual(self.cx.state_of(t), CONTINUE_CURRENT_PLAN)
        # Second cycle: CONTINUE → READY → execute → verify → reevaluate(COMPLETE)
        _drive_adapter(self.adapter, t, decision=COMPLETE)
        self.assertEqual(self.cx.state_of(t), COMPLETE)

    def test_cognition_counts_across_tasks(self):
        t1 = self.cx.receive()
        self.cx.recover_context(t1)
        self.adapter.propose_plan(t1, {"goal": "task 1"})
        t2 = self.cx.receive()
        self.cx.recover_context(t2)
        self.adapter.propose_plan(t2, {"goal": "task 2"})
        self.assertEqual(self.cog.thought_count, 2)

    def test_checkpoint_after_lifecycle(self):
        t = self.cx.receive()
        self.cx.recover_context(t)
        self.adapter.propose_plan(t, {"goal": "test"})
        _drive_adapter(self.adapter, t)
        snap = self.adapter.checkpoint()
        self.assertIsInstance(snap, str)
        self.assertTrue(len(snap) > 0)


# -- Full pipeline integration tests ----------------------------------------

class TestGenesisFullPipeline(unittest.TestCase):
    """End-to-end tests: cognition → adapter → contract → lifecycle."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="genesis_pipe_"))

    def test_complete_pipeline_lightweight_to_complete(self):
        cx = ExecutionContract(self.tmp / "pipeline.json")
        cog = GenesisCognition()
        adapter = GenesisAdapter(
            cx,
            execute_fn=lambda tid, plan: "completed work",
            verify_fn=lambda tid, res: ("VERIFIED", ["pipeline-evidence"]),
            cognition_fn=cog.think,
        )

        t = cx.receive()
        cx.recover_context(t)
        plan = adapter.propose_plan(t, {"goal": "fix one line"})
        self.assertEqual(plan.depth, LIGHTWEIGHT)

        adapter.contract.mark_ready(t)
        adapter.execute_unit(t)
        adapter.verify(t)
        adapter.reevaluate(t, _findings(), COMPLETE)
        cx.finalize(t)
        self.assertEqual(cx.state_of(t), COMPLETE)

    def test_complete_pipeline_full_plan_to_complete(self):
        cx = ExecutionContract(self.tmp / "pipeline_full.json")
        cog = GenesisCognition()
        adapter = GenesisAdapter(
            cx,
            execute_fn=lambda tid, plan: "full implementation result",
            verify_fn=lambda tid, res: ("VERIFIED", ["full-evidence"]),
            cognition_fn=cog.think,
        )

        t = cx.receive()
        cx.recover_context(t)
        plan = adapter.propose_plan(t, {
            "goal": "implement complete error handling with retry logic",
            "current_state": "no error handling",
            "constraints": "backward compatible",
            "dependencies": "providers, routing",
        })
        self.assertEqual(plan.depth, FULL)
        self.assertIn("risks", plan.fields)
        self.assertIn("steps", plan.fields)

        adapter.contract.mark_ready(t)
        adapter.execute_unit(t)
        adapter.verify(t)
        adapter.reevaluate(t, _findings(), COMPLETE)
        cx.finalize(t)
        self.assertEqual(cx.state_of(t), COMPLETE)

    def test_pipeline_adapt_on_failure(self):
        cx = ExecutionContract(self.tmp / "pipeline_adapt.json")
        cog = GenesisCognition()
        # First adapter: verify returns FAILED (triggers adaptation)
        adapter_fail = GenesisAdapter(
            cx,
            execute_fn=lambda tid, plan: "attempt result",
            verify_fn=lambda tid, res: ("FAILED", ["test failed"]),
            cognition_fn=cog.think,
        )

        t = cx.receive()
        cx.recover_context(t)
        adapter_fail.propose_plan(t, {"goal": "task that will fail"})
        adapter_fail.contract.mark_ready(t)
        adapter_fail.execute_unit(t)
        adapter_fail.verify(t)

        # Re-evaluate with failure -> adapt plan
        cx.begin_reevaluate(t)
        cx.record_reevaluation(t,
            _findings(behaviour_matched_expected="no",
                      plan_should_change="yes"),
            "ADAPT_PLAN", ["test failed"], adapter_fail.name)

        # New plan via cognition, with adapter whose verify returns VERIFIED
        adapter_ok = GenesisAdapter(
            cx,
            execute_fn=lambda tid, plan: "revised result",
            verify_fn=lambda tid, res: ("VERIFIED", ["revised-evidence"]),
            cognition_fn=cog.think,
        )
        adapter_ok.propose_plan(t, {"goal": "revised approach after failure"})
        adapter_ok.contract.mark_ready(t)
        adapter_ok.execute_unit(t)
        adapter_ok.verify(t)
        cx.begin_reevaluate(t)
        cx.record_reevaluation(t, _findings(), COMPLETE, [],
                               adapter_ok.name)
        cx.finalize(t)
        self.assertEqual(cx.state_of(t), COMPLETE)

    def test_pipeline_multiple_tasks_independent(self):
        cx = ExecutionContract(self.tmp / "pipeline_multi.json")
        cog = GenesisCognition()
        adapter = GenesisAdapter(
            cx,
            execute_fn=lambda tid, plan: f"result-{tid}",
            verify_fn=lambda tid, res: ("VERIFIED", ["e"]),
            cognition_fn=cog.think,
        )

        t1 = cx.receive()
        t2 = cx.receive()
        cx.recover_context(t1)
        cx.recover_context(t2)

        adapter.propose_plan(t1, {"goal": "first"})
        adapter.propose_plan(t2, {"goal": "second"})

        _drive_adapter(adapter, t1)
        _drive_adapter(adapter, t2)

        self.assertEqual(cx.state_of(t1), CONTINUE_CURRENT_PLAN)
        self.assertEqual(cx.state_of(t2), CONTINUE_CURRENT_PLAN)

    def test_cognition_depth_adapts_to_context(self):
        cog = GenesisCognition()

        # Simple context -> LIGHTWEIGHT
        simple = cog.think("t1", {"goal": "fix"})
        self.assertEqual(simple["_genesis_depth"], LIGHTWEIGHT)

        # Rich context -> FULL
        rich = cog.think("t2", {
            "goal": "implement comprehensive multi-module error handling",
            "current_state": "design complete, code needed",
            "constraints": "must maintain API compatibility",
            "dependencies": "routing, providers, task_dag",
        })
        self.assertEqual(rich["_genesis_depth"], FULL)

    def test_cognition_produces_evidence_requirements(self):
        cog = GenesisCognition()
        result = cog.think("t1", {
            "goal": "implement comprehensive feature with tests",
            "current_state": "design phase",
            "constraints": "must pass CI",
            "verify": "run tests and check coverage",
        })
        self.assertIn("evidence_requirements", result)
        self.assertIn("run tests", result["evidence_requirements"])

    def test_cognition_produces_acceptance_criteria(self):
        cog = GenesisCognition()
        result = cog.think("t1", {
            "goal": "implement comprehensive feature with tests",
            "current_state": "design phase",
            "constraints": "must pass CI",
            "expected_result": "all tests pass",
        })
        self.assertIn("acceptance", result)
        self.assertIn("all tests pass", result["acceptance"])

    def test_collapse_with_block_and_resume(self):
        cx = ExecutionContract(self.tmp / "pipeline_block.json")
        cog = GenesisCognition()
        # First adapter: verify returns FAILED (triggers block)
        adapter_block = GenesisAdapter(
            cx,
            execute_fn=lambda tid, plan: "result",
            verify_fn=lambda tid, res: ("FAILED", ["blocker"]),
            cognition_fn=cog.think,
        )

        t = cx.receive()
        cx.recover_context(t)
        adapter_block.propose_plan(t, {"goal": "blocked task"})
        _drive_adapter(adapter_block, t,
                       _findings(plan_should_change="yes"),
                       BLOCK_WITH_EVIDENCE)
        self.assertEqual(cx.state_of(t), BLOCK_WITH_EVIDENCE)

        # Unblocked via contract re-evaluation
        cx.begin_reevaluate(t)
        cx.record_reevaluation(t, _findings(), CONTINUE_CURRENT_PLAN,
                               ["unblock"], adapter_block.name)

        # Resume with a new adapter whose verify returns VERIFIED
        adapter_ok = GenesisAdapter(
            cx,
            execute_fn=lambda tid, plan: "result-ok",
            verify_fn=lambda tid, res: ("VERIFIED", ["unblock-evidence"]),
            cognition_fn=cog.think,
        )
        adapter_ok.contract.mark_ready(t)
        adapter_ok.execute_unit(t)
        adapter_ok.verify(t)
        cx.begin_reevaluate(t)
        cx.record_reevaluation(t, _findings(), COMPLETE, [],
                               adapter_ok.name)
        cx.finalize(t)
        self.assertEqual(cx.state_of(t), COMPLETE)


if __name__ == "__main__":
    unittest.main()
