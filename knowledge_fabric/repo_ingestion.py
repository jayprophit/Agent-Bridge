"""Full-account repository ingestion (§6, §7, §10, §11).

THE GAP THIS CLOSES

The Knowledge Fabric P0 proof indexed 17 repositories. That proved the
ADAPTER works. It did not prove ACCOUNT-WIDE ingestion — the owner's estate
is 396 repositories. A proof-of-concept on 1/23rd of the estate is not
coverage.

WHAT THIS DOES

Enumerates every repository, produces the §10 normalized record, and — per
§11 — only re-analyses repositories whose state CHANGED. The change
detector keys on HEAD SHA, updated_at and a metadata hash, so an unchanged
estate costs one enumeration and zero deep inspections.

PRIVACY (§5)

Records carry operational metadata only. No API keys, no token material, no
vault contents, no prompt bodies. Fork/parent relationships are structural
facts and are recorded.

DOES NOT DELETE (§25)

Ingestion is read-only and migratory. Nothing here removes a repository,
and reaching SAFE_TO_DELETE requires the separate migration gate.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# §7 lifecycle classification.
ACTIVE_CANONICAL = "ACTIVE_CANONICAL"
ACTIVE_SUPPORTING = "ACTIVE_SUPPORTING"
PREDECESSOR = "PREDECESSOR"
FORK = "FORK"
REFERENCE = "REFERENCE"
LEARNING = "LEARNING"
EXPERIMENT = "EXPERIMENT"
SUPERSEDED = "SUPERSEDED"
ARCHIVED = "ARCHIVED"
UNKNOWN = "UNKNOWN"

STATUS_VALUES = (
    ACTIVE_CANONICAL, ACTIVE_SUPPORTING, PREDECESSOR, FORK, REFERENCE,
    LEARNING, EXPERIMENT, SUPERSEDED, ARCHIVED, UNKNOWN,
)

# §14 graph relationship types.
FORK_OF = "FORK_OF"
PREDECESSOR_OF = "PREDECESSOR_OF"
MIGRATED_FROM = "MIGRATED_FROM"
IMPLEMENTED_IN = "IMPLEMENTED_IN"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_repo_id(owner: str, name: str) -> str:
    """§6/§10 — a STABLE repository ID that survives renames of order.

    Derived from owner+name so the same repository always yields the same id
    across runs. Content is never part of the id, or a single commit would
    forge a new identity.
    """
    digest = hashlib.sha256(f"{owner.lower()}/{name.lower()}".encode()).hexdigest()
    return f"repo-{digest[:16]}"


def metadata_hash(record: dict[str, Any]) -> str:
    """§11 — hash of the fields that matter for change detection.

    Excludes volatile fields (last_indexed) so re-indexing an unchanged
    repository does not register as a change.
    """
    stable = {k: v for k, v in record.items()
              if k not in ("last_indexed", "metadata_hash")}
    blob = json.dumps(stable, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


@dataclass
class RepositoryKnowledgeRecord:
    """§10 normalized repository record."""

    repo_id: str
    name: str
    owner: str
    url: str
    visibility: str = "public"
    is_fork: bool = False
    upstream: str | None = None
    license: str | None = None
    default_branch: str | None = None
    head_sha: str | None = None
    updated_at: str | None = None
    languages: list[str] = field(default_factory=list)
    status: str = UNKNOWN
    projects: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    predecessor_of: str | None = None
    successor: str | None = None
    migration_state: str = "NOT_STARTED"
    archived: bool = False
    stars: int = 0
    size_kb: int | None = None
    unique_commits: int | None = None
    last_indexed: str = field(default_factory=utc_now)
    metadata_hash: str = ""
    provenance: dict[str, Any] = field(default_factory=dict)

    def finalize(self) -> "RepositoryKnowledgeRecord":
        if not self.metadata_hash:
            self.metadata_hash = metadata_hash(asdict(self))
        return self

    def as_dict(self) -> dict:
        return asdict(self)


def classify_status(live: dict[str, Any], *, is_predecessor: bool = False,
                    is_canonical: bool = False) -> str:
    """§7 lifecycle classification from live facts only."""
    if live.get("archived"):
        return ARCHIVED
    if is_canonical:
        return ACTIVE_CANONICAL
    if is_predecessor:
        return PREDECESSOR
    if live.get("fork"):
        return FORK
    return UNKNOWN


class ChangeDetector:
    """§11 — skip unchanged repositories, inspect only what moved."""

    def __init__(self, known: dict[str, RepositoryKnowledgeRecord] | None = None):
        self.known = known or {}

    def load_state(self, path: Path) -> int:
        if not path.is_file():
            return 0
        raw = json.loads(path.read_text(encoding="utf-8"))
        loaded = 0
        for item in raw if isinstance(raw, list) else raw.get("repositories", []):
            rec = RepositoryKnowledgeRecord(**item)
            self.known[rec.repo_id] = rec
            loaded += 1
        return loaded

    def save_state(self, path: Path, records: list[RepositoryKnowledgeRecord]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"indexed_at": utc_now(),
                        "count": len(records),
                        "repositories": [r.as_dict() for r in records]},
                       indent=2),
            encoding="utf-8")

    def evaluate(self, incoming: RepositoryKnowledgeRecord) -> tuple[str, str]:
        """Return (action, reason): NEW / CHANGED / UNCHANGED."""
        prior = self.known.get(incoming.repo_id)
        if prior is None:
            return "NEW", "no prior record"
        if prior.head_sha and incoming.head_sha and prior.head_sha != incoming.head_sha:
            return "CHANGED", f"head {prior.head_sha[:8]} -> {incoming.head_sha[:8]}"
        if prior.metadata_hash and prior.metadata_hash != incoming.metadata_hash:
            return "CHANGED", "metadata hash differs"
        return "UNCHANGED", "head SHA and metadata hash identical"
