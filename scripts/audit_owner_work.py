"""Audit the forks that carry unique owner work (§12, §13).

WHY THIS IS READ-ONLY AND BOUNDED

Three forks contain divergence the owner authored or inherited:

    IsaacLab                        +154 commits, 300 files
    neo4j                             +7 commits, 189 files (incl. a real Java edit)
    devops-directive-docker-course    +2 commits,   9 files

These MUST NOT be deleted (§11). This script reads the upstream compare
endpoint and reports what actually changed, so a retirement decision can be
made on evidence rather than on the assumption that "154 commits" is either
trivially mergeable or precious.

It deliberately does not clone, does not checkout, and does not write to any
repository. The estate is raw material; nothing here consumes it destructively.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import Counter, OrderedDict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
AUDIT_CACHE = REPO / "migration" / "evidence" / "unique_commit_audit.json"

OWNER = "jayprophit"

# §12/§13 — the forks with owner divergence. upstream taken from the resolved
# estate, not guessed.
TARGETS = ("neo4j", "IsaacLab", "devops-directive-docker-course")


def gh(*args: str) -> dict | list | None:
    """Run a gh api call, returning parsed JSON or None on failure."""
    proc = subprocess.run(["gh", "api", *args], capture_output=True, text=True,
                          timeout=180)
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def classify_path(path: str) -> str:
    """Coarse capability cluster for a changed file.

    Deliberately conservative: this buckets by LOCATION, never claiming to
    understand what a change does. §12 warns against judging load-bearing-ness
    from filenames, so these are starting points for human review, not verdicts.
    """
    low = path.lower()
    if low.endswith((".java", ".kt", ".scala")):
        return "jvm_source"
    if low.endswith((".py", ".pyi")):
        return "python_source"
    if low.endswith((".cpp", ".cc", ".h", ".hpp", ".cu", ".cuh")):
        return "native_source"
    if low.endswith((".js", ".ts", ".tsx", ".jsx")):
        return "js_source"
    if low.endswith((".md", ".rst", ".txt")):
        return "documentation"
    if low.endswith((".yml", ".yaml", ".toml", ".ini", ".cfg")):
        return "configuration"
    if low.endswith(("pom.xml", "build.gradle", "settings.gradle")):
        return "build_metadata"
    if "test" in low or low.startswith("tests/"):
        return "tests"
    if low.endswith((".json", ".lock")):
        return "data"
    return "other"


def audit_fork(repo: str, upstream: str, fork_branch: str,
               upstream_branch: str, limit: int = 250) -> dict:
    """Compare fork against upstream and summarise the divergence.

    Branches are PASSED IN, not assumed. Default branches differ per repo and
    per fork: neo4j upstream is `2026.09` while the fork sits on `2026.07`,
    IsaacLab upstream is `develop` while the fork is on `release/3.0.0-beta2`.
    Assuming `master` made every lookup 404.
    """
    data = gh(f"repos/{upstream}/compare/"
              f"{upstream_branch}...{OWNER}:{fork_branch}")
    if not isinstance(data, dict):
        return OrderedDict([
            ("repo", repo), ("upstream", upstream),
            ("upstream_branch", upstream_branch),
            ("fork_branch", fork_branch),
            ("state", "LOOKUP_FAILED"),
            ("note", "compare endpoint unavailable for this branch pair"),
        ])

    commits = data.get("commits", []) or []
    files = data.get("files", []) or []

    clusters: Counter = Counter()
    java_files, build_only = [], []
    for f in files:
        kind = classify_path(f.get("filename", ""))
        clusters[kind] += 1
        name = f.get("filename", "")
        if name.endswith(".java"):
            java_files.append(name)
        if name.endswith(("pom.xml", "build.gradle", "settings.gradle")):
            build_only.append(name)

    messages = [c.get("commit", {}).get("message", "").splitlines()[0]
                for c in commits[:limit]]

    return OrderedDict([
    ("repo", repo),
    ("upstream", upstream),
    ("upstream_branch", upstream_branch),
    ("fork_branch", fork_branch),
    ("state", "AUDITED"),
    ("ahead_by", data.get("ahead_by")),
    ("behind_by", data.get("behind_by")),
        ("commit_count", len(commits)),
        ("changed_file_count", len(files)),
        ("additions", data.get("total_commits") and sum(
            f.get("additions", 0) for f in files)),
        ("deletions", sum(f.get("deletions", 0) for f in files)),
        ("capability_clusters", dict(clusters.most_common())),
        ("java_source_files", java_files[:20]),
        ("build_metadata_files", build_only[:20]),
        ("recent_commit_subjects", messages[:25]),
        ("deletion_gate", "DENY"),
        ("deletion_reason", "UNIQUE_OWNER_WORK — must be inspected and "
                            "preserved before any retirement decision (§11)"),
    ])


def default_branch(full_name: str) -> str:
    """Resolve a repo's default branch rather than assuming `master`."""
    data = gh(f"repos/{full_name}")
    if isinstance(data, dict) and data.get("default_branch"):
        return data["default_branch"]
    return ""


def main() -> int:
    upstreams: dict[str, str] = {}
    if AUDIT_CACHE.exists():
        for entry in json.loads(AUDIT_CACHE.read_text(encoding="utf-8")):
            if entry.get("repo") in TARGETS and entry.get("upstream"):
                upstreams[entry["repo"]] = entry["upstream"]

    print("auditing forks carrying unique owner work (§12, §13)\n")
    results = []
    for repo in TARGETS:
        upstream = upstreams.get(repo)
        if not upstream:
            print(f"  {repo}: no resolved upstream — skipping")
            continue
        # Branches differ per repo AND per fork. Resolve both; assuming
        # `master` made every lookup 404 earlier.
        fork_branch = default_branch(f"{OWNER}/{repo}")
        upstream_branch = default_branch(upstream)
        print(f"  {repo}  (upstream {upstream})\n"
              f"    fork {fork_branch or '?'} vs upstream "
              f"{upstream_branch or '?'} ...", flush=True)
        result = audit_fork(repo, upstream, fork_branch, upstream_branch)
        results.append(result)
        if result.get("state") == "AUDITED":
            print(f"    ahead {result['ahead_by']} / behind {result['behind_by']}"
                  f"  files {result['changed_file_count']}"
                  f"  +{result['additions']} -{result['deletions']}")
            print(f"    clusters: {result['capability_clusters']}")
            if result["java_source_files"]:
                print(f"    JAVA SOURCE ({len(result['java_source_files'])}): "
                      f"{result['java_source_files'][:5]}")
            print(f"    deletion gate: {result['deletion_gate']}")
        else:
            print(f"    {result.get('note')}")
        print()

    out = REPO / "migration" / "evidence" / "owner_work_audit.json"
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    print(f"written: {out.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
