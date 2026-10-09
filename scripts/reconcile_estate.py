"""Reconcile the live estate against the migration catalog (§51 steps 4-8).

Answers three questions with LIVE data instead of trusting the October
inventory:

  1. Which catalog rows exist live, and which do not?
  2. Which live repos are NOT in the catalog at all?
  3. Which catalog rows are actually forks vs originals mislabelled?

Writes the reconciliation report. Deletes nothing (never did, never will).
"""

import csv
import json
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ESTATE = REPO_ROOT / "migration" / "evidence" / "live_estate.json"
CATALOG = (REPO_ROOT / "migration" / "evidence" / "catalog"
           / "Aetherius_Fork_Use_Case_Migration_Catalog_2026-10-08.csv")
OUT = REPO_ROOT / "migration" / "evidence" / "reconciliation.json"


def main() -> int:
    repos = json.loads(ESTATE.read_text(encoding="utf-8"))
    live = {r["name"]: r for r in repos}

    with CATALOG.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    catalog = {r["repository"].split("/", 1)[-1]: r for r in rows}

    in_both = sorted(set(live) & set(catalog))
    catalog_missing = sorted(set(catalog) - set(live))
    live_uncatalogued = sorted(set(live) - set(catalog))

    # Where live evidence contradicts the catalog's fork assumption.
    contradictions = []
    for name in in_both:
        live_fork = live[name]["fork"]
        cat_mode = catalog[name]["migration_mode"]
        if live_fork and cat_mode == "VERIFY_BEFORE_USE":
            contradictions.append(
                {"repo": name, "live": "FORK", "catalog": "VERIFY_BEFORE_USE",
                 "upstream": live[name].get("parent")})
    for name in in_both:
        if not live[name]["fork"]:
            contradictions.append(
                {"repo": name, "live": "ORIGINAL",
                 "catalog_category": catalog[name]["category"],
                 "note": "live says original; catalog may have misclassified"})

    report = {
        "live_total": len(live),
        "catalog_total": len(catalog),
        "matched": len(in_both),
        "catalog_rows_not_live": catalog_missing,
        "live_repos_uncatalogued": live_uncatalogued,
        "contradictions": contradictions,
        "live_originals": sorted(n for n, r in live.items() if not r["fork"]),
        "archived": sorted(r["name"] for r in repos if r["archived"]),
        "license_distribution": dict(
            Counter(r.get("license") or "UNKNOWN" for r in repos).most_common()),
    }
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"live repos          {len(live)}")
    print(f"catalog rows        {len(catalog)}")
    print(f"matched             {len(in_both)}")
    print(f"catalog rows not live ({len(catalog_missing)}):")
    for n in catalog_missing[:25]:
        print(f"  {n}")
    print(f"live uncatalogued ({len(live_uncatalogued)}):")
    for n in live_uncatalogued[:25]:
        print(f"  {n:44} fork={live[n]['fork']} up={live[n].get('parent')}")
    print(f"\ncontradictions      {len(contradictions)}")
    print(f"archived            {report['archived']}")
    print("\ntop licenses:")
    for lic, n in list(report["license_distribution"].items())[:10]:
        print(f"  {lic:16} {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
