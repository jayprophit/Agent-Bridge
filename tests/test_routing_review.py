"""v0.3 suite (migrated): role routing, reviewer verdicts, revision loop."""
import shutil
import tempfile
import unittest
from pathlib import Path

from bridge import run_bridge
from config import BridgeConfig
from reviewer import parse_verdict
from routing import RoleRouter
from tests.helpers import FakeProvider, RoleFakeProviders


def _cfg(tmp: Path, **kw) -> BridgeConfig:
    # v0.4 intentional change: default collision policy now gates rewrites;
    # migrated rewrite flows pin OVERWRITE to preserve original intent
    # (dedicated collision tests cover the new default).
    args = dict(workspace=tmp, mode="build", approval="AUTO_SAFE",
                max_steps=10, non_interactive=True, collision="OVERWRITE")
    args.update(kw)
    return BridgeConfig(**args)


class TestRouting(unittest.TestCase):
    def test_same_model_shared_honestly(self):
        r = RoleRouter("m")
        route = r.route("reviewer")
        self.assertEqual(route.model, "m")
        self.assertEqual(len(route.shared_with), 3)
        self.assertIn("shared", route.reason)

    def test_per_role_models(self):
        from config import RoleModels
        roles = RoleModels(planner="p", coder="c", reviewer="r", general="g")
        r = RoleRouter("default", roles)
        self.assertEqual(r.model_for("planner"), "p")
        self.assertEqual(r.model_for("coder"), "c")
        self.assertEqual(r.model_for("reviewer"), "r")
        self.assertEqual(r.route("coder").shared_with, [])

    def test_phase_roles(self):
        r = RoleRouter("m")
        self.assertEqual(r.phase_role("plan", "write"), "planner")
        self.assertEqual(r.phase_role("build", "write"), "coder")
        self.assertEqual(r.phase_role("hybrid", "read"), "planner")
        self.assertEqual(r.phase_role("hybrid", "write"), "coder")


class TestVerdictParsing(unittest.TestCase):
    def test_approve(self):
        v, err = parse_verdict('{"verdict":"approve","issues":[],"recommendations":[],"confidence":0.9}')
        self.assertEqual(err, "")
        self.assertEqual(v["verdict"], "approve")
        self.assertAlmostEqual(v["confidence"], 0.9)

    def test_fenced_revise(self):
        v, err = parse_verdict('notes\n```json\n{"verdict":"revise","issues":["x is wrong"],"recommendations":["fix x"],"confidence":0.4}\n```')
        self.assertEqual(err, "")
        self.assertEqual(v["verdict"], "revise")
        self.assertEqual(v["issues"], ["x is wrong"])

    def test_garbage_rejected(self):
        v, err = parse_verdict("looks good to me")
        self.assertIsNone(v)
        self.assertTrue(err)

    def test_bad_verdict_value(self):
        v, err = parse_verdict('{"verdict":"maybe"}')
        self.assertIsNone(v)


class TestReviewerLoop(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="v03_rev_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _coder(self, *script: str) -> FakeProvider:
        return FakeProvider(list(script))

    def test_approve_finishes(self):
        cfg = _cfg(self.tmp)
        coder = self._coder('{"action":"write","path":"a.txt","content":"hi"}',
                            '{"action":"finish","message":"done"}')
        rev = FakeProvider(['{"verdict":"approve","issues":[],"recommendations":[],"confidence":0.95}'])
        out = run_bridge(cfg, "t", providers={"coder": coder, "planner": coder,
                                              "general": coder, "reviewer": rev})
        self.assertTrue(out.get("finished"), out)
        self.assertEqual(out["review"]["status"], "approve")
        self.assertTrue((self.tmp / "a.txt").exists())

    def test_revise_then_approve(self):
        cfg = _cfg(self.tmp, max_revision_cycles=2)
        coder = self._coder(
            '{"action":"write","path":"a.txt","content":"v1"}',
            '{"action":"finish","message":"round1"}',
            '{"action":"write","path":"a.txt","content":"v2"}',
            '{"action":"finish","message":"round2"}')
        rev = FakeProvider([
            '{"verdict":"revise","issues":["content should be v2"],"recommendations":["rewrite a.txt"],"confidence":0.6}',
            '{"verdict":"approve","issues":[],"recommendations":[],"confidence":0.9}'])
        helpers = RoleFakeProviders({})
        out = run_bridge(cfg, "t", providers={"coder": coder, "planner": coder,
                                              "general": coder, "reviewer": rev})
        self.assertTrue(out.get("finished"), out)
        self.assertEqual(out["review"]["rounds"], 2)
        self.assertEqual((self.tmp / "a.txt").read_text(), "v2")

    def test_reject_stops(self):
        cfg = _cfg(self.tmp)
        coder = self._coder('{"action":"finish","message":"done"}')
        rev = FakeProvider(['{"verdict":"reject","issues":["unsafe"],"recommendations":[],"confidence":0.9}'])
        out = run_bridge(cfg, "t", providers={"coder": coder, "planner": coder,
                                              "general": coder, "reviewer": rev})
        self.assertFalse(out.get("finished", False))
        self.assertEqual(out.get("kind"), "REVIEW_REJECTED")

    def test_revision_exhaustion(self):
        cfg = _cfg(self.tmp, max_revision_cycles=1)
        coder = self._coder('{"action":"finish","message":"r1"}',
                            '{"action":"finish","message":"r2"}',
                            '{"action":"finish","message":"r3"}')
        rev = FakeProvider([
            '{"verdict":"revise","issues":["bad"],"recommendations":["fix"],"confidence":0.5}',
            '{"verdict":"revise","issues":["still bad"],"recommendations":["fix"],"confidence":0.5}'])
        out = run_bridge(cfg, "t", providers={"coder": coder, "planner": coder,
                                              "general": coder, "reviewer": rev})
        self.assertFalse(out.get("finished", False))
        self.assertEqual(out.get("kind"), "REVISION_EXHAUSTED")


class TestCallRouting(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="v03_route_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_hybrid_uses_planner_then_coder(self):
        cfg = _cfg(self.tmp, mode="hybrid")
        planner = FakeProvider(['{"action":"list","path":"."}'], model="planner-m")
        coder = FakeProvider(['{"action":"write","path":"c.txt","content":"v"}',
                              '{"action":"finish","message":"done"}'],
                             model="coder-m")
        rev = FakeProvider(['{"verdict":"approve","issues":[],"recommendations":[],"confidence":0.9}'])
        out = run_bridge(cfg, "t", providers={"planner": planner, "coder": coder,
                                              "general": coder, "reviewer": rev})
        self.assertTrue(out.get("finished"), out)
        # step1 list via planner, step2 write via coder, step3 finish via
        # planner (steered back after the mutation), review via reviewer.
        self.assertEqual(planner.calls, 2)
        self.assertEqual(coder.calls, 1)
        roles = [h.get("role") for h in out["history"] if h.get("action")]
        self.assertIn("planner", roles)
        self.assertIn("coder", roles)


if __name__ == "__main__":
    unittest.main()
