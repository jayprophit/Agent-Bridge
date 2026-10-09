"""Migration programme package (§10 Fork/Predecessor Migration Programme)."""

from .provenance import (
    DELETABLE_DISPOSITIONS, DISPOSITION_PENDING, GATE_ORDER,
    GATE_SAFE_TO_DELETE, ProvenanceRecord, ProvenanceRegistry,
    GateError, catalog_coverage, load_catalog, records_from_catalog,
)
from migration.auditor import (
    AuditorUnavailable, apply_audit, audit_batch, detect_unique_commits,
    gh_available, probe_repo, upstream_default_branch,
)
from migration.manifest import build_manifest
from .unique_audit import (
    PRESERVATION_REQUIRED, SAFE_DELETE_CONDITIONS, SafeDeleteVerdict,
    UniqueContentClass, classify_unique_content, fork_vs_upstream,
)

UNIQUE_CONTENT_CLASSES = tuple(c.value for c in UniqueContentClass)

__all__ = [
    "DELETABLE_DISPOSITIONS", "DISPOSITION_PENDING", "GATE_ORDER",
    "GATE_SAFE_TO_DELETE", "GateError", "ProvenanceRecord",
    "ProvenanceRegistry", "catalog_coverage", "load_catalog",
    "records_from_catalog", "AuditorUnavailable", "apply_audit",
    "audit_batch", "detect_unique_commits", "gh_available", "probe_repo",
    "upstream_default_branch", "build_manifest",
    "SAFE_DELETE_CONDITIONS", "PRESERVATION_REQUIRED", "SafeDeleteVerdict",
    "UNIQUE_CONTENT_CLASSES", "UniqueContentClass",
    "classify_unique_content", "fork_vs_upstream",
]
