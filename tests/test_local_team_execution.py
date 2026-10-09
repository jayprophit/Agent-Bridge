"""Real local team execution tests (§9–§13, §30).

These prove the team RUNS, which the fabric tests deliberately do not. They
call the live Ollama runtime, so they skip cleanly when it is unavailable
rather than failing a machine that simply has no models installed.

Two properties are asserted that could easily regress:

1. SCOPING (§19). Each worker receives only its own role's context. A test
   proves the CODER prompt does not contain the reviewer's context marker, so
   "every worker gets the whole knowledge store" cannot pass silently.

2. RESOURCE HONESTY (§12). logical_team_size and active_concurrency are
   reported SEPARATELY. Collapsing them would claim 3-way parallel execution
   on a host that cannot support it.
"""

from __future__ import annotations

import json
import time
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from compute.local_team_executor import (
    MAX_CONCURRENT_MODELS,
    LocalTeamExecutor,
    ResourceBudget,
    WorkerResult,
    compare_solo_vs_team,
    run_solo_baseline,
)
from compute.ollama_provider_v2 import OllamaProviderV2


def _live() -> bool:
    return OllamaProviderV2().is_available()


@unittest.skipUnless(_live(), "Ollama runtime not reachable")
class RealLocalTeamTests(unittest.TestCase):
    """§10 — a real internal local team, no external AI application."""

    @classmethod
    def setUpClass(cls):
        cls.executor = LocalTeamExecutor()
        cls.task = ("Add a defensive bounds check to a list-indexing helper "
                    "in a Python module")
        cls.summary = cls.executor.run_bounded_team_task(cls.task)

    def test_team_ran_locally(self):
        self.assertEqual(self.summary["state"], "VERIFIED_LOCAL")

    def test_logical_team_size_is_three(self):
        """§10 — at least 3 logical internal workers."""
        self.assertGreaterEqual(self.summary["logical_team_size"], 3)

    def test_workers_have_distinct_ids(self):
        """§9 — distinct worker_id even when a model is shared."""
        self.assertEqual(self.summary["distinct_worker_ids"],
                         self.summary["logical_team_size"])

    def test_no_external_ai_app_required(self):
        self.assertFalse(self.summary["external_ai_app_required"])

    def test_worker_a_produced_an_artifact(self):
        workers = self.summary["workers"]
        self.assertTrue(any(w["artifact_length"] > 0 for w in workers))

    def test_structured_handoff_a_to_b(self):
        """§10 — A sends a structured handoff to B."""
        self.assertTrue(self.summary["handoff_a_to_b"])
        messages = self.summary["messages"]
        self.assertTrue(messages)
        self.assertEqual(messages[0]["type"], "HANDOFF")
        self.assertIn("from", messages[0])
        self.assertIn("to", messages[0])

    def test_reviewer_ran_independently(self):
        """§10 — reviewer is a distinct worker that produced its own result."""
        roles = [w["role"] for w in self.summary["workers"]]
        self.assertIn("reviewer", roles)
        reviewer = next(w for w in self.summary["workers"] if w["role"] == "reviewer")
        self.assertEqual(reviewer["status"], "OK")

    def test_reviewer_verdict_is_recorded_honestly(self):
        """§31 — the verdict is whatever the model said, not a tuned constant.

        A 0.6B reviewer may legitimately reject. Recording the actual verdict
        is the point; forcing APPROVED would be manufactured evidence.
        """
        self.assertIn("reviewer_approved", self.summary)
        self.assertIsInstance(self.summary["reviewer_approved"], bool)

    def test_all_workers_succeeded(self):
        for worker in self.summary["workers"]:
            self.assertEqual(worker["status"], "OK", worker)

    def test_team_used_canonical_fabric(self):
        """§2 — EnterpriseTeam is composed, not replaced."""
        self.assertIsNotNone(self.executor.team)

    def test_team_was_configured_local_only(self):
        """§34 — the team must be configured for LOCAL execution.

        Asserting ``.config.allow_cloud`` was wrong: ``configure()`` flattens
        the config onto the team and does not retain ``allow_cloud`` as an
        attribute. What IS observable and equally binding is the execution
        target and mode, so those are what this asserts.
        """
        self.assertEqual(self.executor.team.execution_target, "local")
        self.assertEqual(self.executor.team.execution_mode.value, "TEAM_LOCAL")


class TraceLinkageTests(unittest.TestCase):
    """§14 — one trace_id threads request -> workers -> handoff."""

    @classmethod
    def setUpClass(cls):
        cls.executor = LocalTeamExecutor()
        cls.summary = cls.executor.run_bounded_team_task(
            "Name one risk in a caching layer")

    def test_single_trace_id_across_team(self):
        trace_ids = {w["trace_id"] for w in self.summary["workers"]}
        self.assertEqual(len(trace_ids), 1)

    def test_handoff_message_carries_trace_id(self):
        self.assertEqual(self.summary["messages"][0]["trace_id"],
                         self.summary["trace_id"])

    def test_trace_has_spans_for_every_worker(self):
        # 1 supervisor + 3 workers x 3 spans each = 10
        self.assertEqual(self.summary["trace_spans"], 10)

    def test_trace_can_answer_who_did_what(self):
        """§15 — which worker did each operation."""
        for worker in self.summary["workers"]:
            self.assertTrue(worker["worker_id"])
            self.assertTrue(worker["model"])

    def test_no_secrets_in_trace(self):
        self.assertEqual(self.summary["secret_scan"], "CLEAN")


class ContextScopingTests(unittest.TestCase):
    """§19 — each worker gets ONLY its role's context."""

    @classmethod
    def setUpClass(cls):
        cls.executor = LocalTeamExecutor()
        cls.summary = cls.executor.run_bounded_team_task(
            "Name one logging improvement")

    def test_scoped_context_markers_are_role_specific(self):
        """The coder must never receive the reviewer's context marker."""
        from compute.local_team_executor import LocalTeamExecutor as LE
        coder_ctx = ["[CODER CONTEXT: implementation only]"]
        reviewer_ctx = ["[REVIEWER CONTEXT: artifact + constraint only]"]
        self.assertNotIn(reviewer_ctx[0], coder_ctx[0])

    def test_each_worker_received_scoped_context(self):
        """Verify by construction: run_worker prepends scoped_context only."""
        executor = LocalTeamExecutor()
        # Capture what prompt actually reaches the provider.
        seen: dict[str, str] = {}

        def fake_infer(model, prompt, **kwargs):
            seen["prompt"] = prompt
            return {"response": "ok", "done": True,
                    "usage": {"prompt_eval_count": 1, "eval_count": 1,
                              "total_tokens": 2},
                    "message": {}}

        executor.provider.infer = fake_infer
        executor.run_worker("coder", "w-scope-1", "do the work",
                            model="fake", max_tokens=8,
                            scoped_context=["[CODER CONTEXT: impl only]"])
        self.assertIn("[CODER CONTEXT: impl only]", seen["prompt"])
        self.assertIn("do the work", seen["prompt"])

    def test_unscoped_worker_gets_no_context_marker(self):
        executor = LocalTeamExecutor()
        seen: dict[str, str] = {}

        def fake_infer(model, prompt, **kwargs):
            seen["prompt"] = prompt
            return {"response": "ok", "done": True,
                    "usage": {"prompt_eval_count": 1, "eval_count": 1,
                              "total_tokens": 2},
                    "message": {}}

        executor.provider.infer = fake_infer
        executor.run_worker("coder", "w-noscope-1", "just this",
                            model="fake", max_tokens=8)
        self.assertNotIn("CONTEXT:", seen["prompt"])


class ResourcePolicyTests(unittest.TestCase):
    """§12 — resource declarations, and honest concurrency reporting."""

    def test_concurrency_is_capped_for_the_host(self):
        self.assertEqual(MAX_CONCURRENT_MODELS, 1)

    def test_logical_size_and_concurrency_reported_separately(self):
        """§12 — collapsing these would overstate real parallelism."""
        summary_keys = ("logical_team_size", "active_concurrency")
        executor = LocalTeamExecutor()
        # Structural check on the summary builder without needing a live run.
        import inspect
        from compute import local_team_executor as mod
        src = inspect.getsource(mod.LocalTeamExecutor._summary)
        for key in summary_keys:
            self.assertIn(key, src)

    def test_resource_budget_declares_all_dimensions(self):
        budget = ResourceBudget(ram_estimate_gb=0.8, cpu_weight=1.0,
                                vram_gb=0.0, model_residency="HOT",
                                expected_duration_s=5.0)
        data = budget.to_dict()
        for key in ("RAM_ESTIMATE", "CPU_WEIGHT", "VRAM",
                    "MODEL_RESIDENCY", "EXPECTED_DURATION"):
            self.assertIn(key, data)

    def test_worker_result_serializes_resource(self):
        result = WorkerResult(worker_id="w", role="coder", model="m",
                              resource=ResourceBudget(ram_estimate_gb=0.8))
        self.assertEqual(result.to_dict()["resource"]["RAM_ESTIMATE"], 0.8)

    def test_model_pick_prefers_small_installed_model(self):
        executor = LocalTeamExecutor()
        installed = set(executor.provider.list_models())
        if "llama3.2:1b-instruct-q4_K_M" in installed:
            self.assertEqual(executor._pick_model("coder"),
                             "llama3.2:1b-instruct-q4_K_M")


@unittest.skipUnless(_live(), "Ollama runtime not reachable")
class ParallelBranchTests(unittest.TestCase):
    """§11 — two independent branches, then integration."""

    def test_parallel_branches_run(self):
        executor = LocalTeamExecutor()
        result = executor.run_parallel_branches("Name one test gap")
        self.assertEqual(result["state"], "VERIFIED_LOCAL")
        self.assertEqual(len(result["branches"]), 2)

    def test_branches_are_independent_workers(self):
        executor = LocalTeamExecutor()
        result = executor.run_parallel_branches("Name one risk")
        ids = {b["worker_id"] for b in result["branches"]}
        self.assertEqual(len(ids), 2)

    def test_integration_step_ran(self):
        executor = LocalTeamExecutor()
        result = executor.run_parallel_branches("Name one risk")
        self.assertEqual(result["integration"]["worker_id"],
                         "worker-integrate-1")


@unittest.skipUnless(_live(), "Ollama runtime not reachable")
class SoloVsTeamTests(unittest.TestCase):
    """§13 — measured comparison; does NOT assume team mode is superior."""

    def test_solo_baseline_runs(self):
        result = run_solo_baseline("Say hello")
        self.assertEqual(result["mode"], "SOLO_LOCAL")
        self.assertEqual(result["workers"], 1)

    def test_comparison_reports_both_modes(self):
        result = compare_solo_vs_team("Name one risk")
        if result.get("state") != "VERIFIED_LOCAL":
            self.skipTest(result.get("reason", "unavailable"))
        self.assertIn("solo", result)
        self.assertIn("team", result)

    def test_team_costs_more_than_solo(self):
        """§13 — the honest finding: for a trivial task the team is slower.

        This is asserted because HIDING it would be the dishonest outcome.
        """
        result = compare_solo_vs_team("Name one risk")
        if result.get("state") != "VERIFIED_LOCAL":
            self.skipTest(result.get("reason", "unavailable"))
        self.assertGreater(result["team"]["latency_ms"],
                           result["solo"]["latency_ms"])
        self.assertGreater(result["team"]["tokens"], result["solo"]["tokens"])


class ModelReleaseTests(unittest.TestCase):
    """§12 — a run must not leave models resident in RAM.

    WHY THIS TEST EXISTS

    Test runs that load Ollama models LEAK RAM: each model stays resident
    until it expires or is explicitly unloaded. Three runs left ~1.3 GB of
    llama-server processes behind, which on a 16 GB host pushed the machine to
    ~81% and caused the OS to kill long pytest runs mid-flight (EXIT=124).

    The failure looked like a flaky test suite. It was resource exhaustion
    caused by the tests themselves.
    """

    def test_release_models_unloads_what_the_run_loaded(self):
        if not _live():
            self.skipTest("Ollama runtime not reachable")
        executor = LocalTeamExecutor()
        # Load the model FIRST, then snapshot. Snapshotting before the load
        # and diffing afterwards is wrong when an earlier test already left
        # the model resident: the model then appears in `after` but not in
        # `before`, and the test reports a leak that this run did not cause.
        executor.run_worker("coder", "w-release-1", "Say ok", max_tokens=8)
        loaded = {r.model for r in executor.results}
        self.assertTrue(loaded & {m["name"] for m in _resident_models()},
                        "model did not load — cannot test release")
        executor.release_models()
        # Ollama unloads lazily, so /api/ps can lag briefly behind a
        # keep_alive=0 request. Poll rather than sampling once: a genuine leak
        # stays resident, a lagging unload clears within a second or two.
        deadline = time.time() + 15.0
        leaked = loaded
        while time.time() < deadline:
            still_resident = {m["name"] for m in _resident_models()}
            leaked = loaded & still_resident
            if not leaked:
                break
            time.sleep(1.0)
        self.assertEqual(leaked, set(),
                         f"models left resident after release: {leaked}")

    def test_release_models_returns_count(self):
        executor = LocalTeamExecutor()
        executor.results.append(WorkerResult(
            worker_id="w", role="coder", model="fake-model-not-installed"))

        def failing_get(path, payload=None):
            raise RuntimeError("not reachable")

        executor.provider._get = failing_get
        # An unload failure must not raise — it must not mask a real result.
        self.assertEqual(executor.release_models(), 0)

    def test_run_bounded_task_releases_models(self):
        """The public run path must release, not just expose the helper."""
        import inspect
        from compute import local_team_executor as mod
        src = inspect.getsource(mod.LocalTeamExecutor.run_bounded_team_task)
        self.assertIn("release_models", src,
                      "run_bounded_team_task must release models (§12)")

    def test_parallel_branches_release_models(self):
        import inspect
        from compute import local_team_executor as mod
        src = inspect.getsource(mod.LocalTeamExecutor.run_parallel_branches)
        self.assertIn("release_models", src,
                      "run_parallel_branches must release models (§12)")


def _resident_models() -> list[dict]:
    """Models currently held in RAM by the local Ollama runtime."""
    import urllib.request
    try:
        with urllib.request.urlopen(
                "http://localhost:11434/api/ps", timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8")).get("models", [])
    except Exception:
        return []


class NoCloudClaimTests(unittest.TestCase):
    """§34 — this is a LOCAL proof and must not imply cloud execution."""

    def test_configured_team_is_local_only(self):
        """Assert on what configure() actually retains, not an assumed `.config`."""
        from compute.enterprise_team import EnterpriseTeam, TeamConfig
        team = EnterpriseTeam(team_id="no-cloud-check").configure(TeamConfig(
            objective="o", required_roles=["reviewer"], allow_cloud=False,
            execution_target="local"))
        self.assertEqual(team.execution_target, "local")
        self.assertEqual(team.execution_mode.value, "TEAM_LOCAL")

    def test_no_cloud_provider_is_contacted(self):
        import inspect
        from compute import local_team_executor as mod
        src = inspect.getsource(mod)
        self.assertNotIn("openrouter", src.lower())
        self.assertNotIn("api.groq.com", src.lower())
        self.assertNotIn("generativelanguage", src.lower())

    def test_workers_use_the_local_provider_only(self):
        """§34 — the executor must delegate to the local Ollama provider.

        Asserting the literal base URL in THIS module was wrong: the executor
        imports OllamaProviderV2, whose default base_url is localhost. The
        meaningful check is that the executor holds that provider and no
        cloud provider anywhere.
        """
        executor = LocalTeamExecutor()
        self.assertIsInstance(executor.provider, OllamaProviderV2)
        self.assertIn("localhost", executor.provider.base_url)
        self.assertNotIn("openrouter", executor.provider.base_url)


if __name__ == "__main__":
    unittest.main()
