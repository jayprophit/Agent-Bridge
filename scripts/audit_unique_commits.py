"""Estate-wide unique-commit audit (§5, §51 step 6) — READ-ONLY.

For every fork with a resolved upstream, compares fork vs upstream and
classifies any unique content per §5. This is the data that determines
which forks hold owner-authored work and therefore MUST NOT be deleted.

Bounded: forks are fixed by the estate, lookups are concurrent, and results
are cached to disk so the audit is resumable and never re-hits GitHub for
work already done (§48).
"""

import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from migration.unique_audit import (
    classify_unique_content, fork_vs_upstream,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
ESTATE = REPO_ROOT / "migration" / "evidence" / "live_estate.json"
CACHE = REPO_ROOT / "migration" / "evidence" / "unique_commit_audit.json"
LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 0  # 0 = all


def audit_one(repo: dict) -> dict:
    name = repo["name"]
    if not repo.get("fork") or not repo.get("parent"):
        return {"repo": name, "status": "SKIPPED_NOT_FORK"}
    upstream = repo.get("parent")
    result = fork_vs_upstream(
        fork=f"jayprophit/{name}",
        upstream=upstream,
        upstream_branch=repo.get("parent_branch") or "HEAD",
        fork_branch=repo.get("default_branch") or "main",
    )
    ahead = result.get("ahead_by")
    files = result.get("files") or []
    entry = {
        "repo": name,
        "upstream": upstream,
        "ahead_by": ahead,
        "behind_by": result.get("behind_by"),
        "unique_files": files[:50],
        "unique_file_count": len(files),
        "audited_at": datetime.now(timezone.utc).isoformat(),
    }
    if ahead is None:
        entry["status"] = "ERROR"
        entry["error"] = result.get("error", "unknown")
        entry["classification"] = "UNKNOWN"
        entry["preservation_required"] = True
    elif ahead == 0:
        entry["status"] = "CLEAN"
        entry["classification"] = "NONE"
        entry["preservation_required"] = False
    else:
        cls = classify_unique_content(files, ahead)
        entry["status"] = "HAS_UNIQUE"
        entry["classification"] = cls.value
        entry["preservation_required"] = True
    return entry


def main() -> int:
    repos = json.loads(ESTATE.read_text(encoding="utf-8"))
    existing = {}
    if CACHE.is_file():
        existing = {e["repo"]: e for e in
                    json.loads(CACHE.read_text(encoding="utf-8"))}

    todo = [r for r in repos if r["name"] not in existing]
    if LIMIT:
        todo = todo[:LIMIT]

    print(f"forks total      {sum(1 for r in repos if r['fork'])}")
    print(f"already audited  {len(existing)}")
    print(f"auditing now     {len(todo)}")

    results = dict(existing)
    done = 0
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(audit_one, r): r["name"] for r in todo}
        for fut in as_completed(futures):
            try:
                entry = fut.result()
            except Exception as exc:  # a single failure must not abort the run
                entry = {"repo": futures[fut], "status": "EXCEPTION",
                         "error": str(exc)[:200],
                         "classification": "UNKNOWN",
                         "preservation_required": True}
            results[entry["repo"]] = entry
            done += 1
            if done % 20 == 0:
                print(f"  {done}/{len(todo)}")

    out = sorted(results.values(), key=lambda e: e["repo"])
    CACHE.write_text(json.dumps(out, indent=2), encoding="utf-8")

    clean = [e for e in out if e["status"] == "CLEAN"]
    unique = [e for e in out if e["status"] == "HAS_UNIQUE"]
    errors = [e for e in out if e["status"] in ("ERROR", "EXCEPTION")]
    preserved = [e for e in out if e.get("preservation_required")]

    print()
    print(f"CLEAN (no owner work)     {len(clean)}")
    print(f"HAS UNIQUE (preserve!)    {len(unique)}")
    print(f"errors                    {len(errors)}")
    print(f"preservation required     {len(preserved)}")
    if unique:
        print("\nFORKS WITH OWNER-AUTHORED WORK — must NOT be deleted:")
        for e in sorted(unique, key=lambda x: x["repo"]):
            print(f"  {e['repo']:44} +{e['ahead_by']} {e['classification']}")
    if errors:
        print("\nERRORS (treated as preservation-required):")
        for e in errors[:20]:
            print(f"  {e['repo']:44} {str(e.get('error'))[:60]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
