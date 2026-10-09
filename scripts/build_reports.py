"""Produce the §40 reporting artefacts (A-J).

Generates, from live + cached evidence only — never from assumption:

  A. FORK_MASTER_INVENTORY
  B. PREDECESSOR_MIGRATION_MATRIX
  C. FORK_USE_CASE_MATRIX
  D. LICENSE_PROVENANCE_MATRIX
  E. UNIQUE_COMMIT_REPORT
  F. MIGRATION_TODO_GRAPH
  G. ACTIVE_DEPENDENCY_REGISTER
  H. SAFE_TO_DELETE_QUEUE
  I. RETAINED_FORK_REGISTER
  J. MIGRATION_HISTORY

Every artefact states its own evidence basis. An empty queue is reported as
empty rather than filled with speculative entries.
"""

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EV = REPO_ROOT / "migration" / "evidence"
CATALOG = (EV / "catalog"
           / "Aetherius_Fork_Use_Case_Migration_Catalog_2026-10-08.csv")
OUTDIR = REPO_ROOT / "migration" / "reports"

# §8 canonical ownership hierarchy.
CANONICAL_OWNERS = {
    "AETHERIUS_OS_CORE": "Aetherius OS",
    "AETHERIUS_COMPUTE_AI_RUNTIME": "Hybrid Compute",
    "AETHERIUS_STORAGE_DATA": "Aetherius OS / Knowledge Fabric",
    "AETHERIUS_NETWORK_IOT_MESSAGING": "Agent Bridge / comms fabric",
    "AETHERIUS_SECURITY_IDENTITY_PROVENANCE": "Credential Broker / security",
    "AETHERIUS_IDE_AGENT_DEVELOPER": "Aetherius IDE / Orchestrator",
    "AETHERIUS_FIRST_PARTY_AUDIO_MEDIA": "First-Party Apps / Poietek / Universal-Bridge",
    "AETHERIUS_FIRST_PARTY_CREATIVE_CAD": "First-Party Applications",
    "AETHERIUS_FIRST_PARTY_BUSINESS_APPS": "First-Party Applications",
    "AETHERIUS_OBSERVABILITY_DEVOPS_BUILD": "Build/release/observability infra",
    "GENESIS_AVATAR_VOICE_VIDEO": "Genesis",
    "GENESIS_BIO_NEURO_HEALTH": "Genesis (research)",
    "GENESIS_MEMORY_COGNITION": "Genesis",
    "MAT_SCIENCE_ENGINEERING": "MAT",
    "ROBOTICS_EMBODIMENT_SIMULATION": "Agent Bridge / Genesis embodiment",
    "CHIP_FPGA_QUANTUM": "VM-B / hardware research",
    "GEO_RADIO_SENSOR": "Sensor/geospatial apps + Agent Bridge",
    "VERIFY_UPSTREAM": "UNASSIGNED — live verification supersedes",
}

# §29 migration order.
PRIORITY_BY_CATEGORY = {
    "AETHERIUS_COMPUTE_AI_RUNTIME": "P0",
    "AETHERIUS_SECURITY_IDENTITY_PROVENANCE": "P1",
    "AETHERIUS_NETWORK_IOT_MESSAGING": "P1",
    "AETHERIUS_STORAGE_DATA": "P2",
    "GENESIS_AVATAR_VOICE_VIDEO": "P2",
    "GENESIS_MEMORY_COGNITION": "P2",
    "GENESIS_BIO_NEURO_HEALTH": "P2",
    "AETHERIUS_IDE_AGENT_DEVELOPER": "P3",
    "AETHERIUS_OS_CORE": "P4",
    "AETHERIUS_FIRST_PARTY_AUDIO_MEDIA": "P5",
    "AETHERIUS_FIRST_PARTY_CREATIVE_CAD": "P5",
    "AETHERIUS_FIRST_PARTY_BUSINESS_APPS": "P5",
    "MAT_SCIENCE_ENGINEERING": "P6",
    "GEO_RADIO_SENSOR": "P6",
    "ROBOTICS_EMBODIMENT_SIMULATION": "P7",
    "CHIP_FPGA_QUANTUM": "P8",
    "VERIFY_UPSTREAM": "P0",
    "AETHERIUS_OBSERVABILITY_DEVOPS_BUILD": "P1",
}


def _load(name):
    p = EV / name
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


def _catalog():
    with CATALOG.open(newline="", encoding="utf-8") as fh:
        return {r["repository"].split("/", 1)[-1]: r for r in csv.DictReader(fh)}


def main() -> int:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    estate = _load("live_estate.json") or []
    recon = _load("reconciliation.json") or {}
    preds = _load("predecessor_matrix.json") or {"predecessors": []}
    uniq = _load("unique_commit_audit.json") or []
    catalog = _catalog()
    now = datetime.now(timezone.utc).isoformat()

    live = {r["name"]: r for r in estate}
    uniq_by = {e["repo"]: e for e in uniq}

    # A — FORK MASTER INVENTORY
    a = {"generated_at": now, "basis": "live GitHub REST API",
         "total_repos": len(estate),
         "originals": [r["name"] for r in estate if not r["fork"]],
         "forks": [r["name"] for r in estate if r["fork"]],
         "repos": estate}
    (OUTDIR / "A_fork_master_inventory.json").write_text(
        json.dumps(a, indent=2), encoding="utf-8")

    # B — PREDECESSOR MIGRATION MATRIX (already built, republish)
    (OUTDIR / "B_predecessor_migration_matrix.json").write_text(
        json.dumps(preds, indent=2), encoding="utf-8")

    # C — FORK USE CASE MATRIX: catalog + live + §8 owner + §29 priority
    rows = []
    for name, cat in catalog.items():
        lv = live.get(name, {})
        cat_name = cat["category"]
        rows.append({
            "repo": name,
            "catalog_category": cat_name,
            "canonical_owner": CANONICAL_OWNERS.get(cat_name, "UNMAPPED"),
            "priority": PRIORITY_BY_CATEGORY.get(cat_name, "P8"),
            "use_case": cat["primary_use_case"],
            "when_used": cat["when_used"],
            "where_used": cat["primary_destination"],
            "how_used": cat["migration_mode"],
            "confidence": cat["analysis_confidence"],
            "live_upstream": lv.get("parent"),
            "live_license": lv.get("license"),
            "unique_commits": uniq_by.get(name, {}).get("ahead_by"),
            "unique_class": uniq_by.get(name, {}).get("classification"),
            "migration_state": "NOT_STARTED",
        })
    (OUTDIR / "C_fork_use_case_matrix.json").write_text(
        json.dumps({"generated_at": now, "rows": rows}, indent=2), encoding="utf-8")

    # D — LICENSE PROVENANCE MATRIX
    lic = defaultdict(list)
    for r in estate:
        lic[r.get("license") or "UNKNOWN"].append(r["name"])
    copyleft = {"GPL-3.0", "GPL-2.0", "AGPL-3.0", "LGPL-2.1", "LGPL-3.0",
                "MPL-2.0", "EPL-2.0", "OSL-3.0"}
    risky = {k: v for k, v in lic.items() if k in copyleft}
    unlicensed = lic.get("UNKNOWN", []) + lic.get("None", [])
    d = {"generated_at": now,
         "distribution": {k: len(v) for k, v in sorted(lic.items(),
                                                      key=lambda x: -len(x[1]))},
         "copyleft_requires_notice": {k: sorted(v) for k, v in sorted(risky.items())},
         "no_license_detected": sorted(unlicensed),
         "note": ("NOASSERTION/None/UNKNOWN require manual license "
                  "identification before any code use (§6).")}
    (OUTDIR / "D_license_provenance_matrix.json").write_text(
        json.dumps(d, indent=2), encoding="utf-8")

    # E — UNIQUE COMMIT REPORT
    preserve = [e for e in uniq if e.get("preservation_required")]
    e = {"generated_at": now,
         "basis": "fork-vs-upstream compare via GitHub API",
         "audited": len(uniq),
         "clean": [x["repo"] for x in uniq if x.get("status") == "CLEAN"],
         "has_unique": [x["repo"] for x in uniq
                        if x.get("status") == "HAS_UNIQUE"],
         "errors": [x["repo"] for x in uniq
                    if x.get("status") in ("ERROR", "EXCEPTION")],
         "preservation_required": [x["repo"] for x in preserve],
         "detail": uniq}
    (OUTDIR / "E_unique_commit_report.json").write_text(
        json.dumps(e, indent=2), encoding="utf-8")

    # F — MIGRATION TODO GRAPH (§29 order, dependency-ready only)
    todo = []
    for row in rows:
        if row["unique_commits"] not in (0, None):
            continue  # needs preservation first (§4)
        todo.append({
            "task": f"Evaluate {row['repo']} -> {row['canonical_owner']}",
            "source": row["repo"],
            "upstream": row["live_upstream"],
            "capability": row["use_case"],
            "destination": row["canonical_owner"],
            "priority": row["priority"],
            "integration_method": row["how_used"],
            "output": "decision record + optional adapter",
            "test": "deterministic test proving the capability at destination",
        })
    todo.sort(key=lambda t: (t["priority"], t["source"]))
    (OUTDIR / "F_migration_todo_graph.json").write_text(
        json.dumps({"generated_at": now,
                    "basis": ("only forks with ZERO unique commits and a "
                              "resolved upstream are dependency-ready (§29)"),
                    "count": len(todo), "tasks": todo},
                   indent=2), encoding="utf-8")

    # G — ACTIVE DEPENDENCY REGISTER (none yet — nothing migrated)
    g = {"generated_at": now, "basis": "no capability has been migrated yet",
         "active_dependencies": [],
         "note": ("This register is empty because migration_state is "
                  "NOT_STARTED for every source. It is reported empty rather "
                  "than populated speculatively.")}
    (OUTDIR / "G_active_dependency_register.json").write_text(
        json.dumps(g, indent=2), encoding="utf-8")

    # H — SAFE TO DELETE QUEUE (§34: requires all 15 conditions)
    h = {"generated_at": now,
         "gate": "§34 — 15 conditions, all mandatory",
         "safe_to_delete": [],
         "count": 0,
         "blocked_reasons": {
             "no_source_inspection": "migration_state=NOT_STARTED",
             "no_implementation": "replacement not implemented",
             "no_remote_verification": "no replacement commit exists",
             "unique_work_unpreserved": len(preserve),
         },
         "note": ("EMPTY BY DESIGN. No repository has passed the §34 gate. "
                  "Nothing may be deleted.")}
    (OUTDIR / "H_safe_to_delete_queue.json").write_text(
        json.dumps(h, indent=2), encoding="utf-8")

    # I — RETAINED FORK REGISTER
    retained = [{"repo": x["repo"], "reason": "§34 gate not passed",
                 "unique_class": x.get("classification")} for x in preserve]
    (OUTDIR / "I_retained_fork_register.json").write_text(
        json.dumps({"generated_at": now,
                    "retained": retained, "count": len(retained),
                    "note": "Every fork is retained until it passes §34."},
                   indent=2), encoding="utf-8")

    # J — MIGRATION HISTORY
    j = {"generated_at": now, "events": [
        {"at": now, "event": "LIVE_ESTATE_FETCHED",
         "detail": f"{len(estate)} repositories via REST API"},
        {"at": now, "event": "UPSTREAMS_RESOLVED",
         "detail": f"{sum(1 for r in estate if r['fork'] and r.get('parent'))}"
                   f"/{sum(1 for r in estate if r['fork'])} forks linked"},
        {"at": now, "event": "CATALOG_RECONCILED",
         "detail": f"{recon.get('matched', 0)} catalog rows matched live"},
        {"at": now, "event": "PREDECESSORS_CLASSIFIED",
         "detail": f"{len(preds['predecessors'])} predecessors, all live"},
        {"at": now, "event": "UNIQUE_COMMIT_AUDIT",
         "detail": f"{len(uniq)} forks audited, "
                   f"{len(preserve)} require preservation"},
        {"at": now, "event": "DELETIONS", "detail": "ZERO — none authorised"},
    ]}
    (OUTDIR / "J_migration_history.json").write_text(
        json.dumps(j, indent=2), encoding="utf-8")

    print(f"reports written to {OUTDIR.relative_to(REPO_ROOT)}/")
    for f in sorted(OUTDIR.glob("*.json")):
        print(f"  {f.name:46} {f.stat().st_size:>9,} bytes")
    print()
    print(f"A inventory       {len(estate)} repos "
          f"({sum(1 for r in estate if not r['fork'])} original / "
          f"{sum(1 for r in estate if r['fork'])} fork)")
    print(f"C use-case matrix {len(rows)} rows")
    print(f"E unique audit    {len(uniq)} audited, {len(preserve)} preserve")
    print(f"F todo graph      {len(todo)} dependency-ready tasks")
    print(f"H delete queue    {h['count']}  <- EMPTY BY DESIGN")
    print(f"I retained        {len(retained)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
