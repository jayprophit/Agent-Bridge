"""Change-aware test selection tests (P21, REQ-p21-test-impact)."""
import unittest

from test_impact import (
    DIRECT_DEPENDENCY,
    HISTORICAL_FAILURE,
    HISTORICALLY_FLAKY,
    MANDATORY,
    NAME_MATCH,
    NO_RELEVANT_PATH,
    RUN,
    SELF_TEST,
    SKIPPED_BY_PREDICTION,
    TRANSITIVE_DEPENDENCY,
    UNKNOWN_IMPACT,
    ImpactError,
    build_import_graph,
    normalize_changed,
    predict,
)


def graph():
    return {
        "src/auth.py": [],
        "src/db.py": ["src/auth.py"],
        "src/api.py": ["src/db.py"],
        "src/util.py": [],
        "tests/test_auth.py": ["src/auth.py"],
        "tests/test_api.py": ["src/api.py"],
        "tests/test_util.py": ["src/util.py"],
        "tests/test_cycle_a.py": ["tests/test_cycle_b.py"],
        "tests/test_cycle_b.py": ["tests/test_cycle_a.py"],
    }


UNIVERSE = sorted(t for t in graph() if t.startswith("tests/"))


class TestInputs(unittest.TestCase):
    def test_normalize_rejects_escapes(self):
        self.assertEqual(normalize_changed(["b.py", "a.py", "a.py"]), ["a.py", "b.py"])
        with self.assertRaises(ImpactError):
            normalize_changed(["/abs/path.py"])
        with self.assertRaises(ImpactError):
            normalize_changed(["../escape.py"])
        with self.assertRaises(ImpactError):
            normalize_changed([""])
        with self.assertRaises(ImpactError):
            predict(["ok.py"], [""], {})

    def test_malformed_graph_history_rejected(self):
        with self.assertRaises(ImpactError):
            predict(["a.py"], ["t"], {"a": "notalist"})
        with self.assertRaises(ImpactError):
            predict(["a.py"], ["t"], {}, {"t": {"failures": -1}})

    def test_graph_cycles_terminate_deterministically(self):
        first = predict(["tests/test_cycle_a.py"], UNIVERSE, graph())
        second = predict(["tests/test_cycle_a.py"], UNIVERSE, graph())
        self.assertEqual(first.selected(), second.selected())
        self.assertIn("tests/test_cycle_b.py", first.selected())


class TestSelection(unittest.TestCase):
    def test_direct_and_transitive_impact(self):
        plan = predict(["src/auth.py"], UNIVERSE, graph())
        by_id = {d.test_id: d for d in plan.decisions}
        self.assertEqual(by_id["tests/test_auth.py"].state, RUN)
        self.assertIn(DIRECT_DEPENDENCY, by_id["tests/test_auth.py"].reasons)
        self.assertEqual(by_id["tests/test_api.py"].state, RUN)
        self.assertIn(TRANSITIVE_DEPENDENCY, by_id["tests/test_api.py"].reasons)
        self.assertIn("src/auth.py", by_id["tests/test_api.py"].related_paths)
        self.assertEqual(by_id["tests/test_util.py"].state, SKIPPED_BY_PREDICTION)
        self.assertEqual(by_id["tests/test_util.py"].reasons, [NO_RELEVANT_PATH])

    def test_changed_test_runs_itself(self):
        plan = predict(["tests/test_util.py"], UNIVERSE, graph())
        by_id = {d.test_id: d for d in plan.decisions}
        self.assertIn(SELF_TEST, by_id["tests/test_util.py"].reasons)

    def test_deleted_file_still_impacts(self):
        plan = predict(["src/db.py"], UNIVERSE, graph())
        self.assertEqual(plan.selected(), ["tests/test_api.py"])

    def test_unknown_code_runs_conservatively(self):
        plan = predict(["src/brand_new.py"], UNIVERSE, graph())
        self.assertEqual(plan.selected(), UNIVERSE)
        for decision in plan.decisions:
            self.assertIn(UNKNOWN_IMPACT, decision.reasons)

    def test_unknown_noncode_noted_not_forced(self):
        plan = predict(["README.md"], UNIVERSE, graph())
        self.assertEqual(plan.selected(), [])
        self.assertTrue(any("README.md" in note for note in plan.notes))
        self.assertEqual(plan.skipped(), UNIVERSE)

    def test_history_adds_evidence_never_authority(self):
        history = {
            "tests/test_api.py": {"failures": 2, "runs": 5},
            "tests/test_util.py": {"failures": 1, "runs": 4},
        }
        plan = predict(["src/auth.py"], UNIVERSE, graph(), history)
        by_id = {d.test_id: d for d in plan.decisions}
        self.assertIn(HISTORICAL_FAILURE, by_id["tests/test_api.py"].reasons)
        # Flaky but unrelated: metadata recorded, state untouched.
        self.assertIn(HISTORICALLY_FLAKY, by_id["tests/test_util.py"].reasons)
        self.assertEqual(by_id["tests/test_util.py"].state, SKIPPED_BY_PREDICTION)
        # Direct impact without history still RUNs.
        plain = predict(["src/auth.py"], UNIVERSE, graph(), {})
        self.assertEqual(plain.selected(), ["tests/test_api.py", "tests/test_auth.py"])

    def test_mandatory_beats_prediction(self):
        plan = predict(["src/util.py"], UNIVERSE, graph(), {}, mandatory=["tests/test_api.py"])
        by_id = {d.test_id: d for d in plan.decisions}
        self.assertIn(MANDATORY, by_id["tests/test_api.py"].reasons)
        self.assertEqual(by_id["tests/test_api.py"].state, RUN)

    def test_skipped_never_reported_passed(self):
        plan = predict(["src/util.py"], UNIVERSE, graph())
        for decision in plan.decisions:
            self.assertIn(decision.state, (RUN, SKIPPED_BY_PREDICTION))
            self.assertNotIn("passed", str(decision.__dict__).lower())
            self.assertNotIn("PASS", str(decision.__dict__))
        self.assertEqual(plan.skipped(), ["tests/test_api.py", "tests/test_auth.py",
                                          "tests/test_cycle_a.py", "tests/test_cycle_b.py"])


class TestGraphBuilder(unittest.TestCase):
    def test_builds_bounded_deterministic_graph(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.py").write_text("import b\n")
            (root / "b.py").write_text("x = 1\n")
            (root / "broken.py").write_text("def broken(:\n")
            first = build_import_graph(root)
            second = build_import_graph(root)
            self.assertEqual(first, second)
            self.assertEqual(first["a.py"], ["b.py"])
            self.assertEqual(first["b.py"], [])
            self.assertEqual(first["broken.py"], [])
        with self.assertRaises(ImpactError):
            build_import_graph("/nonexistent-root-xyz")


if __name__ == "__main__":
    unittest.main()
