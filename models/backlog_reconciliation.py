"""Reconcile AI-conversation extracted tasks into a CURRENT backlog.

Owner rule: the raw 64,833-entry corpus stays available for retrieval,
but the active task graph must contain only genuine current work.
The 2,397 "actionable" extractions are candidates, NOT requirements.

Each candidate is classified as one of:
  CURRENT_REQUIREMENT, ALREADY_VERIFIED, IMPLEMENTED_UNVERIFIED,
  DUPLICATE, SUPERSEDED, REJECTED, HISTORICAL, MIGRATION_SOURCE,
  FUTURE_IDEA, RESEARCH_ONLY, OWNER_REVIEW_REQUIRED

Deduplication: normalized content hash; first occurrence wins.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

KNOWLEDGE_DIR = Path(r"E:\OpenCode-Data\Knowledge")
ACTIONABLE_PATH = KNOWLEDGE_DIR / "actionable_tasks.json"
OUTPUT_PATH = KNOWLEDGE_DIR / "reconciled_backlog.json"
CURRENT_PATH = KNOWLEDGE_DIR / "CURRENT_BACKLOG.json"

VERIFIED_WORK_PATTERNS = [
    r"62\s*/\s*62", r"baseline tests?.*(pass|green)",
    r"real (worker )?delegation.*(prov|verif|certif)",
    r"fibonacci.*fix", r"add_?function.*fix",
    r"desktop consolidation", r"duplicate.*(genesis|mat|poietek|universal.bridge).*merg",
    r"downloads? (reorg|re-?org|cleanup|empty)",
    r"ubridge-cert-001.*(mov|preserv|certif)",
    r"knowledge ingestion|64,?833 entries|actionable tasks.*ingest",
    r"requirement-based routing|route_by_requirements",
    r"model fitness|capability discovery|benchmark.*(suite|runner)",
    r"merkle.*dag|work.?proof|problem.*memory|resource.?ledger",
]

SUPERSEDED_PATTERNS = [
    r"move (the )?(genesis|aetheri?ous|poietek|universal.bridge|mat|agent.bridge|ide).{0,30}to e:",
    r"desktop.{0,20}(repo|project).{0,20}(to|onto) e:",
    r"treat downloads as permanent",
    r"create .* subfolders inside downloads and call .* complete",
]

REJECTED_PATTERNS = [
    r"exactly the same (a duplicate|copy)",
    r"clone .* exactly",
    r"redistribut.*elementor pro",
    r"duplicate.*buddyboss.*(demo|exact)",
    r"reverse-engineer.*(buddyboss|elementor)",
]

REVIEW_PATTERNS = [
    r"password|passwd|secret|api[_-]?key|private[_-]?key|seed phrase",
    r"\bpublish\b.*(public|github|store)", r"public release",
    r"\bformat\b.*driv", r"wipe|erase .*disk",
    r"real.?money|mainnet|financial transaction",
    r"credential",
]

FUTURE_PATTERNS = [
    r"\bsomeday\b", r"\beventually\b", r"later we could",
    r"idea for later", r"potential future",
]

MIGRATION_PATTERNS = [
    r"migrate from", r"port from", r"legacy", r"old version",
    r"previous implementation",
]

# Phase-1 remaining scope: only explicit Phase-1 gate language may become
# CURRENT_REQUIREMENT. Bare words like "observability" appear in unrelated
# historical brainstorming (e.g. directory trees) and must NOT qualify.
CURRENT_SCOPE_PATTERNS = {
    "agent-bridge": [
        r"taskcenter",
        r"view (sources|evidence|history)",
        r"nested task.*(copy|edit|expand)|copy.*branch.*task",
        r"phase.?1.*acceptance|acceptance.*phase.?1",
        r"\b504\b.{0,60}(recover|resilien|restart|reset)",
        r"provider failure.{0,60}(not reset|recover|resilien)",
        r"persist.{0,40}restart.{0,40}task",
        r"supervisor.{0,30}bridge.{0,30}worker.{0,30}(review|verif)",
    ],
}


def _norm(text: str) -> str:
    t = (text or "").lower()
    t = re.sub(r"\s+", " ", t).strip()
    return t[:400]


def _hash(text: str) -> str:
    return hashlib.sha256(_norm(text).encode()).hexdigest()[:16]


def _has_any(text: str, patterns: list[str]) -> bool:
    t = (text or "").lower()
    return any(re.search(p, t) for p in patterns)


def classify(entry: dict[str, Any], seen_hashes: set[str]) -> str:
    content = str(entry.get("content", ""))
    category = str(entry.get("category", ""))
    h = _hash(content)
    if h in seen_hashes:
        return "DUPLICATE"
    seen_hashes.add(h)

    if _has_any(content, REJECTED_PATTERNS):
        return "REJECTED"
    if _has_any(content, SUPERSEDED_PATTERNS):
        return "SUPERSEDED"
    if _has_any(content, REVIEW_PATTERNS):
        return "OWNER_REVIEW_REQUIRED"
    if _has_any(content, VERIFIED_WORK_PATTERNS):
        if "VERIFIED" in category or "IMPLEMENTED" in category:
            return "ALREADY_VERIFIED"
        # A candidate merely *about* verified work is not itself a new requirement.
        return "HISTORICAL"
    if "FUTURE_IDEA" in category or _has_any(content, FUTURE_PATTERNS):
        return "FUTURE_IDEA"
    if _has_any(content, MIGRATION_PATTERNS) or "MIGRATION_SOURCE" in category:
        return "MIGRATION_SOURCE"

    projects = entry.get("project_relevance") or []
    # Conservative CURRENT gate: actionable + confident + project-relevant +
    # matches the remaining Phase-1 scope.
    if entry.get("actionable") and float(entry.get("confidence", 0) or 0) >= 0.7 and projects:
        for proj in projects:
            for pat in CURRENT_SCOPE_PATTERNS.get(proj, []):
                if re.search(pat, content.lower()):
                    return "CURRENT_REQUIREMENT"
    # Broad platform brainstorming without owner confirmation -> research only.
    if not projects or "UNCLASSIFIED" in category:
        return "HISTORICAL"
    if "FEATURE_REQUIREMENT" in category or "TODO" in category or "BUG" in category:
        # Genuine-looking but outside the current gated scope: keep retrievable,
        # do not activate.
        return "RESEARCH_ONLY"
    return "HISTORICAL"


def reconcile(actionable_path: Path = ACTIONABLE_PATH,
              output_path: Path = OUTPUT_PATH,
              current_path: Path = CURRENT_PATH) -> dict[str, Any]:
    entries = json.loads(actionable_path.read_text(encoding="utf-8"))
    seen: set[str] = set()
    reconciled: list[dict[str, Any]] = []
    for e in entries:
        label = classify(e, seen)
        reconciled.append({**e, "disposition": label})
    counts = Counter(r["disposition"] for r in reconciled)

    # Deduplicate CURRENT requirements by normalized hash into backlog items.
    current: list[dict[str, Any]] = []
    seen_current: set[str] = set()
    for r in reconciled:
        if r["disposition"] != "CURRENT_REQUIREMENT":
            continue
        h = _hash(str(r.get("content", "")))
        if h in seen_current:
            continue
        seen_current.add(h)
        current.append({
            "title": (str(r.get("suggested_task", "")) or
                      str(r.get("content", ""))[:120]),
            "detail": str(r.get("content", ""))[:800],
            "projects": r.get("project_relevance", []),
            "source": f"{r.get('source_provider')}:{Path(str(r.get('source_file', ''))).name}",
            "entry_id": r.get("entry_id"),
            "category": r.get("category"),
        })

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(reconciled, indent=1), encoding="utf-8")
    per_project: dict[str, list[dict[str, Any]]] = {}
    for item in current:
        for p in item["projects"]:
            per_project.setdefault(p, []).append(item)
    current_path.write_text(json.dumps(
        {"counts": dict(counts),
         "current_total": len(current),
         "per_project": {k: v for k, v in per_project.items()},
         "current": current}, indent=1), encoding="utf-8")
    print(f"Reconciled {len(entries)} candidates -> "
          f"{len(current)} CURRENT, counts={dict(counts)}")
    return {"counts": dict(counts), "current": current,
            "per_project": per_project}


if __name__ == "__main__":
    reconcile()
