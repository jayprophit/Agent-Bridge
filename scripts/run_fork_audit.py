"""Live fork/upstream audit runner — §10 gate step 1, BOUNDED and READ-ONLY.

This script NEVER deletes, archives, or mutates any repository. It only
reads live GitHub state and records it into the permanent provenance
registry. Deletion is a separate, later, human-gated decision.

Usage:
    python scripts/run_fork_audit.py --limit 10
    python scripts/run_fork_audit.py --limit 10 --category VERIFY_UPSTREAM
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from migration.auditor import AuditorUnavailable, audit_batch, gh_available
from migration.provenance import ProvenanceRegistry, load_catalog, \
    records_from_catalog

def _default_catalog() -> str:
    """Locate the catalog without hardcoding a personal path.

    The repo is PUBLIC and hygiene rejects personal absolute paths, so the
    owner's Downloads folder is discovered at runtime instead.
    """
    env = os.environ.get("AETHERIUS_MIGRATION_CATALOG")
    if env and os.path.isfile(env):
        return env
    candidates = [
        os.path.join("Downloads",
                     "Aetherius_Fork_Use_Case_Migration_Catalog_2026-10-08.csv"),
        os.path.join("migration", "evidence", "catalog",
                     "Aetherius_Fork_Use_Case_Migration_Catalog_2026-10-08.csv"),
    ]
    home = os.path.expanduser("~")
    roots = [os.getcwd(), home,
             os.path.join(home, "OneDrive"),
             os.path.join(home, "AppData", "Local", "hermes", "profiles",
                          "aetherius-build", "cache", "scratch")]
    for base in roots:
        for rel in candidates:
            path = os.path.join(base, *rel.split("/"))
            if os.path.isfile(path):
                return path
    return candidates[1]      # deterministic default for the error message


CATALOG = _default_catalog()
REGISTRY = os.path.join("migration", "evidence", "provenance_registry.json")


def main() -> int:
    ap = argparse.ArgumentParser(description="Aetherius fork/upstream audit")
    ap.add_argument("--limit", type=int, default=10,
                    help="max repos to audit this run (default 10)")
    ap.add_argument("--category", default=None,
                    help="only audit rows in this catalog category")
    ap.add_argument("--catalog", default=CATALOG)
    ap.add_argument("--registry", default=REGISTRY)
    args = ap.parse_args()

    ok, reason = gh_available()
    if not ok:
        print(f"AUDIT UNAVAILABLE: {reason}")
        print("No records were modified. Nothing was deleted.")
        return 2

    rows = load_catalog(args.catalog)
    if args.category:
        rows = [r for r in rows if r["category"] == args.category]
        print(f"filtered to category={args.category}: {len(rows)} rows")

    records = records_from_catalog(args.catalog)
    if args.category:
        wanted = {r["repository"] for r in rows}
        records = [r for r in records if r.source_repo in wanted]

    reg = ProvenanceRegistry(args.registry)
    # Merge: keep prior audits, only audit records not yet verified.
    todo = []
    for rec in records:
        existing = reg.by_source(rec.source_repo)
        if existing is None:
            reg.add(rec)
            todo.append(rec)
        elif existing.upstream.audit_status == "NOT_CHECKED":
            todo.append(existing)
        else:
            todo.append(existing)   # re-audit is idempotent and cheap

    batch = todo[:args.limit]
    print(f"auditing {len(batch)} of {len(todo)} pending repositories "
          f"(READ-ONLY)\n")

    try:
        result = audit_batch(batch, limit=len(batch),
                             progress=lambda i, n, repo, st:
                             print(f"  [{i}/{n}] {repo} -> {st}"))
    except AuditorUnavailable as exc:
        print(f"AUDIT UNAVAILABLE: {exc}")
        return 2

    sha = reg.save()
    print(f"\nby_status: {result['by_status']}")
    if result["failures"]:
        print(f"failures: {len(result['failures'])}")
        for f in result["failures"][:5]:
            print(f"  {f}")
    print(f"registry sha256: {sha}")
    print(f"summary: {reg.summary()}")
    print("\nNOTHING WAS DELETED. Deletion requires the full §10 gate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
