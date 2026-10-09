"""Build the AETHERIUS OS predecessor migration matrix (§9, §42, §51 step 8).

For each named predecessor, records live-verified facts (existence, license,
branch, last activity, fork status) and the owner's authoritative
classification and destination from §0 and §9.

This is a CLASSIFICATION matrix, not a code audit: it states what the owner
has directed and what live evidence confirms. Per-repo capability mining
(§10) is downstream work requiring actual source inspection.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ESTATE = REPO_ROOT / "migration" / "evidence" / "live_estate.json"
OUT = REPO_ROOT / "migration" / "evidence" / "predecessor_matrix.json"

# §0 owner-authoritative classifications.
PREDECESSORS = {
    "aetherium": {
        "lineage": "earliest Aetherius platform attempt",
        "intention": "Aetherius-branded platform, pre-OS",
        "destination": "Aetherius OS",
        "mine": ["platform concepts", "settings", "identity",
                 "service boundaries", "reusable code"],
    },
    "Aetherial": {
        "lineage": "early platform attempt",
        "intention": "Aetherius platform, earlier architecture",
        "destination": "Aetherius OS",
        "mine": ["platform architecture", "UI/runtime assumptions",
                 "service boundaries", "abandoned requirements"],
    },
    "aetherial-platform": {
        "lineage": "aetherial continuation",
        "intention": "platform/web/service architecture",
        "destination": "Aetherius OS + shared platform services",
        "mine": ["platform/web/service architecture",
                 "cross-device/product concepts", "schemas"],
    },
    "Niche_platform": {
        "lineage": "platform experiment",
        "intention": "marketplace/community/application platform",
        "destination": "Aetherius OS / First-Party App Ecosystem",
        "mine": ["marketplace/community/application-platform ideas",
                 "reusable workflows"],
    },
    "Quantum-OS": {
        "lineage": "OS experiment, superseded",
        "intention": "binary/ternary/quantum compute OS",
        "destination": "Aetherius OS + VM-B",
        "mine": ["binary/ternary/quantum compute abstractions",
                 "HAL/VM ideas", "scheduling", "interface concepts"],
        "caution": "preserve real-vs-simulated distinction",
    },
    "Crossplatform---multiplatform": {
        "lineage": "cross-device experiment",
        "intention": "cross-device/cross-platform packaging and runtime",
        "destination": "Aetherius OS SDK/runtime + first-party app framework",
        "mine": ["cross-device/cross-platform packaging",
                 "UI and runtime abstraction"],
    },
    "QVA-merged": {
        "lineage": "MIXED — predates current clean boundaries",
        "intention": "merged platform + assistant + avatar",
        "destination": "SPLIT: Aetherius OS / Agent Bridge / Genesis",
        "mine": ["OS/platform/runtime concepts -> Aetherius OS",
                 "model/tool access -> Agent Bridge + Hybrid Compute",
                 "assistant/avatar/identity -> Genesis"],
        "caution": "must be DECOMPOSED (§12), not migrated wholesale",
    },
    "Veyra": {
        "lineage": "LATEST predecessor — owner-corrected to FAILED",
        "intention": "sovereign platform (README frames it as finance)",
        "destination": ("Aetherius OS / Agent Bridge / Hybrid Compute / "
                        "Knowledge Fabric; finance -> future Aetherius Finance app"),
        "mine": ["model/inference architecture", "memory architecture",
                 "agent orchestration lessons", "API gateway patterns",
                 "event-driven architecture", "cross-device frontends",
                 "Docker/Kubernetes/Terraform",
                 "observability/security patterns",
                 "finance-specific functionality"],
        "caution": ("do NOT migrate Veyra finance logic into OS kernel (§11); "
                    "finance-specific features do not define the new OS"),
    },
}

# §13 Genesis avatar/digital-twin predecessors (separate gate, §50).
GENESIS_PREDECESSORS = {
    "VirtualAssistant": {
        "destination": "Genesis Master Implementation",
        "mine": ["avatar", "voice", "interaction", "digital-twin",
                 "assistant UX", "continuity ideas"],
        "caution": "ONE Genesis identity — do not create another assistant",
    },
}


def main() -> int:
    repos = {r["name"]: r for r in
             json.loads(ESTATE.read_text(encoding="utf-8"))}

    matrix = []
    for name, spec in {**PREDECESSORS, **GENESIS_PREDECESSORS}.items():
        live = repos.get(name)
        entry = {
            "repository": name,
            "exists_live": live is not None,
            "classification": ("PREDECESSOR"
                               if name in PREDECESSORS
                               else "GENESIS_PREDECESSOR"),
            "gate": ("AETHERIUS_OS_PREDECESSOR" if name in PREDECESSORS
                     else "GENESIS_AVATAR_DIGITAL_TWIN"),
            "owner_directed_destination": spec["destination"],
            "capabilities_to_mine": spec["mine"],
            "caution": spec.get("caution"),
        }
        if live:
            entry["live_evidence"] = {
                "url": live["url"],
                "fork": live["fork"],
                "upstream": live.get("parent"),
                "default_branch": live.get("default_branch"),
                "license": live.get("license"),
                "last_push": live.get("pushed_at"),
                "size_kb": live.get("size_kb"),
                "language": live.get("language"),
                "archived": live.get("archived"),
                "stars": live.get("stars"),
            }
        # Migration state is NOT claimed — no source inspection has occurred.
        entry["migration_state"] = ("NOT_STARTED"
                                    if live is not None else "NOT_FOUND_LIVE")
        entry["safe_to_delete"] = False
        entry["provenance_recorded"] = False
        matrix.append(entry)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "basis": "§9/§42/§43 owner-authoritative classification + LIVE evidence",
        "note": ("migration_state=NOT_STARTED means no source inspection has "
                 "happened. This matrix records WHAT to mine and WHERE it "
                 "goes; capability extraction (§10) is downstream work."),
        "predecessors": matrix,
    }
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    missing = [e["repository"] for e in matrix if not e["exists_live"]]
    print(f"predecessors classified: {len(matrix)}")
    print(f"  exist live: {len(matrix) - len(missing)}")
    print(f"  NOT live  : {len(missing)} {missing}")
    print()
    for e in matrix:
        ev = e.get("live_evidence", {})
        print(f"{e['repository']:32} {str(ev.get('license')):14} "
              f"{str(ev.get('last_push'))[:10]:12} {e['migration_state']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
