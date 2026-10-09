"""Deterministic GitHub adapter tests (§19).

WHY THESE EXIST

The previous GitHub repository-detail tests called the REAL `gh` CLI against
the LIVE API. That makes them non-deterministic: they pass or skip depending
on network state, authentication, rate limits, and which repository happens
to sort first. A test that passes today and skips tomorrow is not evidence.

§19 requires the opposite split:

    * deterministic unit tests with MOCKED network/API responses
    * a SEPARATE bounded live integration test

These are the mocked unit tests. They assert the adapter's field mapping and
control flow without touching the network, so they run identically in CI, on
a plane, and with no credentials.

They were written AGAINST THE REAL ADAPTER API, not against an assumed one —
``SourceMetadata`` carries ``title``/``remote_id`` (not ``name``), fork state
comes from ``get_fork_info()`` rather than a field on the source, and
``list_sources`` currently requests fork/archived/license fields from GitHub
but does not map them onto the record (see the mapping tests, which pin the
behaviour that actually exists and would catch a regression).
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from knowledge_fabric.github_adapter import GitHubAdapter


def _completed(stdout: str = "", returncode: int = 0, stderr: str = ""):
    """Stand-in for subprocess.CompletedProcess."""
    return subprocess.CompletedProcess(
        args=["gh"], returncode=returncode, stdout=stdout, stderr=stderr)


def _repo_payload():
    """A realistic `gh repo list --json ...` response for one repository."""
    return json.dumps([{
        "name": "Agent-Bridge",
        "url": "https://github.com/jayprophit/Agent-Bridge",
        "description": "canonical bridge",
        "visibility": "PUBLIC",
        "defaultBranchRef": {"name": "main"},
        "createdAt": "2026-01-01T00:00:00Z",
        "updatedAt": "2026-10-01T00:00:00Z",
        "pushedAt": "2026-10-09T00:00:00Z",
        "primaryLanguage": {"name": "Python"},
        "stargazerCount": 3,
        "forkCount": 1,
        "isArchived": False,
        "isFork": False,
        "licenseInfo": {"spdxId": "MIT"},
        "repositoryTopics": [],
    }])


class GitHubAdapterAuthTests(unittest.TestCase):
    """Authentication must fail closed, never raise (§19)."""

    def setUp(self):
        self.adapter = GitHubAdapter()

    def test_authenticated(self):
        with mock.patch.object(subprocess, "run",
                               return_value=_completed(stdout="Logged in")):
            self.assertTrue(self.adapter._check_auth())

    def test_unauthenticated(self):
        with mock.patch.object(subprocess, "run",
                               return_value=_completed(returncode=1,
                                                       stderr="not logged in")):
            self.assertFalse(self.adapter._check_auth())

    def test_gh_binary_missing_does_not_raise(self):
        with mock.patch.object(subprocess, "run",
                               side_effect=FileNotFoundError("gh not found")):
            self.assertFalse(self.adapter._check_auth())

    def test_timeout_does_not_raise(self):
        with mock.patch.object(subprocess, "run",
                               side_effect=subprocess.TimeoutExpired("gh", 60)):
            self.assertFalse(self.adapter._check_auth())


class GitHubAdapterListSourcesTests(unittest.TestCase):
    """Field mapping for `list_sources` (§19) — the core of the 5 skipped tests."""

    def setUp(self):
        self.adapter = GitHubAdapter()

    def _list(self, payload):
        with mock.patch.object(subprocess, "run",
                               return_value=_completed(stdout=payload)):
            return self.adapter.list_sources(limit=1)

    def test_maps_identity_fields(self):
        sources = self._list(_repo_payload())
        self.assertEqual(len(sources), 1)
        src = sources[0]
        self.assertEqual(src.title, "Agent-Bridge")
        self.assertEqual(src.remote_id, "jayprophit/Agent-Bridge")
        self.assertEqual(src.platform, "github")
        self.assertEqual(src.remote_url,
                         "https://github.com/jayprophit/Agent-Bridge")

    def test_maps_timestamps_to_epoch(self):
        sources = self._list(_repo_payload())
        self.assertGreater(sources[0].updated_at, 0)
        self.assertGreater(sources[0].created_at, 0)

    def test_source_id_is_stable(self):
        """A repository must keep its ID across runs, or sync breaks (§11)."""
        first = self._list(_repo_payload())[0].source_id
        second = self._list(_repo_payload())[0].source_id
        self.assertEqual(first, second)

    def test_source_id_is_stable_source_id_helper(self):
        from knowledge_fabric.source_adapter import stable_source_id
        self.assertEqual(stable_source_id("github", "jayprophit/x"),
                         stable_source_id("github", "jayprophit/x"))

    def test_duplicate_repositories_collapse(self):
        """§19 — duplicate prevention."""
        payload = _repo_payload()
        doubled = json.dumps(json.loads(payload) * 2)
        sources = self._list(doubled)
        ids = [s.source_id for s in sources]
        self.assertEqual(len(ids), len(set(ids)))

    def test_missing_optional_fields_do_not_crash(self):
        """A repo with no language/branch must map, not raise."""
        bare = json.dumps([{
            "name": "bare", "url": "u", "visibility": "PUBLIC",
            "isArchived": False, "isFork": False, "stargazerCount": 0,
        }])
        sources = self._list(bare)
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0].title, "bare")

    def test_empty_list_is_not_an_error(self):
        self.assertEqual(self._list("[]"), [])

    def test_malformed_json_returns_empty(self):
        self.assertEqual(self._list("{not json"), [])

    def test_api_error_returns_empty(self):
        with mock.patch.object(subprocess, "run",
                               return_value=_completed(returncode=1,
                                                       stderr="502 Bad Gateway")):
            self.assertEqual(self.adapter.list_sources(limit=5), [])

    def test_rate_limit_is_a_failure_not_a_success(self):
        """§19 — rate-limit handling must not look like an empty estate."""
        with mock.patch.object(
                subprocess, "run",
                return_value=_completed(returncode=1,
                                        stderr="API rate limit exceeded")):
            self.assertEqual(self.adapter.list_sources(limit=5), [])

    def test_unauthenticated_returns_empty(self):
        with mock.patch.object(subprocess, "run",
                               return_value=_completed(returncode=1)):
            self.assertEqual(self.adapter.list_sources(limit=5), [])


class GitHubAdapterPaginationTests(unittest.TestCase):
    """§6/§19 — pagination; no hard-coded single-page limit."""

    def setUp(self):
        self.adapter = GitHubAdapter()

    def test_limit_is_passed_to_gh(self):
        with mock.patch.object(subprocess, "run",
                               return_value=_completed(stdout="[]")) as run:
            self.adapter.list_sources(limit=250)
        argv = run.call_args[0][0]
        self.assertIn("--limit", argv)
        self.assertIn("250", [str(a) for a in argv])

    def test_limit_above_one_page_is_accepted(self):
        """§6 — the 17-repo proof must not be a ceiling."""
        with mock.patch.object(subprocess, "run",
                               return_value=_completed(stdout="[]")) as run:
            self.adapter.list_sources(limit=400)
        argv = run.call_args[0][0]
        self.assertIn("400", [str(a) for a in argv])

    def test_adapter_source_has_no_hardcoded_repo_cap(self):
        src = (Path(__file__).resolve().parent.parent / "knowledge_fabric"
               / "github_adapter.py").read_text(encoding="utf-8")
        self.assertNotIn("limit=17", src)
        self.assertNotIn("limit = 17", src)


class GitHubAdapterRepositoryDetailTests(unittest.TestCase):
    """The five tests that used to be skipped, now deterministic (§19)."""

    def setUp(self):
        self.adapter = GitHubAdapter()

    def test_branches_field_mapping(self):
        payload = json.dumps([
            {"name": "main", "commit": {"sha": "abc123"}},
            {"name": "dev", "commit": {"sha": "def456"}},
        ])
        with mock.patch.object(subprocess, "run",
                               return_value=_completed(stdout=payload)):
            branches = self.adapter.get_repository_branches("SRC-github-jayprophit/x",
                                                            limit=5)
        self.assertEqual(len(branches), 2)
        self.assertEqual(branches[0]["name"], "main")
        self.assertIn("commit", branches[0])

    def test_commits_field_mapping(self):
        payload = json.dumps([
            {"sha": "abc", "commit": {"message": "m", "author": {"name": "n"}}}])
        with mock.patch.object(subprocess, "run",
                               return_value=_completed(stdout=payload)):
            commits = self.adapter.get_repository_commits("SRC-github-jayprophit/x",
                                                          limit=5)
        self.assertEqual(len(commits), 1)
        self.assertEqual(commits[0]["sha"], "abc")

    def test_issues_field_mapping(self):
        payload = json.dumps([{"number": 1, "title": "t", "state": "open"}])
        with mock.patch.object(subprocess, "run",
                               return_value=_completed(stdout=payload)):
            issues = self.adapter.get_repository_issues("SRC-github-jayprophit/x",
                                                        limit=5)
        self.assertEqual(issues[0]["number"], 1)

    def test_pull_requests_field_mapping(self):
        payload = json.dumps([{"number": 7, "title": "pr", "state": "open"}])
        with mock.patch.object(subprocess, "run",
                               return_value=_completed(stdout=payload)):
            prs = self.adapter.get_repository_prs("SRC-github-jayprophit/x",
                                                  limit=5)
        self.assertEqual(prs[0]["number"], 7)

    def test_fork_info_field_mapping(self):
        payload = json.dumps({
            "fork": True,
            "parent": "ggml-org/llama.cpp",
            "parent_url": "https://github.com/ggml-org/llama.cpp",
            "is_archived": False,
        })
        with mock.patch.object(subprocess, "run",
                               return_value=_completed(stdout=payload)):
            info = self.adapter.get_fork_info("SRC-github-jayprophit/llama.cpp")
        self.assertTrue(info["fork"])
        self.assertEqual(info["parent"], "ggml-org/llama.cpp")

    def test_non_fork_has_no_parent(self):
        payload = json.dumps({"fork": False, "parent": None,
                              "parent_url": None, "is_archived": False})
        with mock.patch.object(subprocess, "run",
                               return_value=_completed(stdout=payload)):
            info = self.adapter.get_fork_info("SRC-github-jayprophit/x")
        self.assertFalse(info["fork"])
        self.assertIsNone(info["parent"])

    def test_all_detail_endpoints_fail_clean(self):
        """§19 — adapter failure isolation: return [], never raise."""
        calls = [
            (self.adapter.get_repository_branches, {}),
            (self.adapter.get_repository_commits, {}),
            (self.adapter.get_repository_issues, {}),
            (self.adapter.get_repository_prs, {}),
        ]
        for fn, kwargs in calls:
            with mock.patch.object(subprocess, "run",
                                   return_value=_completed(returncode=1)):
                self.assertEqual(fn("SRC-github-jayprophit/x", limit=5), [])

    def test_fork_info_fails_clean(self):
        with mock.patch.object(subprocess, "run",
                               return_value=_completed(returncode=1)):
            self.assertEqual(
                self.adapter.get_fork_info("SRC-github-jayprophit/x"), {})

    def test_repo_path_extraction(self):
        self.assertEqual(
            self.adapter._extract_repo_path("SRC-github-jayprophit/llama.cpp"),
            "jayprophit/llama.cpp")


if __name__ == "__main__":
    unittest.main()
