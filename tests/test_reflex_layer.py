"""v0.9.0 reflex layer tests (no LLM, no I/O)."""
import unittest

from reflex_layer import (
    LatencyBudget,
    LatencyStats,
    ReflexExecutionLayer,
    Route,
    TaskTriageEngine,
)


class TestReflex(unittest.TestCase):
    def test_arithmetic_case_a(self):
        r = ReflexExecutionLayer().execute("2 + 4")
        self.assertTrue(r["ok"])
        self.assertEqual(r["result"], 6)
        self.assertEqual(r["engine"], "arithmetic")

    def test_arithmetic_rejects_code(self):
        r = ReflexExecutionLayer().execute("__import__('os').system('x')")
        self.assertFalse(r["ok"])

    def test_non_deterministic(self):
        r = ReflexExecutionLayer().execute("design a distributed architecture")
        self.assertFalse(r["ok"])

    def test_latency_measured(self):
        r = ReflexExecutionLayer().execute("2 + 4")
        self.assertIn("latency_s", r)
        self.assertLess(r["latency_s"], 1.0)


class TestTriage(unittest.TestCase):
    def test_case_a_reflex(self):
        t = TaskTriageEngine().triage("2 + 4")
        self.assertEqual(t.route, Route.EXECUTE_INLINE_NOW)

    def test_case_d_deliberative(self):
        t = TaskTriageEngine().triage(
            "design a distributed architecture for multi-region failover "
            "with event sourcing and CQRS and cost analysis")
        self.assertEqual(t.route, Route.EXECUTE_DELIBERATIVE_AI)

    def test_case_f_background(self):
        t = TaskTriageEngine().triage("render a long video",
                                      {"long_running": True})
        self.assertEqual(t.route, Route.QUEUE_BACKGROUND)

    def test_case_g_approval(self):
        t = TaskTriageEngine().triage("format F:\\")
        self.assertEqual(t.route, Route.REQUEST_APPROVAL)
        self.assertTrue(t.needs_approval)

    def test_case_e_parallel(self):
        t = TaskTriageEngine().triage("implement subsystem",
                                      {"parallel_subtasks": True})
        self.assertEqual(t.route, Route.PARALLEL_DELEGATE)

    def test_case_c_quick(self):
        t = TaskTriageEngine().triage("explain this Python error: NameError")
        self.assertEqual(t.route, Route.EXECUTE_QUICK_AI)

    def test_case_h_remote(self):
        t = TaskTriageEngine().triage("train 70b model",
                                      {"remote_only": True})
        self.assertEqual(t.route, Route.ROUTE_REMOTE)

    def test_case_b_data_tool(self):
        t = TaskTriageEngine().triage("filter this spreadsheet and total column X")
        # deterministic data-op pattern exists; triage keeps it fast
        self.assertIn(t.route, (Route.EXECUTE_INLINE_NOW,
                                Route.EXECUTE_QUICK_AI))
        self.assertEqual(t.budget, LatencyBudget.REFLEX
                         if t.route == Route.EXECUTE_INLINE_NOW
                         else LatencyBudget.INTERACTIVE)


class TestLatencyStats(unittest.TestCase):
    def test_summary(self):
        s = LatencyStats()
        s.record("REFLEX", 0.002)
        s.record("REFLEX", 0.004)
        out = s.summary()
        self.assertEqual(out["REFLEX"]["n"], 2)
        self.assertLessEqual(out["REFLEX"]["p50"], 0.004)


if __name__ == "__main__":
    unittest.main()
