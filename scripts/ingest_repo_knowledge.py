"""Ingest the LIVE estate into Knowledge Fabric records (§6, §7, §10, §11).

Converts ``migration/evidence/live_estate.json`` — already fetched and
upstream-resolved by the migration programme — into §10 normalized records,
enriched with the §9 predecessor relationships and the §5 unique-commit
audit. Deletes nothing. Reuses the existing fork registry rather than
building a second one (§8).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from knowledge_fabric.repo_ingestion import (
    ACTIVE_CANONICAL, ARCHIVED, FORK, FORK_OF, PREDECESSOR,
    PREDECESSOR_OF, ChangeDetector, RepositoryKnowledgeRecord,
    classify_status, stable_repo_id, utc_now,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
EV = REPO_ROOT / "migration" / "evidence"
ESTATE = EV / "live_estate.json"
PREDECESSOR_MATRIX = EV / "predecessor_matrix.json"
UNIQUE_AUDIT = EV / "unique_commit_audit.json"
STATE = REPO_ROOT / "knowledge_fabric" / "evidence" / "repo_knowledge_state.json"
LINKS = REPO_ROOT / "knowledge_fabric" / "evidence" / "repo_relationship_graph.json"

# §8/§9 owner-authoritative predecessor relationships, with destinations.
PREDECESSOR_TARGETS = {
    "aetherium": "Aetherius-OS",
    "Aetherial": "Aetherius-OS",
    "aetherial-platform": "Aetherius-OS",
    "Niche_platform": "Aetherius-OS",
    "Quantum-OS": "Aetherius-OS",
    "Crossplatform---multiplatform": "Aetherius-OS",
    "QVA-merged": "Aetherius-OS",
    "Veyra": "Aetherius-OS",
    "VirtualAssistant": "Genesis",
}

# §39 protected canonical current projects.
CANONICAL_PROJECTS = {
    "Aetherius-OS", "Genesis", "Agent-Bridge", "IDE-Workspace",
    "Materials-Atlas-Table-Codex---MAT", "Universal-Bridge", "Poietek",
}


def main() -> int:
    estate = json.loads(ESTATE.read_text(encoding="utf-8"))
    pred_matrix = json.loads(PREDECESSOR_MATRIX.read_text(encoding="utf-8"))
    unique = {e["repo"]: e for e in
              json.loads(UNIQUE_AUDIT.read_text(encoding="utf-8"))}
    pred_names = {p["repository"] for p in pred_matrix["predecessors"]}

    detector = ChangeDetector()
    detector.load_state(STATE)

    records = []
    actions = {"NEW": 0, "CHANGED": 0, "UNCHANGED": 0}
    changed_repos = []

    for live in sorted(estate, key=lambda r: r["name"].lower()):
        name = live["name"]
        rid = stable_repo_id("jayprophit", name)
        is_pred = name in pred_names
        is_canon = name in CANONICAL_PROJECTS
        status = classify_status(live, is_predecessor=is_pred,
                                 is_canonical=is_canon)
        uniq = unique.get(name, {})
        rec = RepositoryKnowledgeRecord(
            repo_id=rid,
            name=name,
            owner="jayprophit",
            url=live["url"],
            visibility="private" if live.get("private") else "public",
            is_fork=bool(live["fork"]),
            upstream=live.get("parent"),
            license=live.get("license"),
            default_branch=live.get("default_branch"),
            head_sha=None,  # REST list omits SHA; recorded as unknown, not guessed
            updated_at=live.get("pushed_at"),
            languages=[live["language"]] if live.get("language") else [],
            status=status,
            projects=[PREDECESSOR_TARGETS[name]] if name in PREDECESSOR_TARGETS else (
                [name] if is_canon else []),
            predecessor_of=PREDECESSOR_TARGETS.get(name),
            migration_state=("NOT_STARTED" if is_pred else "NOT_APPLICABLE"),
            archived=bool(live.get("archived")),
            stars=live.get("stars") or 0,
            size_kb=live.get("size_kb"),
            unique_commits=uniq.get("ahead_by"),
            provenance={
                "source": "GitHub REST API (live)",
                "fetched_at": utc_now_safe(live),
                "unique_content_class": uniq.get("classification"),
                "preservation_required": uniq.get("preservation_required"),
            },
        )
        rec.finalize()
        action, reason = detector.evaluate(rec)
        actions[action] += 1
        if action != "UNCHANGED":
            changed_repos.append({"repo": name, "action": action,
                                  "reason": reason})
        # Preserve last_indexed for unchanged records.
        prior = detector.known.get(rid)
        if action == "UNCHANGED" and prior is not None:
            rec.last_indexed = prior.last_indexed
        records.append(rec)

    detector.save_state(STATE, records)

    # §14 relationship graph.
    nodes = [{"repo_id": r.repo_id, "name": r.name, "status": r.status,
              "is_fork": r.is_fork, "upstream": r.upstream} for r in records]
    edges = []
    for r in records:
        if r.is_fork and r.upstream:
            edges.append({"from": r.repo_id, "to": f"ext:{r.upstream}",
                          "type": FORK_OF, "external": True})
        if r.predecessor_of:
            edges.append({"from": r.repo_id, "to": r.predecessor_of,
                          "type": PREDECESSOR_OF, "external": False})
    LINKS.parent.mkdir(parents=True, exist_ok=True)
    LINKS.write_text(json.dumps({
        "generated_at": utc_now(),
        "nodes": nodes, "edges": edges,
        "edge_counts": {
            FORK_OF: sum(1 for e in edges if e["type"] == FORK_OF),
            PREDECESSOR_OF: sum(1 for e in edges
                                if e["type"] == PREDECESSOR_OF),
        },
    }, indent=2), encoding="utf-8")

    print(f"records written     {len(records)}")
    print(f"  NEW               {actions['NEW']}")
    print(f"  CHANGED           {actions['CHANGED']}")
    print(f"  UNCHANGED (skip)  {actions['UNCHANGED']}")
    print(f"fork edges          {sum(1 for e in edges if e['type'] == FORK_OF)}")
    print(f"predecessor edges   {sum(1 for e in edges if e['type'] == PREDECESSOR_OF)}")
    print(f"archived            {sum(1 for r in records if r.archived)}")
    print(f"state -> {STATE.relative_to(REPO_ROOT)}")
    print(f"graph -> {LINKS.relative_to(REPO_ROOT)}")
    return 0


def utc_now_safe(live: dict) -> str:
    return live.get("pushed_at") or "unknown"


if __name__ == "__main__":
    raise SystemExit(main())
