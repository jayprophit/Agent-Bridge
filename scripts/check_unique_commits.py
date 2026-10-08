"""Unique-commit detection (§10 gate step 9 precheck) — READ-ONLY.

For each audited fork, compares the fork's default branch against the
upstream default branch using the UPSTREAM repo's compare endpoint:

    repos/<upstream>/compare/<upstream-branch>...<fork-owner>:<fork-branch>

ahead_by > 0 means the fork carries commits upstream does not have. Those
commits are irrecoverable if the fork is deleted without preservation, so
this measurement decides whether step 9 has anything to preserve.

Nothing is written to any repository. Output is JSON on stdout.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from migration.auditor import gh_available
from migration.provenance import ProvenanceRegistry

REGISTRY = os.path.join("migration", "evidence", "provenance_registry.json")


def compare(fork_full: str, upstream_full: str, fork_branch: str,
            upstream_branch: str) -> dict:
    """Compare fork branch against upstream branch via the upstream repo."""
    import subprocess
    fork_owner, _ = fork_full.split("/", 1)
    basehead = f"{upstream_branch}...{fork_owner}:{fork_branch}"
    proc = subprocess.run(
        ["gh", "api", f"repos/{upstream_full}/compare/{basehead}",
         "--jq", "[.ahead_by, .behind_by, .status] | @tsv"],
        capture_output=True, text=True, timeout=90)
    if proc.returncode != 0:
        return {"has_unique_commits": None,
                "error": (proc.stderr or proc.stdout or "").strip()[:200]}
    parts = [p.strip() for p in proc.stdout.strip().split("\t") if p.strip()]
    if len(parts) < 2:
        return {"has_unique_commits": None, "error": "unexpected compare output"}
    try:
        ahead, behind = int(parts[0]), int(parts[1])
    except ValueError:
        return {"has_unique_commits": None, "error": "unparseable output"}
    return {"has_unique_commits": ahead > 0, "ahead_by": ahead,
            "behind_by": behind, "status": parts[2] if len(parts) > 2 else None}


def main() -> int:
    ok, reason = gh_available()
    if not ok:
        print(f"UNAVAILABLE: {reason}")
        return 2

    reg = ProvenanceRegistry(REGISTRY)
    results = []
    for rec in reg.all():
        up = rec.upstream
        if up.audit_status != "VERIFIED" or not up.upstream_full_name:
            continue
        fork_branch = up.fork_default_branch or "HEAD"
        upstream_branch = up.upstream_default_branch or "HEAD"
        res = compare(rec.source_repo, up.upstream_full_name,
                      fork_branch, upstream_branch)
        if res.get("has_unique_commits") is not None:
            rec.unique_commits.has_unique_commits = res["has_unique_commits"]
            rec.unique_commits.unique_commit_count = res["ahead_by"]
            rec.unique_commits.ahead_by = res["ahead_by"]
            rec.unique_commits.behind_by = res["behind_by"]
        results.append({"repo": rec.source_repo,
                        "upstream": up.upstream_full_name,
                        "fork_branch": fork_branch,
                        "upstream_branch": upstream_branch, **res})
        flag = res.get("has_unique_commits")
        marker = ("UNIQUE — MUST PRESERVE" if flag else
                  "clean (no unique commits)" if flag is False else "unknown")
        print(f"{rec.source_repo:34} {up.upstream_full_name:36} {marker}")

    reg.save()
    unique = [r for r in results if r.get("has_unique_commits") is True]
    unknown = [r for r in results if r.get("has_unique_commits") is None]
    print(f"\nchecked={len(results)} unique={len(unique)} "
          f"unknown={len(unknown)}")
    print(json.dumps({"results": results}, indent=2)[:4000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
