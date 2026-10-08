"""Aetherius Knowledge & Provenance Fabric (§1-66 of Knowledge Fabric addendum).

INGEST
  conversations, repositories, browser, apps, files, media, devices

NORMALISE
  canonical records, timestamps, IDs, hashes, source links

UNDERSTAND
  projects, concepts, decisions, requirements, tasks, relationships

REGISTER
  provenance, lifecycle, confidence, supersession

INDEX
  exact, semantic, graph, temporal

RETRIEVE
  capability-aware, privacy-aware, project-aware

PACKAGE
  worker context packages

LEARN
  completed tasks, evidence, test results, new knowledge

This subsystem feeds the canonical memory/project/evidence systems.
It does NOT create a second Genesis memory (§2).
"""

from knowledge_fabric.source_adapter import (
    KnowledgeSourceAdapter, SourceMetadata,
    compute_content_hash, stable_source_id,
    SOURCE_TYPE_CONVERSATION, SOURCE_TYPE_REPOSITORY,
    SOURCE_TYPE_FILE, SOURCE_TYPE_IMAGE,
    SOURCE_TYPE_AUDIO, SOURCE_TYPE_VIDEO,
    SOURCE_TYPE_DOCUMENT, SOURCE_TYPES,
    CAP_LIST_CONVERSATIONS, CAP_GET_METADATA, CAP_READ_MESSAGES,
    CAP_SEARCH, CAP_READ_ATTACHMENTS, CAP_READ_CODE_BLOCKS,
    CAP_READ_IMAGES, CAP_READ_LINKS, CAP_ALL,
    STATE_SPECIFIED, STATE_ADAPTER_AVAILABLE, STATE_AUTH_REQUIRED,
    STATE_PARTIAL, STATE_INDEXING, STATE_INDEXED, STATE_VERIFIED,
    STATE_DEGRADED, STATE_BLOCKED, STATE_STALE, STATE_SUPERSEDED,
    STATE_FAILED, STATES,
)
from knowledge_fabric.source_provenance import (
    SourceReference, ProvenanceRecord, DerivedKnowledge,
    CONF_SOURCE_QUOTE, CONF_OWNER_DECISION,
    CONF_IMPLEMENTATION_EVIDENCE, CONF_TEST_EVIDENCE,
    CONF_EXTERNAL_CLAIM, CONF_MODEL_INFERENCE,
    CONF_UNVERIFIED_RESEARCH, CONF_HYPOTHESIS, CONFIDENCE_STATES,
    LIFE_CURRENT, LIFE_SUPERSEDED, LIFE_CONTRADICTED, LIFE_HISTORICAL,
    LIFE_UNVERIFIED, LIFE_RESEARCH_ONLY, LIFE_REJECTED,
    LIFE_FAILED, LIFE_PARTIAL, LIFE_VERIFIED, LIFECYCLE_STATES,
    KIND_REQUIREMENT, KIND_DECISION, KIND_TASK, KIND_IDEA,
    KIND_ARCHITECTURE, KIND_RESEARCH, KIND_CONTRADICTION,
    KIND_TEST_RESULT, KIND_CODE, KIND_CONFIG, KIND_EVIDENCE,
    KIND_REFERENCE, KIND_FAILURE, KIND_UNFINISHED,
    KIND_IMPLEMENTATION, DERIVED_KINDS,
)
from knowledge_fabric.context_broker import (
    ContextBroker, ContextRequest, ContextPackage,
    ROLE_PRIVACY_CEILINGS,
)
from knowledge_fabric.github_adapter import (
    GitHubAdapter, FileIngestionAdapter, ImageIngestionAdapter,
    GitHubRepoInfo,
)

__all__ = [
    # source_adapter
    "KnowledgeSourceAdapter", "SourceMetadata",
    "compute_content_hash", "stable_source_id",
    "SOURCE_TYPE_CONVERSATION", "SOURCE_TYPE_REPOSITORY",
    "SOURCE_TYPE_FILE", "SOURCE_TYPE_IMAGE",
    "SOURCE_TYPE_AUDIO", "SOURCE_TYPE_VIDEO",
    "SOURCE_TYPE_DOCUMENT", "SOURCE_TYPES",
    "CAP_LIST_CONVERSATIONS", "CAP_GET_METADATA", "CAP_READ_MESSAGES",
    "CAP_SEARCH", "CAP_READ_ATTACHMENTS", "CAP_READ_CODE_BLOCKS",
    "CAP_READ_IMAGES", "CAP_READ_LINKS", "CAP_ALL",
    "STATE_SPECIFIED", "STATE_ADAPTER_AVAILABLE", "STATE_AUTH_REQUIRED",
    "STATE_PARTIAL", "STATE_INDEXING", "STATE_INDEXED", "STATE_VERIFIED",
    "STATE_DEGRADED", "STATE_BLOCKED", "STATE_STALE", "STATE_SUPERSEDED",
    "STATE_FAILED", "STATES",
    # source_provenance
    "SourceReference", "ProvenanceRecord", "DerivedKnowledge",
    "CONF_SOURCE_QUOTE", "CONF_OWNER_DECISION",
    "CONF_IMPLEMENTATION_EVIDENCE", "CONF_TEST_EVIDENCE",
    "CONF_EXTERNAL_CLAIM", "CONF_MODEL_INFERENCE",
    "CONF_UNVERIFIED_RESEARCH", "CONF_HYPOTHESIS", "CONFIDENCE_STATES",
    "LIFE_CURRENT", "LIFE_SUPERSEDED", "LIFE_CONTRADICTED", "LIFE_HISTORICAL",
    "LIFE_UNVERIFIED", "LIFE_RESEARCH_ONLY", "LIFE_REJECTED",
    "LIFE_FAILED", "LIFE_PARTIAL", "LIFE_VERIFIED", "LIFECYCLE_STATES",
    "KIND_REQUIREMENT", "KIND_DECISION", "KIND_TASK", "KIND_IDEA",
    "KIND_ARCHITECTURE", "KIND_RESEARCH", "KIND_CONTRADICTION",
    "KIND_TEST_RESULT", "KIND_CODE", "KIND_CONFIG", "KIND_EVIDENCE",
    "KIND_REFERENCE", "KIND_FAILURE", "KIND_UNFINISHED",
    "KIND_IMPLEMENTATION", "DERIVED_KINDS",
    # context_broker
    "ContextBroker", "ContextRequest", "ContextPackage",
    "ROLE_PRIVACY_CEILINGS",
    # github_adapter
    "GitHubAdapter", "FileIngestionAdapter", "ImageIngestionAdapter",
    "GitHubRepoInfo",
]
