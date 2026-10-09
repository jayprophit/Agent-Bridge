"""§17 — raw and resolved estate evidence must be structurally separate.

THE BUG THESE TESTS EXIST TO PREVENT

fetch_live_estate.py and resolve_upstreams.py both used to write the same
file. The REST list endpoint omits the `parent` field, so raw data makes every
fork look like an unlinkable original. Re-running the fetch alone — say, for a
quick repo count — therefore overwrote resolved upstream evidence with
unresolved data, and seven downstream consumers silently read the degraded
version.

That happened once. The fix at the time was a clearer warning message. A
warning is not a fix: the next person to re-run the fetch would corrupt the
evidence again, and only a downstream test failure would reveal it.

These tests assert the STRUCTURAL property instead: the two stages write
different files, and a raw fetch cannot degrade the resolved dataset. They
simulate the exact accident — run the raw writer, then check the resolved
data — so the regression cannot return quietly.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from migration import evidence_paths as ep


class PathSeparationTests(unittest.TestCase):
    """The two datasets must not share a filename."""

    def test_raw_and_resolved_are_different_files(self):
        self.assertNotEqual(ep.RAW_ESTATE, ep.RESOLVED_ESTATE)

    def test_paths_are_distinct_on_disk(self):
        self.assertNotEqual(ep.RAW_ESTATE.name, ep.RESOLVED_ESTATE.name)

    def test_fetch_script_writes_only_the_raw_path(self):
        """Structural check on the actual source, not a comment's promise."""
        import scripts.fetch_live_estate as fetcher
        self.assertEqual(fetcher.OUT, ep.RAW_ESTATE)

    def test_resolve_script_writes_only_the_resolved_path(self):
        import scripts.resolve_upstreams as resolver
        self.assertEqual(resolver.ESTATE, ep.RESOLVED_ESTATE)

    def test_resolve_script_reads_the_raw_path(self):
        """Resolution must consume raw data, not re-read its own output."""
        import scripts.resolve_upstreams as resolver
        src = Path(resolver.__file__).read_text(encoding="utf-8")
        self.assertIn("RAW_ESTATE", src)
        # It must not read the resolved file as its input source.
        self.assertNotIn("repos = json.loads(ESTATE.read_text", src)

    def test_no_script_writes_the_legacy_path(self):
        """The legacy file is read for compatibility, never written."""
        for name in ("fetch_live_estate", "resolve_upstreams"):
            module = __import__(f"scripts.{name}", fromlist=["x"])
            src = Path(module.__file__).read_text(encoding="utf-8")
            self.assertNotIn("LEGACY_ESTATE.write_text", src)


class RawFetchCannotDegradeResolvedTests(unittest.TestCase):
    """THE CORE REGRESSION GUARD: simulate the exact accident."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _seed(self, raw_path: Path, resolved_path: Path) -> None:
        resolved = [
            {"name": "llama.cpp", "fork": True, "parent": "ggml-org/llama.cpp",
             "parent_branch": "master"},
            {"name": "Agent-Bridge", "fork": False, "parent": None},
        ]
        # Raw enumeration omits `parent` entirely — that is the whole hazard.
        raw = [{"name": "llama.cpp", "fork": True},
               {"name": "Agent-Bridge", "fork": False}]
        resolved_path.write_text(json.dumps(resolved), encoding="utf-8")
        raw_path.write_text(json.dumps(raw), encoding="utf-8")

    def test_raw_fetch_leaves_resolved_intact(self):
        raw_path = self.tmpdir / "raw.json"
        resolved_path = self.tmpdir / "resolved.json"
        self._seed(raw_path, resolved_path)
        before = json.loads(resolved_path.read_text(encoding="utf-8"))

        with mock.patch.object(ep, "RAW_ESTATE", raw_path), \
             mock.patch.object(ep, "RESOLVED_ESTATE", resolved_path):
            # Simulate a fresh raw enumeration landing on disk.
            ep.write_raw([{"name": "llama.cpp", "fork": True},
                          {"name": "Agent-Bridge", "fork": False}])
            stats = ep.assert_not_degraded()

        after = json.loads(resolved_path.read_text(encoding="utf-8"))
        self.assertEqual(before, after, "raw fetch degraded the resolved dataset")
        self.assertTrue(stats["fully_resolved"])

    def test_degraded_resolved_data_is_detected(self):
        """If resolution data IS lost, the guard must fail loudly."""
        resolved_path = self.tmpdir / "resolved.json"
        degraded = [{"name": "llama.cpp", "fork": True, "parent": None}]
        resolved_path.write_text(json.dumps(degraded), encoding="utf-8")
        with mock.patch.object(ep, "RESOLVED_ESTATE", resolved_path), \
             mock.patch.object(ep, "LEGACY_ESTATE",
                               self.tmpdir / "absent.json"):
            with self.assertRaises(AssertionError) as ctx:
                ep.assert_not_degraded()
        self.assertIn("degraded", str(ctx.exception).lower())
        self.assertIn("raw enumeration", str(ctx.exception))

    def test_raw_file_genuinely_lacks_parent(self):
        """Confirms the hazard is real, not hypothetical."""
        with mock.patch.object(ep, "RAW_ESTATE", self.tmpdir / "raw.json"):
            ep.write_raw([{"name": "x", "fork": True}])
            data = json.loads(ep.RAW_ESTATE.read_text(encoding="utf-8"))
        self.assertNotIn("parent", data[0])


class StatsTests(unittest.TestCase):
    """Resolved stats drive both tests and the evidence report."""

    def test_stats_counts_forks_and_originals(self):
        repos = [
            {"name": "a", "fork": True, "parent": "up/a"},
            {"name": "b", "fork": False, "parent": None},
        ]
        stats = ep.resolved_stats(repos)
        self.assertEqual(stats["total"], 2)
        self.assertEqual(stats["forks"], 1)
        self.assertEqual(stats["originals"], 1)
        self.assertTrue(stats["fully_resolved"])

    def test_unresolved_fork_is_flagged(self):
        repos = [{"name": "a", "fork": True, "parent": None}]
        stats = ep.resolved_stats(repos)
        self.assertFalse(stats["fully_resolved"])
        self.assertEqual(stats["unresolved_forks"], ["a"])

    def test_empty_estate_is_not_an_error(self):
        """An empty estate has no forks to be unresolved — must not look degraded.

        `bool(forks) and not unresolved` made an empty estate report False,
        which would read as 'the resolved data is broken' when in fact there is
        simply nothing resolved yet. Degradation requires forks that LACK an
        upstream, not merely an absence of forks.
        """
        self.assertTrue(ep.resolved_stats([])["fully_resolved"])


class LiveEvidenceTests(unittest.TestCase):
    """The committed evidence must satisfy the invariant right now."""

    def test_committed_resolved_estate_is_fully_resolved(self):
        stats = ep.assert_not_degraded()
        self.assertEqual(stats["unresolved_forks"], [])
        self.assertEqual(stats["forks"], 352,
                         "expected 352 forks per the verified live estate")
        self.assertEqual(stats["total"], 396)


if __name__ == "__main__":
    unittest.main()
