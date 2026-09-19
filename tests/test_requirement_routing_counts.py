"""Regression tests: requirement routing aggregation + reconciler keyword matcher.

BUG-001 (route_requirements.py:234-241): by_category was incremented twice
per capability (lines 235 and 241 held the same value), so category counts
summed to ~2x the real total (e.g. general 11,706 vs 6,162 requirements).
by_project was unaffected (single increment).

Matcher cases per programme directive: short tokens must not match word
fragments (ar/search, ai/said), project names must not match via substring
(MAT/materials, DATA/database).
"""
import importlib.util
import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


route_requirements = _load("route_requirements",
                            REPO_ROOT / "route_requirements.py")
reconciler = _load("reconciler_under_test",
                   REPO_ROOT / "reconcile_unknown_requirements.py")


def _records(*texts):
    recs = {"deepseek": [], "chatgpt": [], "claude": []}
    for i, t in enumerate(texts):
        recs["deepseek"].append({"filename": f"f{i}.txt",
                                 "requirements": [{"text": t}]})
    return recs


class AggregationTests(unittest.TestCase):
    def test_by_category_sums_to_total_once(self):
        # 1 technical (POIETEK keyword), 2 general (one routed, one UNKNOWN).
        with redirect_stdout(io.StringIO()):
            reg = route_requirements.route_requirements(_records(
                "add audio effect plugin support",
                "the agent deployment workflow",
                "cover the main platforms and how they work",
            ))
        total = reg["statistics"]["total_requirements"]
        by_cat = dict(reg["statistics"]["by_category"])
        self.assertEqual(total, 3)
        self.assertEqual(sum(by_cat.values()), total)
        self.assertEqual(by_cat.get("technical"), 1)
        self.assertEqual(by_cat.get("general"), 2)

    def test_by_project_sums_to_total(self):
        with redirect_stdout(io.StringIO()):
            reg = route_requirements.route_requirements(_records(
                "add audio effect plugin support",
                "the agent deployment workflow",
                "cover the main platforms and how they work",
            ))
        total = reg["statistics"]["total_requirements"]
        self.assertEqual(sum(reg["statistics"]["by_project"].values()), total)

    def test_single_requirement_counted_once(self):
        with redirect_stdout(io.StringIO()):
            reg = route_requirements.route_requirements(_records("plain text fragment here"))
        self.assertEqual(sum(reg["statistics"]["by_category"].values()), 1)

    def test_provenance_model_threads_corpus(self):
        # BUG-002: provenance.model was hardcoded "deepseek" for every corpus.
        recs = {"deepseek": [], "chatgpt": [], "claude": []}
        recs["chatgpt"].append({"filename": "chatgpt - x.txt",
                                "requirements": [{"text": "chatgpt audio plugin requirement here"}]})
        recs["claude"].append({"filename": "claude - y.txt",
                               "requirements": [{"text": "claude audio plugin requirement here"}]})
        recs["deepseek"].append({"filename": "deepseek - z.txt",
                                 "requirements": [{"text": "deepseek audio plugin requirement here"}]})
        with redirect_stdout(io.StringIO()):
            reg = route_requirements.route_requirements(recs)
        got = {}
        for cap in reg["requirements"]:
            got[cap["provenance"]["source_file"]] = cap["provenance"]["model"]
        self.assertEqual(got["chatgpt - x.txt"], "chatgpt")
        self.assertEqual(got["claude - y.txt"], "claude")
        self.assertEqual(got["deepseek - z.txt"], "deepseek")


class MatcherTests(unittest.TestCase):
    def _hits(self, target, text):
        scores = reconciler.score_targets(text.lower())
        return scores.get(target, (0, []))

    def test_ar_does_not_match_search(self):
        w, matched = self._hits("GAMING", "search the codebase for hardware drivers")
        self.assertNotIn("ar", matched)
        self.assertNotIn("vr", matched)

    def test_ai_does_not_match_fragments(self):
        for text in ["he said it was broken", "training data pipeline",
                     "explain the details", "available options"]:
            w, matched = self._hits("AI", text)
            self.assertNotIn("ai", matched, f"false hit in: {text}")

    def test_ai_matches_standalone(self):
        w, matched = self._hits("AI", "distributed ai training network")
        self.assertIn("ai", matched)

    def test_mat_does_not_match_materials(self):
        w, matched = self._hits("MAT", "new materials for thermal management")
        self.assertNotIn("mat", [m.lower() for m in matched])

    def test_data_does_not_match_database(self):
        w, matched = self._hits("DATA", "local database with sync")
        self.assertNotIn("data", [m.lower() for m in matched])
        self.assertIn("database", [m.lower() for m in matched])

    def test_phrase_matching(self):
        w, matched = self._hits("AGENT_BRIDGE", "durable task graph with checkpoints")
        self.assertIn("task graph", matched)
        self.assertEqual(w, 2)  # multi-word phrase = weight 2

    def test_short_token_exact(self):
        w, matched = self._hits("AI", "support for ml inference on device")
        self.assertIn("ml", matched)
        w2, matched2 = self._hits("GAMING", "vr headset compatibility")
        self.assertIn("vr", matched2)

    def test_word_start_anchored(self):
        w, matched = self._hits("VIDEO", "process immediately without delay")
        self.assertNotIn("media", [m.lower() for m in matched])

    def test_case_insensitive(self):
        w, matched = self._hits("POIETEK", "VST Plugin hosting")
        self.assertTrue([m for m in matched if m.lower() in ("vst", "plugin")])

    def test_plural_forms_match(self):
        w, matched = self._hits("OFFICE", "manage tasks and notes")
        self.assertIn("task", [m.lower() for m in matched])

    def test_athena_canonicalisation(self):
        # Owner correction 2026-09-16: canonical ATHENA; ATHEENA historical alias.
        for text in ["athena health and fitness tracking",
                     "atheena workout planner",
                     "Athena biometric wearable"]:
            scores = reconciler.score_targets(text)
            target, _, _, _ = reconciler.pick_target(scores)
            self.assertEqual(target, "ATHENA", f"failed for: {text}")

    def test_project_identity_aliases(self):
        from project_identity import (CANONICAL_PROJECTS, normalize_project,
                                      canonical_spellings)
        self.assertEqual(normalize_project("ATHEENA"), "ATHENA")
        self.assertEqual(normalize_project("athena"), "ATHENA")
        self.assertEqual(normalize_project("ATHENA"), "ATHENA")
        self.assertIn("ATHENA", CANONICAL_PROJECTS)
        self.assertNotIn("ATHEENA", CANONICAL_PROJECTS)
        # Detection finds historical spellings; raw text itself is untouched.
        raw = "routing used ATHEENA for health"
        self.assertEqual(canonical_spellings(raw), ["ATHEENA"])
        self.assertIn("ATHEENA", raw)

    def test_fea_does_not_match_feature_or_fear(self):
        for text in ["add that feature next", "fear of missing out",
                     "featured artist playlist"]:
            w, matched = self._hits("ENGINEERING", text)
            self.assertNotIn("fea", [m.lower() for m in matched],
                             f"false hit in: {text}")

    def test_hyphenated_keyword(self):
        w, matched = self._hits("POIETEK", "a daw with piano roll editing")
        self.assertIn("piano roll", matched)


class Pass2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p2 = _load("pass2_under_test",
                       REPO_ROOT / "pass2_context_enrichment.py")

    def test_locate_returns_raw_coordinates(self):
        p2 = self.p2
        text = ("Hmm, the user is asking about hardware.\n\n"
                "I need to provide device mapping details.\n\n"
                "The universal bridge handles device mapping well.")
        frag = "The universal bridge handles device mapping well"
        pos, how = p2.locate(text, frag)
        self.assertGreaterEqual(pos, 0)
        window = text[max(0, pos - 50):pos + len(frag) + 50]
        self.assertIn("universal bridge handles device mapping", window.lower())

    def test_locate_missing_for_paraphrase(self):
        p2 = self.p2
        pos, how = p2.locate("completely unrelated content here", "quantum flux capacitors")
        self.assertEqual(pos, -1)

    def test_utterance_reasoning_markers(self):
        p2 = self.p2
        text = ("Hmm, the user is asking about AI tools. "
                "I need to provide a comprehensive overview of available tools.")
        utype, _ = p2.utterance_type("deepseek", text, 10, "comprehensive overview")
        self.assertEqual(utype, "ASSISTANT_REASONING")

    def test_utterance_owner_prompt_first_block(self):
        p2 = self.p2
        text = ("I want to make my own version with blockchain.\n\n"
                "Here is the comprehensive documentation of the project.")
        utype, _ = p2.utterance_type("claude", text, 5, "make my own version")
        self.assertEqual(utype, "OWNER_PROMPT")

    def test_topic_link_precision_generic_no_link(self):
        p2 = self.p2
        idx = {"DEC-000007": ("DECISION_LEDGER", True),
               "CON-000004": ("CONTRADICTION_REGISTER", True)}
        links = p2.register_links(
            "manage requirements in the repository for the project", idx)
        ids = [L["id"] for L in links]
        self.assertNotIn("CON-000004", ids)
        self.assertNotIn("DEC-000007", ids)

    def test_topic_link_genesis_tests(self):
        p2 = self.p2
        links = p2.register_links("16/17 C++ ctests pass, investigate the failure", {})
        ids = [L["id"] for L in links]
        self.assertIn("CON-000004", ids)
        self.assertIn("DEC-000007", ids)

    def test_topic_link_athena_naming_history(self):
        # Historical naming entries must still be detected under both spellings.
        p2 = self.p2
        for text in ["canonical project name ATHEENA for health",
                     "canonical project name ATHENA for health"]:
            ids = [L["id"] for L in p2.register_links(text, {})]
            self.assertIn("DEC-000003", ids, f"failed for: {text}")

    def test_model_from_filename(self):
        p2 = self.p2
        self.assertEqual(p2.model_from_filename("chatgpt - x.txt", "deepseek"), "chatgpt")
        self.assertEqual(p2.model_from_filename("claude - y.txt", "deepseek"), "claude")
        self.assertEqual(p2.model_from_filename("deepseek - z.txt", "chatgpt"), "deepseek")
        # Source-filename typo verified in the deepseek corpus dir.
        self.assertEqual(p2.model_from_filename("deeseek - q.txt", "chatgpt"), "deepseek")


class DomainEnrichmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dom = _load("domain_under_test",
                        REPO_ROOT / "pass2_domain_enrichment.py")

    def _rec(self, **kw):
        r = {"RAW_TEXT": "fragment", "NEW_DOMAIN": "AI",
             "NEW_SHARED_COMPONENT": [], "CLASSIFICATION_CONFIDENCE": 0.5,
             "CLASSIFICATION_REASONING": "", "SHA256_ID": "abc123"}
        r.update(kw)
        return r

    def test_shared_component_never_assigns_project(self):
        dom = self.dom
        comp, proj, repo, notes, exp = dom.component_project_repo(
            self._rec(NEW_SHARED_COMPONENT=["Aetherius Sync"]),
            "DATA", "ASSISTANT_ANSWER", "some window", "sync the database")
        self.assertEqual(comp, "Aetherius Sync")
        self.assertEqual(proj, "")
        self.assertEqual(repo, "")
        self.assertFalse(exp)

    def test_explicit_mention_assigns_project(self):
        dom = self.dom
        comp, proj, repo, notes, exp = dom.component_project_repo(
            self._rec(), "AI", "ASSISTANT_ANSWER",
            "the genesis cognition layer handles this", "ai inference support")
        self.assertEqual(proj, "GENESIS")
        self.assertTrue(exp)

    def test_no_evidence_stages_at_domain(self):
        dom = self.dom
        comp, proj, repo, notes, exp = dom.component_project_repo(
            self._rec(), "OFFICE", "ASSISTANT_ANSWER",
            "a calm window about nothing in particular", "some fragment here")
        self.assertEqual(comp, "FUTURE_OFFICE_CAPABILITY")
        self.assertEqual(proj, "")
        self.assertEqual(repo, "")
        self.assertFalse(exp)

    def test_utterance_subtypes(self):
        dom = self.dom
        self.assertEqual(dom.utterance_subtype("OWNER_PROMPT", "Build the editor now"),
                         "OWNER_DIRECTIVE")
        self.assertEqual(dom.utterance_subtype("OWNER_PROMPT", "How should this work?"),
                         "OWNER_QUESTION")
        self.assertEqual(dom.utterance_subtype("OWNER_PROMPT", "Noting this for later"),
                         "OWNER_PROMPT_OTHER")
        self.assertEqual(dom.utterance_subtype("ASSISTANT_REASONING", "x"),
                         "ASSISTANT_REASONING")


if __name__ == "__main__":
    unittest.main()
