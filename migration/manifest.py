"""Migration manifest (§10 step 8).

Produces the machine-readable manifest showing every audited source's
capability as MIGRATED / REJECTED / SUPERSEDED / NOT_APPLICABLE, or an
explicit HOLD state, together with the deletion decision and its reasons.

The manifest is the audit artefact: it must be readable by a human who was
not present for the migration and must justify every verdict.
"""

import json
import os
import time

from .provenance import ProvenanceRegistry


def build_manifest(registry: ProvenanceRegistry) -> dict:
    safe = registry.safe_to_delete_queue()
    retained = registry.retained_queue()

    def row(rec):
        return {
            "source_repo": rec.source_repo,
            "source_kind": rec.source_kind,
            "capability": rec.capability_summary,
            "upstream": rec.upstream.upstream_full_name,
            "upstream_url": rec.upstream.upstream_url,
            "upstream_default_branch": rec.upstream.upstream_default_branch,
            "fork_default_branch": rec.upstream.fork_default_branch,
            "license": rec.upstream.license_key,
            "audit_status": rec.upstream.audit_status,
            "has_unique_commits": rec.unique_commits.has_unique_commits,
            "unique_commit_count": rec.unique_commits.unique_commit_count,
            "preservation_mode": rec.unique_commits.preservation_mode,
            "preservation_ref": rec.unique_commits.preservation_ref,
            "primary_destination": rec.primary_destination,
            "canonical_repo": rec.destination.canonical_repo,
            "remote_commit_sha": rec.destination.remote_commit_sha,
            "remote_verified": rec.destination.remote_verified,
            "gates_passed": rec.gates_passed,
            "highest_gate": rec.highest_gate,
            "disposition": rec.disposition,
            "disposition_rationale": rec.disposition_rationale,
            "safe_to_delete": rec.is_safe_to_delete(),
            "blockers": rec.blockers(),
            "record_id": rec.record_id,
        }

    return {
        "manifest_type": "AETHERIUS_FORK_PREDECESSOR_MIGRATION",
        "generated_at": time.time(),
        "provenance_rule": "Deleting the personal fork must never delete the "
                           "provenance trail. Upstream URL/SHA/license and "
                           "destination implementation/test evidence are "
                           "retained permanently.",
        "counts": {
            "total": len(registry.all()),
            "safe_to_delete": len(safe),
            "retained": len(retained),
        },
        "safe_to_delete": [row(r) for r in safe],
        "retained": [row(r) for r in retained],
    }


def write_manifest(registry: ProvenanceRegistry, path: str) -> str:
    manifest = build_manifest(registry)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    return path
