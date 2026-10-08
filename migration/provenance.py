"""Aetherius migration provenance + gate (§ Fork/Predecessor Migration Programme).

THE RULE THIS MODULE EXISTS TO ENFORCE

    Deleting the personal fork must never delete the provenance trail.

    Aetherius keeps the upstream URL / SHA / license and the destination
    implementation + test evidence PERMANENTLY. If a fork is still an active
    dependency or holds unique unported changes, it is NOT safe to delete.

Provenance is written FIRST, before any porting work begins, and is never
pruned when a fork disappears. The record is the permanent artefact; the
fork is disposable.

Gate states (§10) — a fork reaches SAFE_TO_DELETE only by passing every
gate in order. There is no shortcut and no bulk bypass.
"""

import csv
import hashlib
import json
import os
import time
from dataclasses import dataclass, field, asdict
from enum import Enum

# ---- Gate steps (§10, in mandatory order) ----

GATE_UPSTREAM_VERIFIED = "GATE_1_UPSTREAM_VERIFIED"
GATE_UNIQUE_CAPABILITY = "GATE_2_UNIQUE_CAPABILITY_IDENTIFIED"
GATE_CANONICAL_OWNER = "GATE_3_CANONICAL_OWNER_MAPPED"
GATE_STRATEGY_CHOSEN = "GATE_4_STRATEGY_CHOSEN"
GATE_IMPLEMENTED = "GATE_5_IMPLEMENTED_IN_CANONICAL"
GATE_TESTED = "GATE_6_TESTS_ADDED"
GATE_COMMITTED = "GATE_7_COMMITTED_AND_PUSHED"
GATE_REMOTE_SHA = "GATE_8_REMOTE_SHA_VERIFIED"
GATE_MANIFESTED = "GATE_9_MANIFEST_PRODUCED"
GATE_UNIQUE_COMMITS = "GATE_10_UNIQUE_COMMITS_PRESERVED"
GATE_SAFE_TO_DELETE = "SAFE_TO_DELETE"

GATE_ORDER = [
    GATE_UPSTREAM_VERIFIED,
    GATE_UNIQUE_CAPABILITY,
    GATE_CANONICAL_OWNER,
    GATE_STRATEGY_CHOSEN,
    GATE_IMPLEMENTED,
    GATE_TESTED,
    GATE_COMMITTED,
    GATE_REMOTE_SHA,
    GATE_MANIFESTED,
    GATE_UNIQUE_COMMITS,
    GATE_SAFE_TO_DELETE,
]

# Terminal dispositions (§10). Only the first four permit deletion.
# The last four are HOLD states — the fork must be retained.
DISPOSITION_MIGRATED = "MIGRATED"
DISPOSITION_REJECTED = "REJECTED"
DISPOSITION_SUPERSEDED = "SUPERSEDED"
DISPOSITION_NOT_APPLICABLE = "NOT_APPLICABLE"
DISPOSITION_KEEP_DEPENDENCY = "KEEP_AS_UPSTREAM_DEPENDENCY"
DISPOSITION_BLOCKED_LICENSE = "BLOCKED_LICENSE"
DISPOSITION_BLOCKED_TECHNICAL = "BLOCKED_TECHNICAL"
DISPOSITION_PENDING = "PENDING_AUDIT"

DELETABLE_DISPOSITIONS = {
    DISPOSITION_MIGRATED,
    DISPOSITION_REJECTED,
    DISPOSITION_SUPERSEDED,
    DISPOSITION_NOT_APPLICABLE,
}

# Migration strategies (§10 step 3)
STRATEGY_REFERENCE_ONLY = "REFERENCE_ONLY"
STRATEGY_DEPENDENCY = "DEPENDENCY"
STRATEGY_ADAPTER = "ADAPTER"
STRATEGY_PORT = "PORT"
STRATEGY_CLEAN_ROOM = "CLEAN_ROOM_REIMPLEMENTATION"
STRATEGY_FIRST_PARTY = "FIRST_PARTY_REPLACEMENT"

VALID_STRATEGIES = {
    STRATEGY_REFERENCE_ONLY, STRATEGY_DEPENDENCY, STRATEGY_ADAPTER,
    STRATEGY_PORT, STRATEGY_CLEAN_ROOM, STRATEGY_FIRST_PARTY,
}

# Audit outcomes from live GitHub inspection
AUDIT_NOT_CHECKED = "NOT_CHECKED"
AUDIT_VERIFIED = "VERIFIED"
AUDIT_NOT_A_FORK = "NOT_A_FORK"
AUDIT_MISSING = "REPO_MISSING"
AUDIT_AUTH_FAILED = "AUTH_FAILED"
AUDIT_ERROR = "ERROR"

PROVENANCE_SCHEMA_VERSION = 1


class GateError(Exception):
    """Raised when a gate is attempted out of order."""


@dataclass
class UpstreamFacts:
    """Live-verified facts about the fork and its upstream (§10 step 1).

    Every field here comes from a real `gh repo view` response. Nothing is
    inferred or assumed; an unverified field stays None.
    """
    fork_full_name: str = ""
    fork_url: str = ""
    is_fork: bool | None = None
    is_archived: bool | None = None
    fork_default_branch: str | None = None
    fork_pushed_at: str | None = None
    upstream_full_name: str | None = None
    upstream_url: str | None = None
    upstream_default_branch: str | None = None
    license_key: str | None = None
    license_name: str | None = None
    audit_status: str = AUDIT_NOT_CHECKED
    audit_error: str | None = None
    audited_at: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class UniqueCommitEvidence:
    """§10 step 9 — proof that fork-specific work was preserved."""
    has_unique_commits: bool | None = None
    unique_commit_count: int | None = None
    ahead_by: int | None = None
    behind_by: int | None = None
    preservation_mode: str | None = None      # PATCHSET | ARCHIVAL_BUNDLE | PORTED | NONE
    preservation_ref: str | None = None       # commit SHA / bundle path in canonical repo
    preserved_at: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DestinationEvidence:
    """§10 steps 5-8 — proof the capability landed in the canonical repo."""
    canonical_repo: str | None = None
    requirement_ids: list = field(default_factory=list)
    implementation_files: list = field(default_factory=list)
    test_files: list = field(default_factory=list)
    local_commit_sha: str | None = None
    remote_commit_sha: str | None = None
    remote_verified: bool = False
    comparison_notes: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ProvenanceRecord:
    """The permanent, fork-independent provenance record.

    This object survives deletion of the fork. It is written before any
    migration work starts and is append-only thereafter.
    """
    record_id: str
    source_repo: str                       # jayprophit/<name>
    source_kind: str                       # FORK | PREDECESSOR
    capability_summary: str = ""
    primary_destination: str | None = None
    use_case: str | None = None
    when_used: str | None = None
    how_used: str | None = None
    migration_mode: str | None = None
    analysis_confidence: str | None = None
    inventory_status: str | None = None

    upstream: UpstreamFacts = field(default_factory=UpstreamFacts)
    unique_commits: UniqueCommitEvidence = field(default_factory=UniqueCommitEvidence)
    destination: DestinationEvidence = field(default_factory=DestinationEvidence)

    gates_passed: list = field(default_factory=list)
    disposition: str = DISPOSITION_PENDING
    disposition_rationale: str | None = None

    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    schema_version: int = PROVENANCE_SCHEMA_VERSION

    # ---- gate machinery ----

    @property
    def highest_gate(self) -> str | None:
        """The furthest gate reached, in canonical order."""
        best = None
        for gate in GATE_ORDER:
            if gate in self.gates_passed:
                best = gate
        return best

    def gate_index(self, gate: str) -> int:
        return GATE_ORDER.index(gate)

    def can_pass(self, gate: str) -> bool:
        """A gate may only be passed when every prior gate is passed.

        Enforced strictly: gates cannot be skipped, so a fork can never be
        marked deletable without verified upstream, preserved unique work,
        and a remote-verified destination implementation.
        """
        idx = self.gate_index(gate)
        for prior in GATE_ORDER[:idx]:
            if prior not in self.gates_passed:
                return False
        return True

    def pass_gate(self, gate: str) -> None:
        if gate not in GATE_ORDER:
            raise GateError(f"unknown gate: {gate}")
        if gate in self.gates_passed:
            return
        if not self.can_pass(gate):
            missing = [g for g in GATE_ORDER[:self.gate_index(gate)]
                       if g not in self.gates_passed]
            raise GateError(
                f"cannot pass {gate}: prerequisite gates not passed: {missing}")
        self.gates_passed.append(gate)
        self.updated_at = time.time()

    # ---- deletion authority ----

    def is_safe_to_delete(self) -> bool:
        """THE critical rule (§10 step 10 + Critical rule).

        Deletion is permitted only when ALL of these hold:
          - every gate passed, including SAFE_TO_DELETE
          - the disposition is one of the four deletable states
          - unique fork commits were preserved (or proven absent)
          - the destination commit was verified on the REMOTE
        A local commit is not enough: local != remote preservation.
        """
        if self.disposition not in DELETABLE_DISPOSITIONS:
            return False
        if GATE_SAFE_TO_DELETE not in self.gates_passed:
            return False
        uc = self.unique_commits
        if uc.has_unique_commits is None:
            return False                      # unknown — never delete on unknown
        if uc.has_unique_commits and not uc.preservation_ref:
            return False                      # unique work not preserved
        dest = self.destination
        if self.disposition == DISPOSITION_MIGRATED and not dest.remote_verified:
            return False                      # local commit != remote preservation
        return True

    def blockers(self) -> list:
        """Human-readable reasons deletion is refused right now."""
        out = []
        for gate in GATE_ORDER:
            if gate not in self.gates_passed:
                out.append(f"gate not passed: {gate}")
        if self.disposition not in DELETABLE_DISPOSITIONS:
            out.append(f"disposition '{self.disposition}' is a HOLD state — "
                       f"fork must be retained")
        uc = self.unique_commits
        if uc.has_unique_commits is None:
            out.append("unique-commit status unknown — cannot assess data loss")
        elif uc.has_unique_commits and not uc.preservation_ref:
            out.append("fork has unique commits with no preservation reference")
        if self.disposition == DISPOSITION_MIGRATED and \
                not self.destination.remote_verified:
            out.append("destination commit not verified on remote")
        return out

    def set_disposition(self, disposition: str, rationale: str) -> None:
        if disposition not in DELETABLE_DISPOSITIONS | {
                DISPOSITION_KEEP_DEPENDENCY, DISPOSITION_BLOCKED_LICENSE,
                DISPOSITION_BLOCKED_TECHNICAL, DISPOSITION_PENDING}:
            raise GateError(f"invalid disposition: {disposition}")
        self.disposition = disposition
        self.disposition_rationale = rationale
        self.updated_at = time.time()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["safe_to_delete"] = self.is_safe_to_delete()
        d["highest_gate"] = self.highest_gate
        d["blockers"] = self.blockers()
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ProvenanceRecord":
        data = dict(data)
        data.pop("safe_to_delete", None)
        data.pop("highest_gate", None)
        data.pop("blockers", None)
        up = data.pop("upstream", {}) or {}
        uc = data.pop("unique_commits", {}) or {}
        dest = data.pop("destination", {}) or {}
        rec = cls(**{k: v for k, v in data.items()
                     if k in cls.__dataclass_fields__})
        rec.upstream = UpstreamFacts(**up)
        rec.unique_commits = UniqueCommitEvidence(**uc)
        rec.destination = DestinationEvidence(**dest)
        return rec


class ProvenanceRegistry:
    """Append-only store of permanent provenance records.

    Records outlive their forks: nothing here is ever keyed on, or pruned
    with, repository existence. Deleting a fork cannot delete its record.
    """

    def __init__(self, path: str):
        self.path = path
        self._records: dict = {}
        self._load()

    def _load(self) -> None:
        if not os.path.isfile(self.path):
            return
        with open(self.path, "r", encoding="utf-8") as fh:
            try:
                data = json.load(fh)
            except json.JSONDecodeError:
                return
        for rec in data.get("records", []):
            r = ProvenanceRecord.from_dict(rec)
            self._records[r.record_id] = r

    def save(self) -> str:
        payload = {
            "schema_version": PROVENANCE_SCHEMA_VERSION,
            "generated_at": time.time(),
            "record_count": len(self._records),
            "records": [r.to_dict() for r in self._records.values()],
        }
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        return hashlib.sha256(
            open(self.path, "rb").read()).hexdigest()

    def add(self, record: ProvenanceRecord) -> None:
        if record.record_id in self._records:
            raise GateError(f"duplicate record_id: {record.record_id}")
        self._records[record.record_id] = record

    def get(self, record_id: str) -> ProvenanceRecord | None:
        return self._records.get(record_id)

    def by_source(self, source_repo: str) -> ProvenanceRecord | None:
        for r in self._records.values():
            if r.source_repo == source_repo:
                return r
        return None

    def all(self) -> list:
        return list(self._records.values())

    def safe_to_delete_queue(self) -> list:
        """Only records that genuinely pass the full gate."""
        return [r for r in self._records.values() if r.is_safe_to_delete()]

    def retained_queue(self) -> list:
        """Everything that must be KEPT, with reasons — the default state."""
        return [r for r in self._records.values() if not r.is_safe_to_delete()]

    def summary(self) -> dict:
        by_disp = {}
        for r in self._records.values():
            by_disp[r.disposition] = by_disp.get(r.disposition, 0) + 1
        by_gate = {}
        for r in self._records.values():
            g = r.highest_gate or "NONE"
            by_gate[g] = by_gate.get(g, 0) + 1
        return {
            "total_records": len(self._records),
            "by_disposition": by_disp,
            "by_highest_gate": by_gate,
            "safe_to_delete": len(self.safe_to_delete_queue()),
            "retained": len(self.retained_queue()),
        }


# ---- Catalog ingestion (the 350-row use-case CSV) ----

CATALOG_COLUMNS = [
    "repository", "category", "primary_destination", "primary_use_case",
    "when_used", "how_used", "migration_mode", "analysis_confidence",
    "inventory_status", "post_migration_disposition",
]


def load_catalog(csv_path: str) -> list:
    """Read the 350-repository use-case catalog.

    Returns a list of plain dicts. Raises on a malformed header so a
    silently-wrong catalog can never drive deletion decisions.
    """
    if not os.path.isfile(csv_path):
        raise FileNotFoundError(csv_path)
    rows = []
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in CATALOG_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"catalog missing required columns: {missing}")
        for row in reader:
            if not (row.get("repository") or "").strip():
                continue
            rows.append({k: (v or "").strip() for k, v in row.items() if k})
    return rows


def records_from_catalog(csv_path: str, source_kind: str = "FORK") -> list:
    """Build UNVERIFIED provenance records from the catalog.

    Every record starts at GATE 0 with disposition PENDING_AUDIT. A catalog
    classification is a hypothesis, not a verification — so nothing derived
    from it can reach SAFE_TO_DELETE until live audit + the full gate run.
    """
    out = []
    for row in load_catalog(csv_path):
        repo = row["repository"]
        record_id = "PROV-" + hashlib.sha256(
            repo.encode("utf-8")).hexdigest()[:16].upper()
        rec = ProvenanceRecord(
            record_id=record_id,
            source_repo=repo,
            source_kind=source_kind,
            capability_summary=row.get("primary_use_case", ""),
            primary_destination=row.get("primary_destination") or None,
            use_case=row.get("primary_use_case") or None,
            when_used=row.get("when_used") or None,
            how_used=row.get("how_used") or None,
            migration_mode=row.get("migration_mode") or None,
            analysis_confidence=row.get("analysis_confidence") or None,
            inventory_status=row.get("inventory_status") or None,
        )
        rec.upstream.fork_full_name = repo
        rec.upstream.fork_url = f"https://github.com/{repo}"
        out.append(rec)
    return out


def catalog_coverage(csv_path: str) -> dict:
    """Distribution of the catalog by category and confidence."""
    rows = load_catalog(csv_path)
    by_cat, by_conf, by_mode = {}, {}, {}
    for r in rows:
        by_cat[r["category"]] = by_cat.get(r["category"], 0) + 1
        by_conf[r["analysis_confidence"]] = \
            by_conf.get(r["analysis_confidence"], 0) + 1
        by_mode[r["migration_mode"]] = by_mode.get(r["migration_mode"], 0) + 1
    return {
        "total_rows": len(rows),
        "by_category": dict(sorted(by_cat.items(), key=lambda kv: -kv[1])),
        "by_confidence": by_conf,
        "by_migration_mode": by_mode,
    }
