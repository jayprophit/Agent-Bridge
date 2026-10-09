"""Unique-commit audit and §34 safe-delete gate (§5, §25, §34, §51 step 6).

Extends the migration package with:

  * UniqueContentClass (§5) — NONE / CONFIG_ONLY / DOCUMENTATION_ONLY /
    EXPERIMENTAL / USEFUL_PATCH / AETHERIUS_SPECIFIC / CRITICAL_UNIQUE_CODE
    / UNKNOWN
  * The FULL §34 safe-delete gate — 15 conditions, not the abbreviated 10
    the earlier gate implemented

§34 is stricter than the gate already in provenance.py, which followed the
earlier 10-step summary. This module is authoritative: a repo reaches
SAFE_TO_DELETE only when ALL FIFTEEN conditions hold.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class UniqueContentClass(str, Enum):
    """§5 classification of fork-only content."""

    NONE = "NONE"
    CONFIG_ONLY = "CONFIG_ONLY"
    DOCUMENTATION_ONLY = "DOCUMENTATION_ONLY"
    EXPERIMENTAL = "EXPERIMENTAL"
    USEFUL_PATCH = "USEFUL_PATCH"
    AETHERIUS_SPECIFIC = "AETHERIUS_SPECIFIC"
    CRITICAL_UNIQUE_CODE = "CRITICAL_UNIQUE_CODE"
    UNKNOWN = "UNKNOWN"


# Content classes that mean "owner work exists and must be preserved".
PRESERVATION_REQUIRED = frozenset({
    UniqueContentClass.USEFUL_PATCH,
    UniqueContentClass.AETHERIUS_SPECIFIC,
    UniqueContentClass.CRITICAL_UNIQUE_CODE,
    UniqueContentClass.UNKNOWN,  # unknown is never safe to discard
})

# §34 — the authoritative 15-condition gate.
SAFE_DELETE_CONDITIONS = (
    "live_identity_verified",
    "upstream_identified",
    "license_recorded",
    "unique_commits_checked",
    "capabilities_mapped",
    "each_capability_decided",
    "implementation_complete",
    "tests_passed",
    "provenance_registered",
    "replacement_committed",
    "replacement_pushed",
    "remote_sha_verified",
    "no_unresolved_dependencies",
    "documentation_updated",
    "archive_created_if_needed",
)


@dataclass
class SafeDeleteVerdict:
    """§34 gate result — all fifteen must hold."""

    repo: str
    conditions: dict[str, bool] = field(default_factory=dict)

    @property
    def satisfied(self) -> list[str]:
        return [k for k, v in self.conditions.items() if v]

    @property
    def unsatisfied(self) -> list[str]:
        return [k for k in SAFE_DELETE_CONDITIONS if not self.conditions.get(k)]

    @property
    def safe(self) -> bool:
        return not self.unsatisfied

    def as_dict(self) -> dict:
        return {
            "repo": self.repo,
            "safe_to_delete": self.safe,
            "satisfied": self.satisfied,
            "unsatisfied": self.unsatisfied,
            "gate": "§34 (15 conditions)",
        }


def classify_unique_content(unique_files: list[str],
                            unique_commits: int) -> UniqueContentClass:
    """§5 heuristic — classifies fork-only content from changed paths.

    Deliberately conservative: anything not clearly inert is escalated,
    because owner work must never be silently discarded.
    """
    if unique_commits == 0 or not unique_files:
        return UniqueContentClass.NONE

    doc_exts = {".md", ".rst", ".txt", ".adoc", ".pdf"}
    config_exts = {".yml", ".yaml", ".toml", ".ini", ".cfg", ".lock", ".json"}
    code_exts = {".py", ".js", ".ts", ".go", ".rs", ".c", ".h", ".cpp", ".hpp",
                 ".java", ".rb", ".sh", ".ps1", ".lua", ".jsx", ".tsx", ".vue",
                 ".html", ".css", ".scss"}

    exts = {Path(f).suffix.lower() for f in unique_files}
    if exts and exts <= doc_exts:
        return UniqueContentClass.DOCUMENTATION_ONLY
    if exts and exts <= (doc_exts | config_exts):
        return UniqueContentClass.CONFIG_ONLY
    if exts & code_exts:
        # Real code diverges from upstream. Whether it is load-bearing cannot
        # be decided from a file list, so escalate rather than discard.
        return UniqueContentClass.UNKNOWN
    return UniqueContentClass.EXPERIMENTAL


def fork_vs_upstream(fork: str, upstream: str, upstream_branch: str,
                     fork_branch: str) -> dict:
    """Compare fork against upstream (§5). READ-ONLY.

    The compare endpoint lives on the UPSTREAM repo, not the fork.
    """
    if not upstream or not upstream_branch:
        return {"error": "upstream or branch unknown", "ahead_by": None,
                "unique_commits": None}
    url = (f"repos/{upstream}/compare/"
           f"{upstream_branch}...{fork.split('/')[0]}:{fork_branch}")
    proc = subprocess.run(
        ["gh", "api", url, "--jq",
         "{ahead_by, behind_by, status, total_commits, "
         "files: [.files[].filename]}"],
        capture_output=True, text=True, timeout=180,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        return {"error": proc.stderr[:200], "ahead_by": None,
                "unique_commits": None}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"error": "unparseable response", "ahead_by": None,
                "unique_commits": None}
