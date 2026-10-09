"""Evidence path resolution — keeps raw and resolved estate data separate (§17).

THE HAZARD THIS MODULE EXISTS TO REMOVE

Both scripts used to write the SAME file:

    fetch_live_estate.py   ->  migration/evidence/live_estate.json   (raw)
    resolve_upstreams.py   ->  migration/evidence/live_estate.json   (resolved)

The REST list endpoint omits the `parent` field, so raw data makes every fork
look like an unlinkable original. Running the fetch alone therefore OVERWROTE
resolved evidence with unresolved data, and seven downstream consumers
silently read the degraded version.

That was caught once, and the fix at the time was a clearer warning message.
A warning is not a fix: the next person to re-run the fetch for a quick count
would silently corrupt the evidence again.

STRUCTURAL RULE ENFORCED HERE

    raw enumeration may ONLY ever write the raw path
    resolution may ONLY ever write the resolved path

The two datasets can no longer clobber each other because they no longer
share a filename. ``assert_not_degraded`` makes the invariant testable: after
any raw fetch, the resolved dataset must still show fully-resolved forks.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = REPO_ROOT / "migration" / "evidence"

# §17 — two distinct files, never one.
RAW_ESTATE = EVIDENCE / "live_estate_raw.json"
RESOLVED_ESTATE = EVIDENCE / "live_estate_resolved.json"

# The historical single-file path. Still READ for backwards compatibility so
# existing evidence is not orphaned, but never written to again.
LEGACY_ESTATE = EVIDENCE / "live_estate.json"


def read_raw() -> list[dict]:
    """Raw enumeration output. Forks here have NO `parent` — by design."""
    if RAW_ESTATE.exists():
        return json.loads(RAW_ESTATE.read_text(encoding="utf-8"))
    return []


def write_raw(repos: list[dict]) -> Path:
    """Write raw enumeration. CANNOT touch the resolved dataset."""
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    RAW_ESTATE.write_text(json.dumps(repos, indent=2, ensure_ascii=False),
                          encoding="utf-8")
    return RAW_ESTATE


def read_resolved() -> list[dict]:
    """Resolved estate: every fork carries its upstream `parent`."""
    if RESOLVED_ESTATE.exists():
        return json.loads(RESOLVED_ESTATE.read_text(encoding="utf-8"))
    # Backwards compatibility: if resolution has not run since the split, the
    # legacy file holds the last resolved state.
    if LEGACY_ESTATE.exists():
        return json.loads(LEGACY_ESTATE.read_text(encoding="utf-8"))
    return []


def write_resolved(repos: list[dict]) -> Path:
    """Write resolved estate. This is the canonical dataset."""
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    RESOLVED_ESTATE.write_text(json.dumps(repos, indent=2, ensure_ascii=False),
                               encoding="utf-8")
    return RESOLVED_ESTATE


def resolved_stats(repos: list[dict] | None = None) -> dict:
    """Summary used by tests and evidence to prove the invariant holds."""
    repos = repos if repos is not None else read_resolved()
    forks = [r for r in repos if r.get("fork")]
    unresolved = [r.get("name", "?") for r in forks if not r.get("parent")]
    return {
        "total": len(repos),
        "forks": len(forks),
        "originals": len(repos) - len(forks),
        "unresolved_forks": unresolved,
        # Degradation means forks EXIST but lack an upstream. An empty estate
        # has nothing unresolved, so it is not degraded — reporting False for
        # it would misread "nothing yet" as "data is broken".
        "fully_resolved": not unresolved,
    }


def assert_not_degraded() -> dict:
    """§17 test hook: the resolved dataset must never look like raw data.

    Returns the stats. Raises when the resolved dataset has forks but none of
    them carry an upstream — the exact signature of raw data overwriting it.
    """
    stats = resolved_stats()
    if stats["forks"] and stats["unresolved_forks"]:
        raise AssertionError(
            "resolved estate is degraded: "
            f"{len(stats['unresolved_forks'])} forks have no upstream "
            f"(first: {stats['unresolved_forks'][:5]}).\n"
            "This is the signature of raw enumeration overwriting resolved "
            "evidence.\n"
            "Re-run the pipeline: scripts/fetch_live_estate.py && "
            "scripts/resolve_upstreams.py")
    return stats
