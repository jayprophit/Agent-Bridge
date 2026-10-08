"""Provenance schema for the Knowledge & Provenance Fabric (§10, §97, §115).

Every derived item retains source links. The system must always be able to
answer: "Where did this information come from?"

Do NOT create a second provenance registry — this feeds into the existing
EvidenceLedger in task_dag.py.
"""
from __future__ import annotations

import time
import uuid
import hashlib
from dataclasses import dataclass, field
from typing import Any


# Confidence states (§38)
CONF_SOURCE_QUOTE = "SOURCE_QUOTE"
CONF_OWNER_DECISION = "OWNER_DECISION"
CONF_IMPLEMENTATION_EVIDENCE = "IMPLEMENTATION_EVIDENCE"
CONF_TEST_EVIDENCE = "TEST_EVIDENCE"
CONF_EXTERNAL_CLAIM = "EXTERNAL_CLAIM"
CONF_MODEL_INFERENCE = "MODEL_INFERENCE"
CONF_UNVERIFIED_RESEARCH = "UNVERIFIED_RESEARCH"
CONF_HYPOTHESIS = "HYPOTHESIS"

CONFIDENCE_STATES = (
    CONF_SOURCE_QUOTE,
    CONF_OWNER_DECISION,
    CONF_IMPLEMENTATION_EVIDENCE,
    CONF_TEST_EVIDENCE,
    CONF_EXTERNAL_CLAIM,
    CONF_MODEL_INFERENCE,
    CONF_UNVERIFIED_RESEARCH,
    CONF_HYPOTHESIS,
)

# Provenance lifecycle (§13)
LIFE_CURRENT = "CURRENT"
LIFE_SUPERSEDED = "SUPERSEDED"
LIFE_CONTRADICTED = "CONTRADICTED"
LIFE_HISTORICAL = "HISTORICAL"
LIFE_UNVERIFIED = "UNVERIFIED"
LIFE_RESEARCH_ONLY = "RESEARCH_ONLY"
LIFE_REJECTED = "REJECTED"
LIFE_FAILED = "FAILED"
LIFE_PARTIAL = "PARTIAL"
LIFE_VERIFIED = "VERIFIED"

LIFECYCLE_STATES = (
    LIFE_CURRENT, LIFE_SUPERSEDED, LIFE_CONTRADICTED, LIFE_HISTORICAL,
    LIFE_UNVERIFIED, LIFE_RESEARCH_ONLY, LIFE_REJECTED,
    LIFE_FAILED, LIFE_PARTIAL, LIFE_VERIFIED,
)

# Derived knowledge types (§12)
KIND_REQUIREMENT = "REQUIREMENT"
KIND_DECISION = "DECISION"
KIND_TASK = "TASK"
KIND_IDEA = "IDEA"
KIND_ARCHITECTURE = "ARCHITECTURE"
KIND_RESEARCH = "RESEARCH"
KIND_CONTRADICTION = "CONTRADICTION"
KIND_TEST_RESULT = "TEST_RESULT"
KIND_CODE = "CODE"
KIND_CONFIG = "CONFIG"
KIND_EVIDENCE = "EVIDENCE"
KIND_REFERENCE = "REFERENCE"
KIND_FAILURE = "FAILURE"
KIND_UNFINISHED = "UNFINISHED"
KIND_IMPLEMENTATION = "IMPLEMENTATION"

DERIVED_KINDS = (
    KIND_REQUIREMENT, KIND_DECISION, KIND_TASK, KIND_IDEA,
    KIND_ARCHITECTURE, KIND_RESEARCH, KIND_CONTRADICTION,
    KIND_TEST_RESULT, KIND_CODE, KIND_CONFIG, KIND_EVIDENCE,
    KIND_REFERENCE, KIND_FAILURE, KIND_UNFINISHED,
    KIND_IMPLEMENTATION,
)


@dataclass
class SourceReference:
    """A minimal reference to a source item (§10, §97)."""
    source_id: str = ""
    source_type: str = ""      # conversation | repository | file | image | ...
    platform: str = ""         # chatgpt, claude, github, local
    remote_id: str = ""
    remote_url: str = ""
    title: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0
    content_hash: str = ""
    snippet: str = ""          # excerpt for attribution (max 500 chars)
    location: dict[str, Any] = field(default_factory=dict)  # e.g. {"offset": 42, "line": 12}


@dataclass
class ProvenanceRecord:
    """Provenance metadata for a derived knowledge item (§10, §97, §115).

    Tracks the full derivation chain: source → extractor → model → result.
    """
    provenance_id: str = ""
    source: SourceReference = field(default_factory=SourceReference)
    derived_kind: str = KIND_RESEARCH
    confidence: str = CONF_UNVERIFIED_RESEARCH
    lifecycle: str = LIFE_CURRENT
    extracted_at: float = 0.0
    extractor: str = ""        # adapter/tool that extracted this
    extraction_model: str = "" # LLM used for extraction (if any)
    content_hash: str = ""     # hash of the extracted content
    relationships: list[dict[str, Any]] = field(default_factory=list)
    # relationships: [{"kind": "SUPERSEDES", "target": "prov-id-002", "reason": "..."}]
    superseded_by: list[str] = field(default_factory=list)
    superseded_at: float = 0.0
    version: int = 1
    evidence_refs: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.provenance_id:
            self.provenance_id = f"prov-{uuid.uuid4().hex[:16]}"
        if not self.extracted_at:
            self.extracted_at = time.time()
        if not self.content_hash:
            self.content_hash = hashlib.sha256(
                f"{self.source.source_id}:{self.derived_kind}".encode()
            ).hexdigest()[:16]

    def supersede(self, new_id: str, reason: str) -> None:
        """Mark this record as superseded by a newer one."""
        self.lifecycle = LIFE_SUPERSEDED
        self.superseded_by.append(new_id)
        self.superseded_at = time.time()
        self.relationships.append({
            "kind": "SUPERSEDED_BY",
            "target": new_id,
            "reason": reason,
            "at": self.superseded_at,
        })

    def contradict(self, other_id: str, reason: str) -> None:
        """Mark this record as contradicted."""
        self.lifecycle = LIFE_CONTRADICTED
        self.relationships.append({
            "kind": "CONTRADICTED_BY",
            "target": other_id,
            "reason": reason,
            "at": time.time(),
        })

    def to_dict(self) -> dict[str, Any]:
        from dataclasses import asdict
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ProvenanceRecord":
        source_data = d.get("source", {})
        source = SourceReference(**{
            k: v for k, v in source_data.items()
            if k in SourceReference.__dataclass_fields__
        }) if isinstance(source_data, dict) else source_data
        return cls(
            provenance_id=d.get("provenance_id", ""),
            source=source,
            derived_kind=d.get("derived_kind", KIND_RESEARCH),
            confidence=d.get("confidence", CONF_UNVERIFIED_RESEARCH),
            lifecycle=d.get("lifecycle", LIFE_CURRENT),
            extracted_at=d.get("extracted_at", 0.0),
            extractor=d.get("extractor", ""),
            extraction_model=d.get("extraction_model", ""),
            content_hash=d.get("content_hash", ""),
            relationships=d.get("relationships", []),
            superseded_by=d.get("superseded_by", []),
            superseded_at=d.get("superseded_at", 0.0),
            version=d.get("version", 1),
            evidence_refs=d.get("evidence_refs", []),
            metadata=d.get("metadata", {}),
        )


@dataclass
class DerivedKnowledge:
    """A derived piece of knowledge from a source (§12).

    DERIVED KNOWLEDGE != ORIGINAL SOURCE.
    The original source is always preserved via SourceReference.
    """
    knowledge_id: str = ""
    provenance: ProvenanceRecord = field(default_factory=ProvenanceRecord)
    title: str = ""
    content: str = ""
    projects: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    confidence: str = CONF_UNVERIFIED_RESEARCH
    lifecycle: str = LIFE_CURRENT
    derived_at: float = 0.0
    relationships: list[str] = field(default_factory=list)  # related knowledge_ids

    def __post_init__(self) -> None:
        if not self.knowledge_id:
            self.knowledge_id = f"kn-{uuid.uuid4().hex[:12]}"
        if not self.derived_at:
            self.derived_at = time.time()

    def to_dict(self) -> dict[str, Any]:
        from dataclasses import asdict
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DerivedKnowledge":
        prov_data = d.get("provenance", {})
        if isinstance(prov_data, dict):
            prov = ProvenanceRecord.from_dict(prov_data)
        else:
            prov = prov_data
        return cls(
            knowledge_id=d.get("knowledge_id", ""),
            provenance=prov,
            title=d.get("title", ""),
            content=d.get("content", ""),
            projects=d.get("projects", []),
            tags=d.get("tags", []),
            confidence=d.get("confidence", CONF_UNVERIFIED_RESEARCH),
            lifecycle=d.get("lifecycle", LIFE_CURRENT),
            derived_at=d.get("derived_at", 0.0),
            relationships=d.get("relationships", []),
        )


__all__ = [
    # confidence
    "CONF_SOURCE_QUOTE", "CONF_OWNER_DECISION", "CONF_IMPLEMENTATION_EVIDENCE",
    "CONF_TEST_EVIDENCE", "CONF_EXTERNAL_CLAIM", "CONF_MODEL_INFERENCE",
    "CONF_UNVERIFIED_RESEARCH", "CONF_HYPOTHESIS", "CONFIDENCE_STATES",
    # lifecycle
    "LIFE_CURRENT", "LIFE_SUPERSEDED", "LIFE_CONTRADICTED", "LIFE_HISTORICAL",
    "LIFE_UNVERIFIED", "LIFE_RESEARCH_ONLY", "LIFE_REJECTED", "LIFE_FAILED",
    "LIFE_PARTIAL", "LIFE_VERIFIED", "LIFECYCLE_STATES",
    # derived kinds
    "KIND_REQUIREMENT", "KIND_DECISION", "KIND_TASK", "KIND_IDEA",
    "KIND_ARCHITECTURE", "KIND_RESEARCH", "KIND_CONTRADICTION",
    "KIND_TEST_RESULT", "KIND_CODE", "KIND_CONFIG", "KIND_EVIDENCE",
    "KIND_REFERENCE", "KIND_FAILURE", "KIND_UNFINISHED",
    "KIND_IMPLEMENTATION", "DERIVED_KINDS",
    # dataclasses
    "SourceReference", "ProvenanceRecord", "DerivedKnowledge",
]
