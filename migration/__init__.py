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

__all__ = [
    "DELETABLE_DISPOSITIONS", "DISPOSITION_PENDING", "GATE_ORDER",
    "GATE_SAFE_TO_DELETE", "GateError", "ProvenanceRecord",
    "ProvenanceRegistry", "catalog_coverage", "load_catalog",
    "records_from_catalog", "AuditorUnavailable", "apply_audit",
    "audit_batch", "detect_unique_commits", "gh_available", "probe_repo",
]
