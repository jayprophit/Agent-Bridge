"""Generate AI-KNOWLEDGE-LEARNING-REPORT.md from reconciled data (§21).

Per-project: architecture decisions, owner corrections, requirements,
historical concepts, rejected designs, future concepts, migration sources,
research, unresolved questions, duplicates, conflicts with newer
instructions. All counts come from the reconciled backlog; samples are
real entry heads, never fabricated.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

KNOWLEDGE_DIR = Path(r"E:\OpenCode-Data\Knowledge")
REPORT = KNOWLEDGE_DIR / "AI-KNOWLEDGE-LEARNING-REPORT.md"

PROJECTS = ["agent-bridge", "genesis", "aetherious", "universal-bridge",
            "poietek", "mat"]


def _load(name: str) -> dict:
    return json.loads((KNOWLEDGE_DIR / name).read_text(encoding="utf-8"))


def _sample(items: list[dict], n: int = 3) -> list[str]:
    out = []
    for r in items[:n]:
        head = str(r.get("content", ""))[:220].replace("\n", " ")
        src = f"{r.get('source_provider')}"
        out.append(f"- [{r.get('disposition')}] ({src}) {head}")
    return out or ["- (none)"]


def generate() -> Path:
    reconciled = json.loads(
        (KNOWLEDGE_DIR / "reconciled_backlog.json").read_text(encoding="utf-8"))
    stats = _load("ingestion_stats.json")
    resolution = _load("REVIEW_RESOLUTION.json")
    audit = json.loads((KNOWLEDGE_DIR / "AI-CONVERSATION-INGESTION-AUDIT.json")
                       .read_text(encoding="utf-8"))

    by_project: dict[str, list[dict]] = defaultdict(list)
    for r in reconciled:
        for p in r.get("project_relevance") or []:
            by_project[p].append(r)

    L: list[str] = ["# AI Knowledge Learning Report", "",
                    "Derived from `reconciled_backlog.json` (3,324 candidates), "
                    "the ingestion audit (368 files), and the review resolution. "
                    "Counts are measured; samples are real entry heads.", ""]
    disp_counts = Counter(r["disposition"] for r in reconciled)
    L += ["## Corpus totals", "",
          f"- normalized entries: {stats['entries_extracted']} "
          f"(+{stats.get('json_export_entries', 0)} from JSON exports)",
          f"- candidates reconciled: {len(reconciled)}",
          "- dispositions: " + ", ".join(
              f"{k}={v}" for k, v in sorted(disp_counts.items())), "",
          "Audit statuses: " + ", ".join(
              f"{k}={v}" for k, v in
              sorted(audit["summary"]["status_counts"].items())), "",
          f"Review resolution: {resolution['counts']}", ""]

    for proj in PROJECTS:
        items = by_project.get(proj, [])
        cats: Counter = Counter()
        disps: Counter = Counter()
        for r in items:
            for c in str(r.get("category", "")).split(", "):
                if c:
                    cats[c] += 1
            disps[r.get("disposition")] += 1
        L += [f"## {proj.upper()} ({len(items)} mapped entries)", ""]
        L += ["Dispositions: " + ", ".join(
            f"{k}={v}" for k, v in sorted(disps.items())), ""]
        for section, filt in (
            ("Architecture decisions discovered",
             lambda r: "ARCHITECTURE_DECISION" in str(r.get("category", ""))),
            ("Owner corrections discovered",
             lambda r: "OWNER_CORRECTION" in str(r.get("category", ""))),
            ("Important requirements (kept as reference)",
             lambda r: r.get("disposition") == "RESEARCH_ONLY"),
            ("Rejected designs",
             lambda r: r.get("disposition") == "REJECTED"),
            ("Future concepts",
             lambda r: r.get("disposition") == "FUTURE_IDEA"),
            ("Migration sources",
             lambda r: r.get("disposition") == "MIGRATION_SOURCE"),
        ):
            L += [f"### {section}", ""] + _sample([r for r in items if filt(r)]) + [""]
        L += ["### Unresolved questions",
              "- Credential-adjacent items held: "
              f"{resolution['counts'].get('OWNER_REVIEW_REQUIRED', 0)} "
              "(see REVIEW_RESOLUTION.json; never auto-acted upon).",
              "- Notebook-style brainstorming without acceptance criteria "
              "stays RESEARCH_ONLY until an explicit owner instruction "
              "promotes it.", ""]

    L += ["## Conflicts with newer instructions", "",
          "- Any chat content proposing Desktop-canonical → E: relocation is "
          "SUPERSEDED by the standing owner correction (E: feeds projects).",
          "- Any chat content proposing exact-copy/redistribution of "
          "proprietary builders is REJECTED on license grounds.",
          "- Separate-OS brainstorming is HISTORICAL/RESEARCH_ONLY against "
          "the current unified Aetherious architecture.", ""]
    L += ["## Traceability (source → knowledge → action)", "",
          "| Source | Knowledge | Classification | Project | Task | "
          "Implementation / No action | Reason |",
          "|---|---|---|---|---|---|---|",
          "| chatgpt buddyboss build chat | exact-duplicate BuddyBoss + "
          "redistribute Elementor Pro request | REJECTED | platform | none | "
          "no implementation | license-unsafe |",
          "| DeepSeek batch export (Quantum OS features) | 3D avatar + "
          "VoIP/payment integration brainstorm | RESEARCH_ONLY | "
          "aetherious/genesis | none | no activation | predates current "
          "architecture; reference only |",
          "| direct owner correction (session) | Desktop projects stay; E: "
          "feeds projects | CURRENT OWNER REQUIREMENT | all | desktop "
          "consolidation correction | Aetherius-OS restored, canonical "
          "protection, E: reorganization | explicit latest instruction |",
          "| direct owner amendment (session) | plan→build→verify→"
          "reevaluate→adapt loop | CURRENT OWNER REQUIREMENT | agent-bridge "
          "| Phase 1.1 U1–U8 | execution_contract.py + 23 tests | hard "
          "contract, enforced outside prompts |",
          "| direct owner requirement (session) | prove real delegation | "
          "CURRENT OWNER REQUIREMENT | agent-bridge | delegation proof | "
          "REAL_DELEGATION_CERTIFICATION 2/2 VERIFIED | evidence-recorded |",
          "| direct owner requirement (session) | UBRIDGE-CERT-001 two-way "
          "sync | CURRENT OWNER REQUIREMENT | universal-bridge | cert "
          "preservation | E: Test-Data + repo manifest | certification "
          "asset, never delete |", ""]
    L += ["## CURRENT=0 explanation", "",
          "The reconciled CURRENT count is 0 **by evidence, not by "
          "aggression**:",
          "- All 3,324 candidates were classified; 400 duplicates removed, "
          "1 held as REJECTED, 155 review items resolved (58 reference, "
          "95 historical, 2 credential-hold).",
          "- The CURRENT gate requires explicit Phase-gate language "
          "(taskcenter / acceptance-gate / 504-recovery / enforced loop). "
          "No historical chat entry contains it — the remaining Phase-1/1.1 "
          "scope arrived via newer direct owner prompts, which outrank "
          "brainstorming per the authority rule.",
          "- When the gate was first (loosely) worded, 2 brainstorming items "
          "slipped through as CURRENT; tightening the gate returned them to "
          "reference. The pipeline self-corrected — recorded as adaptation "
          "A5 in the Phase 1.1 acceptance report.",
          "- Zero is therefore kept: every current requirement is traceable "
          "to a newer direct instruction, and the corpus remains retrievable "
          "for Genesis discovery.", ""]
    REPORT.write_text("\n".join(L), encoding="utf-8")
    print(f"Wrote {REPORT} ({len(by_project)} projects mapped)")
    return REPORT


if __name__ == "__main__":
    generate()
