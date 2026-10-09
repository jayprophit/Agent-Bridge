"""Owner-work source classifier tests (§16–§18).

The classifier decides what KIND of owner divergence each file holds, and
that decision feeds a keep/port/archive recommendation. A classifier that
mislabels the largest changes as the least certain would archive real work
on a pattern-matching miss, so the shape rules are pinned here.

Deterministic: synthetic patches, no network, no gh calls (§19).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from analyse_owner_work_source import (  # noqa: E402
    classify_language,
    classify_patch,
    cluster_isaaclab,
    recommend,
)


def diff(lines: list[tuple[str, str]]) -> str:
    """Build a unified-diff body from (marker, text) pairs."""
    return "\n".join(f"{m}{t}" for m, t in lines)


class FormattingOnlyTests(unittest.TestCase):
    def test_whitespace_only_change_is_formatting(self):
        patch = diff([("-", "    x = 1"), ("+", "x = 1")])
        category, reason = classify_patch("a.py", patch)
        self.assertEqual(category, "formatting_only")
        self.assertIn("whitespace", reason)

    def test_reformat_then_add_is_not_formatting(self):
        """A real change hidden among reformatted lines is still real."""
        patch = diff([("-", "    x = 1"), ("+", "x = 1"),
                      ("+", "y = 2")])
        category, _ = classify_patch("a.py", patch)
        self.assertNotEqual(category, "formatting_only")

    def test_keyword_in_reformatted_comment_stays_formatting(self):
        """The formatting check must run BEFORE any content signal."""
        patch = diff([("-", "    # fix this later"), ("+", "# fix this later")])
        category, _ = classify_patch("a.py", patch)
        self.assertEqual(category, "formatting_only")


class SubstantiveTests(unittest.TestCase):
    def test_many_new_definitions_is_a_feature(self):
        patch = diff([("+", f"def handler_{i}(req):") for i in range(5)])
        category, reason = classify_patch("service.py", patch)
        self.assertEqual(category, "feature")
        self.assertIn("definition", reason)

    def test_assertion_heavy_diff_is_test_work(self):
        patch = diff([("+", "    self.assertEqual(a, b)") for _ in range(6)])
        category, _ = classify_patch("test_service.py", patch)
        self.assertEqual(category, "test_addition")

    def test_assertions_in_a_non_test_path_are_still_test_work(self):
        patch = diff([("+", "    self.assertEqual(a, b)") for _ in range(5)])
        category, _ = classify_patch("lib/checks.py", patch)
        self.assertEqual(category, "test_addition")

    def test_small_surgical_edit_is_a_bug_fix(self):
        patch = diff([("+", "if value is None:"),
                      ("+", "    return 0"),
                      ("-", "return value.count")])
        category, reason = classify_patch("util.py", patch)
        self.assertEqual(category, "bug_fix")
        self.assertIn("surgical", reason)

    def test_import_churn_is_compatibility(self):
        patch = diff([("+", "import os"), ("+", "import sys"),
                      ("+", "x = 1")])
        category, reason = classify_patch("main.py", patch)
        self.assertEqual(category, "compatibility_patch")
        self.assertIn("import", reason)

    def test_java_definitions_count_as_definitions(self):
        patch = diff([("+", f"    public void run{i}() {{}}")
                      for i in range(4)])
        category, _ = classify_patch("Runner.java", patch)
        self.assertEqual(category, "feature")

    def test_deletion_only_is_reported_as_deletion(self):
        patch = diff([("-", f"line {i}") for i in range(3)])
        category, _ = classify_patch("a.py", patch)
        self.assertEqual(category, "deletion")

    def test_config_file_is_not_source_behaviour(self):
        patch = diff([("+", f"dep-{i}: 1.0") for i in range(8)])
        category, _ = classify_patch("pom.xml", patch)
        self.assertEqual(category, "config_or_docs")


class NoUnclassifiedTests(unittest.TestCase):
    """The bug that motivated the rewrite.

    A keyword-only classifier labelled 613 of IsaacLab's largest changes
    `unclassified`, including +1658/-341 diffs. `unclassified` must now be
    unreachable for any patch with added lines.
    """

    def test_large_keyword_free_diff_is_never_unclassified(self):
        """The exact shape that used to fall through."""
        patch = diff([("+", f"        value_{i} = compute({i})")
                      for i in range(400)])
        category, _ = classify_patch("source/isaaclab_physx/fabric.py", patch)
        self.assertNotEqual(category, "unclassified")
        self.assertNotEqual(category, "metadata_only")

    def test_every_added_line_shape_yields_a_category(self):
        shapes = [
            ("def f():", "a.py"),
            ("class Foo:", "a.py"),
            ("    public int x;", "A.java"),
            ("x = 1", "a.py"),
            ("# comment only", "a.py"),
            ("<dependency/>", "pom.xml"),
            ("  indented_change = True", "a.py"),
        ]
        for line, path in shapes:
            patch = diff([("+", line)])
            category, _ = classify_patch(path, patch)
            self.assertNotIn(category, ("unclassified",),
                             f"{path}: {line!r} was unclassified")


class RecommendationTests(unittest.TestCase):
    def test_substantive_changes_never_recommend_archive(self):
        """REGRESSION — the reported self-contradiction.

        The analysis printed "13 substantive source changes" and then
        recommended ARCHIVE with reason "no substantive source change".
        A non-empty source_changes list can no longer reach ARCHIVE.
        """
        source_changes = [{"path": "A.java", "language": "java",
                           "category": "feature"}]
        rec = recommend([], source_changes)
        self.assertNotEqual(rec["decision"], "ARCHIVE")

    def test_empty_source_changes_archives(self):
        rec = recommend([], [])
        self.assertEqual(rec["decision"], "ARCHIVE")

    def test_unclassified_substantive_changes_ask_for_reading(self):
        """A pattern miss is a classifier limit, not evidence of triviality."""
        source_changes = [{"path": "A.java", "language": "java",
                           "category": "unclassified"}]
        rec = recommend([], source_changes)
        self.assertEqual(rec["decision"], "INSPECT_MANUALLY")

    def test_real_changes_recommend_inspect_then_port(self):
        source_changes = [{"path": "A.java", "language": "java",
                           "category": "bug_fix"}]
        rec = recommend([], source_changes)
        self.assertEqual(rec["decision"], "INSPECT_THEN_PORT")
        self.assertIn("§17", rec["owner_action"])


class ClusterTests(unittest.TestCase):
    def test_isaaclab_paths_cluster_by_capability(self):
        cases = {
            "source/isaaclab/simulation/physx.py": "simulation",
            "source/isaaclab/robots/articulation.py": "robot_control",
            "source/isaaclab/rl/runner.py": "training",
            "source/isaaclab/envs/task.py": "environment",
            "source/isaaclab/sensors/camera.py": "sensor_perception",
            "tests/test_foo.py": "tests",
            ".github/workflows/ci.yml": "build_config",
        }
        for path, expected in cases.items():
            self.assertEqual(cluster_isaaclab(path), expected,
                             f"{path} clustered wrong")

    def test_unclustered_is_honest_not_silent(self):
        self.assertEqual(cluster_isaaclab("README.md"), "unclustered")


class LanguageTests(unittest.TestCase):
    def test_languages_are_recognised(self):
        self.assertEqual(classify_language("a/b/C.java"), "java")
        self.assertEqual(classify_language("a/b/c.py"), "python")
        self.assertEqual(classify_language("pom.xml"), "config")
        self.assertEqual(classify_language("k.cu"), "cuda")


if __name__ == "__main__":
    unittest.main(verbosity=2)
