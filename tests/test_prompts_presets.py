"""v0.4: prompt profiles, presets, fallback, escalation, competence."""
import shutil
import tempfile
import unittest
from pathlib import Path

import prompts_lib
from bridge import run_bridge
from config import BridgeConfig
from competence import CompetenceTracker
from reviewer import parse_verdict
from routing import RoleRouter
from tests.helpers import FakeProvider


class TestPromptProfiles(unittest.TestCase):
    def test_all_profiles_load(self):
        for name in prompts_lib.available_profiles():
            text = prompts_lib.load_profile(name)
            self.assertTrue(len(text) > 50, name)

    def test_unknown_profile_rejected(self):
        with self.assertRaises(ValueError):
            prompts_lib.load_profile("evil")

    def test_small_profile_end_to_end(self):
        tmp = Path(tempfile.mkdtemp(prefix="v04_prompt_"))
        try:
            cfg = BridgeConfig(workspace=tmp, mode="build", approval="AUTO_SAFE",
                               max_steps=6, non_interactive=True,
                               enable_reviewer=False, prompt_profile="small")
            fake = FakeProvider(['{"action":"write","path":"s.txt","content":"hi"}',
                                 '{"action":"finish","message":"done"}'])
            out = run_bridge(cfg, "t", provider=fake)
            self.assertTrue(out.get("finished"), out)
            self.assertTrue((tmp / "s.txt").exists())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_version_tracked(self):
        from versions import PROMPT_PROFILE_VERSION
        self.assertEqual(PROMPT_PROFILE_VERSION, 1)


class TestPresetsAndFallback(unittest.TestCase):
    def test_low_resource_preset_same_model(self):
        r = RoleRouter("m")
        self.assertEqual({r.model_for(x) for x in ("planner", "coder", "reviewer")}, {"m"})

    def test_balanced_preset_distinct_reviewer(self):
        from config import RoleModels
        roles = RoleModels(reviewer="big-local-model")
        r = RoleRouter("small-local", roles)
        self.assertEqual(r.model_for("coder"), "small-local")
        self.assertEqual(r.model_for("reviewer"), "big-local-model")

    def test_unavailable_model_surfaced_honestly(self):
        tmp = Path(tempfile.mkdtemp(prefix="v04_fb_"))
        try:
            cfg = BridgeConfig(workspace=tmp, mode="build", approval="AUTO_SAFE",
                               max_steps=4, non_interactive=True,
                               enable_reviewer=False, model="ghost-model-xyz")
            cfg.fallback = {"general": ["another-ghost-xyz"]}
            from bridge import run_bridge as rb
            # unavailable models are never claimed: the run fails honestly
            # with OLLAMA_ERROR (fallback attempted first, then surfaced).
            out = rb(cfg, "t", providers={})
            self.assertFalse(out.get("finished", False))
            self.assertEqual(out.get("kind"), "OLLAMA_ERROR")
            self.assertIn("inventory", out.get("error", ""))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestEscalation(unittest.TestCase):
    def test_escalate_parses(self):
        v, err = parse_verdict('{"verdict":"escalate","issues":["unsure"],"recommendations":[],"confidence":0.2}')
        self.assertEqual(err, "")
        self.assertEqual(v["verdict"], "escalate")

    def test_escalate_pauses_without_extra_permissions(self):
        tmp = Path(tempfile.mkdtemp(prefix="v04_esc_"))
        try:
            cfg = BridgeConfig(workspace=tmp, mode="build", approval="AUTO_SAFE",
                               max_steps=8, non_interactive=True)
            coder = FakeProvider(['{"action":"write","path":"a.txt","content":"x"}',
                                  '{"action":"finish","message":"done"}'])
            rev = FakeProvider(['{"verdict":"escalate","issues":["need human"],"recommendations":[],"confidence":0.3}'])
            out = run_bridge(cfg, "t", providers={"coder": coder, "planner": coder,
                                                  "general": coder, "reviewer": rev})
            self.assertFalse(out.get("finished", False))
            self.assertEqual(out.get("kind"), "ESCALATED")
            # paused with clear state, file work preserved, nothing extra granted
            self.assertTrue((tmp / "a.txt").exists())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestCompetence(unittest.TestCase):
    def test_summary_and_hint(self):
        c = CompetenceTracker()
        for _ in range(6):
            c.note_request(False)
        s = c.summary()
        self.assertLess(s["valid_action_ratio"], 0.5)
        self.assertIn("fallback", s["hint"])
        c2 = CompetenceTracker()
        c2.note_request(True)
        c2.note_execution(False, "SyntaxError: bad")
        c2.note_execution(False, "SyntaxError: bad")
        c2.note_execution(False, "SyntaxError: bad")
        self.assertIn("syntax", c2.summary()["hint"].lower())

    def test_corrections_counted(self):
        c = CompetenceTracker()
        c.note_request(True)
        c.note_execution(False, "boom")
        c.note_execution(True)
        self.assertEqual(c.summary()["corrections"], 1)


if __name__ == "__main__":
    unittest.main()
