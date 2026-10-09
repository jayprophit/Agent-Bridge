"""Compute-runtime audit tests (§19–§25).

WHAT IS DETERMINISTIC AND WHAT IS LIVE (§19)

The reconciliation logic — downgrading a declaration the host contradicts,
counting evidence gaps, refusing to promote emulation to hardware — is
exercised against a fake prober. Deterministic, no network, nothing
installed.

The only live assertion is that the audit RUNS against the real host
without installing anything. It asserts nothing about which runtimes are
present, because that varies by machine and a test asserting presence would
be asserting this workstation's state as a product requirement.
"""

from __future__ import annotations

import unittest

from compute.compute_runtime_audit import (
    LOW_BIT_EVIDENCE_STATES,
    ComputeRuntimeAudit,
    ReuseDecision,
    RuntimeProber,
    RuntimeRecord,
    RuntimeState,
    low_bit_evidence_state,
)


def fake_prober(present: dict[str, bool] | None = None,
                first_lines: dict[str, str] | None = None):
    present = present or {}
    first_lines = first_lines or {}

    def which(name):
        return name if any(present.values()) else None

    def runner(args):
        rid = args[0]
        if rid in ("python",):
            return {"present": True, "reason": "answered", "first_line": ""}
        if present.get(rid):
            return {"present": True, "reason": "answered",
                    "first_line": first_lines.get(rid, f"{rid} 1.0.0")}
        return {"present": False, "reason": "not on PATH"}

    return RuntimeProber(runner=runner, which=which)


class CandidateSetTests(unittest.TestCase):
    def test_candidates_cover_the_directive_runtimes(self):
        """§19–§23 names llama.cpp, ollama, vllm, ggml explicitly."""
        ids = {r.runtime_id for r in ComputeRuntimeAudit.candidate_runtimes()}
        for required in ("ollama", "llama_cpp", "vllm", "ggml"):
            self.assertIn(required, ids,
                          f"§{19 + 0} candidate set is missing {required}")

    def test_every_candidate_answers_what_when_where_how(self):
        """§19 requires all four questions answered, not just a name."""
        for rec in ComputeRuntimeAudit.candidate_runtimes():
            self.assertTrue(rec.purpose, f"{rec.runtime_id}: no WHAT")
            self.assertTrue(rec.trigger, f"{rec.runtime_id}: no WHEN")
            self.assertTrue(rec.owner, f"{rec.runtime_id}: no WHERE")
            self.assertTrue(rec.integration, f"{rec.runtime_id}: no HOW")

    def test_no_runtime_is_installed_blindly(self):
        """§91 — DESIGNED runtimes must not claim measurement."""
        for rec in ComputeRuntimeAudit.candidate_runtimes():
            if rec.state in (RuntimeState.DESIGNED,
                             RuntimeState.RESEARCH_ONLY):
                self.assertEqual(rec.measured, {},
                                 f"{rec.runtime_id} claims measurement "
                                 f"without being installed")

    def test_vllm_is_not_the_desktop_default(self):
        """§22 — a 16 GB CPU-first workstation must not route to vLLM."""
        vllm = next(r for r in ComputeRuntimeAudit.candidate_runtimes()
                    if r.runtime_id == "vllm")
        self.assertEqual(vllm.reuse_decision,
                         ReuseDecision.CLOUD_SERVING_TARGET)
        self.assertNotIn("desktop default", vllm.trigger)

    def test_ollama_is_keep_dependency_not_permanent(self):
        """§21 — Ollama is not assumed permanent."""
        ollama = next(r for r in ComputeRuntimeAudit.candidate_runtimes()
                      if r.runtime_id == "ollama")
        self.assertEqual(ollama.reuse_decision, ReuseDecision.KEEP_DEPENDENCY)
        self.assertTrue(ollama.retirement_condition,
                        "a KEEP_DEPENDENCY must state when it is retired")

    def test_ggml_is_distinct_from_llama_cpp(self):
        """§23 — format/library vs execution engine, recorded separately."""
        by_id = {r.runtime_id: r for r in
                 ComputeRuntimeAudit.candidate_runtimes()}
        self.assertIsNot(by_id["ggml"], by_id["llama_cpp"])
        self.assertIn("format", by_id["ggml"].purpose.lower())


class ReconciliationTests(unittest.TestCase):
    def test_declaration_contradicted_by_host_is_downgraded(self):
        """§15 — live evidence overrides the declaration."""
        records = [RuntimeRecord(
            runtime_id="ollama", name="Ollama",
            state=RuntimeState.INSTALLED_VERIFIED,
            purpose="p", trigger="t", owner="o", integration="i")]
        audit = ComputeRuntimeAudit(prober=fake_prober(present={}))
        result = audit.audit(records)
        row = result["runtimes"][0]
        self.assertEqual(row["state"], RuntimeState.NOT_INSTALLED.value,
                         "an absent runtime was still reported as verified")
        self.assertTrue(any("downgraded" in n for n in row["notes"]))

    def test_present_runtime_records_its_probe(self):
        records = [RuntimeRecord(
            runtime_id="ollama", name="Ollama",
            state=RuntimeState.INSTALLED_VERIFIED,
            purpose="p", trigger="t", owner="o", integration="i")]
        audit = ComputeRuntimeAudit(prober=fake_prober(
            present={"ollama": True},
            first_lines={"ollama": "ollama version is 0.12.0"}))
        result = audit.audit(records)
        self.assertEqual(result["installed"], ["ollama"])
        self.assertEqual(result["not_installed"], [])
        self.assertIn("0.12.0", result["runtimes"][0]["measured"]["probe"])

    def test_evidence_gap_lists_unmeasured_claims(self):
        """An uninstalled runtime's declarations are gaps, not facts."""
        records = [RuntimeRecord(
            runtime_id="vllm", name="vLLM",
            state=RuntimeState.DESIGNED,
            purpose="p", trigger="t", owner="o", integration="i",
            declared={"gpu_support": True, "continuous_batching": True})]
        audit = ComputeRuntimeAudit(prober=fake_prober(present={}))
        result = audit.audit(records)
        gap = result["runtimes"][0]["evidence_gap"]
        self.assertEqual(sorted(gap), ["continuous_batching", "gpu_support"])
        self.assertIn("vllm", result["unverified_claims"])

    def test_verified_runtime_has_no_gap(self):
        records = [RuntimeRecord(
            runtime_id="ollama", name="Ollama",
            state=RuntimeState.INSTALLED_VERIFIED,
            purpose="p", trigger="t", owner="o", integration="i",
            declared={"gpu_support": True})]
        audit = ComputeRuntimeAudit(prober=fake_prober(
            present={"ollama": True}))
        result = audit.audit(records)
        self.assertEqual(result["runtimes"][0]["evidence_gap"], [])

    def test_audit_counts_states_and_decisions(self):
        result = ComputeRuntimeAudit(
            prober=fake_prober(present={"ollama": True})).audit()
        self.assertTrue(result["by_state"])
        self.assertTrue(result["by_decision"])
        self.assertIn("ollama", result["installed"])

    def test_audit_never_installs_anything(self):
        """The audit is read-only: no subprocess other than version probes."""
        calls: list[list[str]] = []

        def runner(args):
            calls.append(list(args))
            return {"present": True, "reason": "answered", "first_line": ""}

        prober = RuntimeProber(runner=runner, which=lambda n: n)
        ComputeRuntimeAudit(prober=prober).audit()
        for args in calls:
            self.assertNotIn("install", " ".join(args))
            self.assertNotIn("pull", " ".join(args))
            self.assertNotIn("run", " ".join(args))

    def test_module_that_imports_but_fails_is_not_installed(self):
        """REGRESSION — §139: a resolved-but-failing runtime is not usable.

        `python -m vllm` exits 1 when the GPU stack is absent. Counting that
        as installed would report a runtime this host cannot run.
        """
        from compute.compute_runtime_audit import _probe_command

        class FakeProc:
            returncode = 1
            stdout = ""
            stderr = "ImportError: no CUDA"

        import compute.compute_runtime_audit as mod

        original = mod.subprocess.run
        mod.subprocess.run = lambda *a, **k: FakeProc()
        try:
            probe = _probe_command(["python", "-m", "vllm", "--version"])
        finally:
            mod.subprocess.run = original

        self.assertFalse(probe["present"],
                         "a runtime that failed to start was reported present")
        self.assertTrue(probe["resolved"])
        self.assertFalse(probe["answered"])
        self.assertIn("exited 1", probe["reason"])

    def test_broken_runtime_is_flagged_not_silently_dropped(self):
        records = [RuntimeRecord(
            runtime_id="vllm", name="vLLM", state=RuntimeState.DESIGNED,
            purpose="p", trigger="t", owner="o", integration="i")]

        def runner(args):
            return {"present": False, "resolved": True, "answered": False,
                    "reason": "resolved but exited 1", "exit_code": 1}

        prober = RuntimeProber(runner=runner, which=lambda n: n)
        result = ComputeRuntimeAudit(prober=prober).audit(records)
        row = result["runtimes"][0]
        self.assertEqual(row["state"], RuntimeState.DESIGNED.value)
        self.assertTrue(any("not functional" in n for n in row["notes"]),
                        "a resolved-but-broken runtime was silently ignored")


class ForkUseCaseTests(unittest.TestCase):
    def test_fork_rows_carry_the_directive_fields(self):
        """§25 — the shape the existing Fork Migration Registry consumes."""
        rows = ComputeRuntimeAudit(
            prober=fake_prober(present={"ollama": True})).audit()["runtimes"]
        fork_rows = ComputeRuntimeAudit.fork_use_cases(rows)
        for row in fork_rows:
            for field in ("repo", "license", "capability", "reuse_decision",
                          "integration_path", "migration_task",
                          "test_requirement", "retirement_condition"):
                self.assertIn(field, row)
        self.assertTrue(all(r["license"] for r in fork_rows),
                        "a fork row without a licence is unusable")

    def test_fork_rows_do_not_restate_commit_counts(self):
        """No second registry: commit counts come from unique_audit."""
        rows = ComputeRuntimeAudit(
            prober=fake_prober(present={"ollama": True})).audit()["runtimes"]
        fork_rows = ComputeRuntimeAudit.fork_use_cases(rows)
        for row in fork_rows:
            self.assertIn("not restated", row["unique_commits"])


class LowBitHonestyTests(unittest.TestCase):
    def test_software_never_claims_physical_hardware(self):
        """§24 — emulation must not be reported as hardware."""
        self.assertEqual(low_bit_evidence_state("ternary hardware"),
                         "SOFTWARE_RUNTIME")
        self.assertEqual(low_bit_evidence_state("1-bit hardware"),
                         "SOFTWARE_RUNTIME")
        self.assertEqual(low_bit_evidence_state("quantum compute"),
                         "SOFTWARE_RUNTIME")

    def test_known_states_pass_through(self):
        for state in LOW_BIT_EVIDENCE_STATES:
            self.assertEqual(low_bit_evidence_state(state.lower()), state)

    def test_empty_claim_defaults_to_software(self):
        self.assertEqual(low_bit_evidence_state(""), "SOFTWARE_RUNTIME")


class LiveAuditTests(unittest.TestCase):
    """Bounded live proof: the audit runs against this host (§19).

    Asserts only that the audit completes and reports honestly — never that
    a specific runtime is installed, which is a host property rather than a
    product requirement.
    """

    def test_live_audit_runs_and_reports_honestly(self):
        result = ComputeRuntimeAudit().audit()
        self.assertTrue(result["runtimes"])
        for row in result["runtimes"]:
            self.assertIn(row["state"],
                          {s.value for s in RuntimeState},
                          f"unknown evidence state: {row['state']}")
            self.assertIn("probe", row)

    def test_live_audit_installs_nothing(self):
        """Running the audit must not create processes or files."""
        before = set(ComputeRuntimeAudit().prober.probe_all())
        after = set(ComputeRuntimeAudit().prober.probe_all())
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main(verbosity=2)
