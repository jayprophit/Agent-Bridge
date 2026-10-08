"""Migration provenance + gate tests (§10 Fork/Predecessor Migration Programme).

The critical rule under test throughout:

    Deleting the personal fork must never delete the provenance trail.

Several tests are deliberately adversarial: they try every shortcut to a
SAFE_TO_DELETE verdict and must all fail. A fork that cannot be deleted
is the safe default; a fork that can be deleted without the full gate is
a security defect.
"""

import json
import os
import shutil

import pytest

from migration.provenance import (
    AUDIT_NOT_A_FORK, AUDIT_VERIFIED, DELETABLE_DISPOSITIONS,
    DISPOSITION_BLOCKED_LICENSE, DISPOSITION_KEEP_DEPENDENCY,
    DISPOSITION_MIGRATED, DISPOSITION_NOT_APPLICABLE, DISPOSITION_PENDING,
    DISPOSITION_REJECTED, DISPOSITION_SUPERSEDED, GATE_COMMITTED,
    GATE_IMPLEMENTED, GATE_MANIFESTED, GATE_ORDER, GATE_REMOTE_SHA,
    GATE_SAFE_TO_DELETE, GATE_STRATEGY_CHOSEN, GATE_TESTED,
    GATE_UNIQUE_COMMITS, GATE_UNIQUE_CAPABILITY, GATE_UPSTREAM_VERIFIED,
    GATE_CANONICAL_OWNER, STRATEGY_DEPENDENCY, STRATEGY_REFERENCE_ONLY,
    GateError, ProvenanceRecord, ProvenanceRegistry, catalog_coverage,
    load_catalog, records_from_catalog,
)

CATALOG = os.environ.get(
    "AETHERIUS_MIGRATION_CATALOG",
    os.path.join("migration", "evidence", "catalog",
                 "Aetherius_Fork_Use_Case_Migration_Catalog_2026-10-08.csv"))
HAS_CATALOG = os.path.isfile(CATALOG)

VERIFIED_FORK_FACTS = {
    "audit_status": AUDIT_VERIFIED,
    "nameWithOwner": "jayprophit/llama.cpp",
    "url": "https://github.com/jayprophit/llama.cpp",
    "isFork": True,
    "isArchived": False,
    "defaultBranchRef": {"name": "master"},
    "pushedAt": "2026-09-11T06:27:16Z",
    "licenseInfo": {"key": "mit", "name": "MIT License", "nickname": ""},
    "parent": {"name": "llama.cpp", "owner": {"login": "ggml-org"},
               "defaultBranchRef": {"name": "master"}},
}


@pytest.fixture
def reg(tmp_path):
    return ProvenanceRegistry(str(tmp_path / "provenance.json"))


def _rec(record_id="PROV-TEST000000000001", repo="jayprophit/testfork"):
    return ProvenanceRecord(record_id=record_id, source_repo=repo,
                            source_kind="FORK",
                            capability_summary="test capability")


def _verified(rec):
    rec.upstream.is_fork = True
    rec.upstream.upstream_full_name = "upstream-org/testfork"
    rec.upstream.upstream_url = "https://github.com/upstream-org/testfork"
    rec.upstream.license_key = "mit"
    rec.upstream.audit_status = AUDIT_VERIFIED
    rec.pass_gate(GATE_UPSTREAM_VERIFIED)
    return rec


def _fully_migrated(rec):
    """A record that has legitimately earned SAFE_TO_DELETE."""
    _verified(rec)
    rec.capability_summary = "GGUF quantised CPU inference"
    rec.pass_gate(GATE_UNIQUE_CAPABILITY)
    rec.primary_destination = "Agent-Bridge Hybrid Compute"
    rec.pass_gate(GATE_CANONICAL_OWNER)
    rec.pass_gate(GATE_STRATEGY_CHOSEN)
    rec.destination.canonical_repo = "jayprophit/Agent-Bridge"
    rec.destination.requirement_ids = ["REQ-HC-001"]
    rec.destination.implementation_files = ["compute/inference_adapter.py"]
    rec.pass_gate(GATE_IMPLEMENTED)
    rec.destination.test_files = ["tests/test_inference_adapter.py"]
    rec.pass_gate(GATE_TESTED)
    rec.destination.local_commit_sha = "a" * 40
    rec.pass_gate(GATE_COMMITTED)
    rec.destination.remote_commit_sha = "a" * 40
    rec.destination.remote_verified = True
    rec.pass_gate(GATE_REMOTE_SHA)
    rec.pass_gate(GATE_MANIFESTED)
    rec.unique_commits.has_unique_commits = False
    rec.unique_commits.preservation_mode = "NONE"
    rec.pass_gate(GATE_UNIQUE_COMMITS)
    rec.set_disposition(DISPOSITION_MIGRATED, "ported and remote-verified")
    rec.pass_gate(GATE_SAFE_TO_DELETE)
    return rec


# =====================================================================
# 1. Catalog ingestion
# =====================================================================

@pytest.mark.skipif(not HAS_CATALOG, reason="catalog CSV not present")
def test_catalog_loads_all_350_rows():
    rows = load_catalog(CATALOG)
    assert len(rows) == 350, f"expected 350 fork candidates, got {len(rows)}"


@pytest.mark.skipif(not HAS_CATALOG, reason="catalog CSV not present")
def test_catalog_has_18_categories():
    cov = catalog_coverage(CATALOG)
    assert cov["total_rows"] == 350
    assert len(cov["by_category"]) == 18


@pytest.mark.skipif(not HAS_CATALOG, reason="catalog CSV not present")
def test_catalog_confidence_distribution():
    cov = catalog_coverage(CATALOG)
    assert cov["by_confidence"]["HIGH"] == 233
    assert cov["by_confidence"]["MEDIUM"] == 107
    assert cov["by_confidence"]["LOW"] == 10


@pytest.mark.skipif(not HAS_CATALOG, reason="catalog CSV not present")
def test_catalog_low_confidence_repos_are_the_verify_set():
    """The 10 LOW rows are exactly the VERIFY_UPSTREAM set."""
    rows = load_catalog(CATALOG)
    low = {r["repository"] for r in rows if r["analysis_confidence"] == "LOW"}
    verify = {r["repository"] for r in rows
              if r["category"] == "VERIFY_UPSTREAM"}
    assert low == verify
    assert len(verify) == 10


@pytest.mark.skipif(not HAS_CATALOG, reason="catalog CSV not present")
def test_records_from_catalog_are_all_unverified():
    """A catalog classification is a HYPOTHESIS, never a verification."""
    recs = records_from_catalog(CATALOG)
    assert len(recs) == 350
    assert all(r.disposition == DISPOSITION_PENDING for r in recs)
    assert all(r.gates_passed == [] for r in recs)
    assert all(r.upstream.audit_status == "NOT_CHECKED" for r in recs)


@pytest.mark.skipif(not HAS_CATALOG, reason="catalog CSV not present")
def test_no_catalog_record_is_safe_to_delete():
    recs = records_from_catalog(CATALOG)
    assert not any(r.is_safe_to_delete() for r in recs), \
        "catalog-derived records must never be deletable without live audit"


@pytest.mark.skipif(not HAS_CATALOG, reason="catalog CSV not present")
def test_record_ids_are_unique_and_deterministic():
    a = records_from_catalog(CATALOG)
    b = records_from_catalog(CATALOG)
    assert len({r.record_id for r in a}) == 350
    assert [r.record_id for r in a] == [r.record_id for r in b]


@pytest.mark.skipif(not HAS_CATALOG, reason="catalog CSV not present")
def test_catalog_rejects_missing_columns(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("repository,category\njayprophit/x,FORK\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_catalog(str(bad))


# =====================================================================
# 2. Gate ordering is strictly enforced (§10)
# =====================================================================

def test_gate_cannot_be_skipped():
    rec = _rec()
    with pytest.raises(GateError):
        rec.pass_gate(GATE_SAFE_TO_DELETE)


def test_gate_cannot_be_skipped_to_unique_commits():
    rec = _verified(_rec())
    with pytest.raises(GateError):
        rec.pass_gate(GATE_UNIQUE_COMMITS)


def test_gate_must_follow_order():
    rec = _verified(_rec())
    rec.pass_gate(GATE_UNIQUE_CAPABILITY)
    rec.pass_gate(GATE_CANONICAL_OWNER)
    rec.pass_gate(GATE_STRATEGY_CHOSEN)
    with pytest.raises(GateError):
        rec.pass_gate(GATE_REMOTE_SHA)      # skipped IMPLEMENTED/TESTED/COMMITTED


def test_gate_repeat_pass_is_idempotent():
    rec = _verified(_rec())
    rec.pass_gate(GATE_UNIQUE_CAPABILITY)
    rec.pass_gate(GATE_UNIQUE_CAPABILITY)
    assert rec.gates_passed.count(GATE_UNIQUE_CAPABILITY) == 1


def test_unknown_gate_rejected():
    with pytest.raises(GateError):
        _rec().pass_gate("GATE_MADE_UP")


def test_gate_order_has_11_steps():
    assert len(GATE_ORDER) == 11
    assert GATE_ORDER[-1] == GATE_SAFE_TO_DELETE


# =====================================================================
# 3. THE CRITICAL RULE — deletion authority
# =====================================================================

def test_fresh_record_is_not_deletable():
    assert _rec().is_safe_to_delete() is False


def test_verified_alone_is_not_deletable():
    """Live audit is necessary but nowhere near sufficient."""
    assert _verified(_rec()).is_safe_to_delete() is False


def test_fully_migrated_is_deletable():
    assert _fully_migrated(_rec()).is_safe_to_delete() is True


def test_local_commit_without_remote_blocks_deletion():
    """Local commit != remote preservation."""
    rec = _fully_migrated(_rec())
    rec.destination.remote_verified = False
    rec.destination.remote_commit_sha = None
    assert rec.is_safe_to_delete() is False
    assert any("remote" in b for b in rec.blockers())


def test_unpreserved_unique_commits_block_deletion():
    rec = _fully_migrated(_rec())
    rec.unique_commits.has_unique_commits = True
    rec.unique_commits.preservation_ref = None
    assert rec.is_safe_to_delete() is False
    assert any("unique commits" in b for b in rec.blockers())


def test_preserved_unique_commits_allow_deletion():
    rec = _fully_migrated(_rec())
    rec.unique_commits.has_unique_commits = True
    rec.unique_commits.unique_commit_count = 3
    rec.unique_commits.preservation_mode = "PATCHSET"
    rec.unique_commits.preservation_ref = "sha-of-preserved-patch"
    assert rec.is_safe_to_delete() is True


def test_unknown_unique_commit_status_blocks_deletion():
    """Never delete when data loss cannot be assessed."""
    rec = _fully_migrated(_rec())
    rec.unique_commits.has_unique_commits = None
    assert rec.is_safe_to_delete() is False
    assert any("unknown" in b for b in rec.blockers())


@pytest.mark.parametrize("hold", [DISPOSITION_KEEP_DEPENDENCY,
                                  DISPOSITION_BLOCKED_LICENSE,
                                  "BLOCKED_TECHNICAL", DISPOSITION_PENDING])
def test_hold_dispositions_block_deletion(hold):
    """§10: only the first four dispositions permit deletion."""
    rec = _fully_migrated(_rec())
    rec.set_disposition(hold, "hold")
    assert rec.is_safe_to_delete() is False


@pytest.mark.parametrize("disp", sorted(DELETABLE_DISPOSITIONS))
def test_deletable_dispositions_permit_deletion_when_gated(disp):
    rec = _fully_migrated(_rec())
    rec.set_disposition(disp, "reason")
    assert rec.is_safe_to_delete() is True


def test_invalid_disposition_rejected():
    with pytest.raises(GateError):
        _rec().set_disposition("DELETED_I_GUESS", "nope")


def test_blockers_are_actionable():
    rec = _rec()
    b = rec.blockers()
    assert len(b) > 0
    assert any("gate not passed" in x for x in b)
    assert any("disposition" in x for x in b)


# =====================================================================
# 4. Provenance outlives the fork (the permanent-trail rule)
# =====================================================================

def test_record_survives_registry_roundtrip(reg, tmp_path):
    rec = _fully_migrated(_rec())
    reg.add(rec)
    sha = reg.save()
    reloaded = ProvenanceRegistry(str(tmp_path / "provenance.json"))
    got = reloaded.get(rec.record_id)
    assert got is not None
    assert got.upstream.upstream_url == rec.upstream.upstream_url
    assert got.upstream.license_key == "mit"
    assert got.is_safe_to_delete() is True
    assert sha and len(sha) == 64


def test_provenance_is_retained_after_fork_disappears(reg, tmp_path):
    """The record is keyed on nothing that the fork's existence provides.

    Deleting the repository cannot reach into the registry: there is no
    code path that removes a record because its source vanished.
    """
    rec = _fully_migrated(_rec())
    reg.add(rec)
    reg.save()
    reg2 = ProvenanceRegistry(str(tmp_path / "provenance.json"))
    # Simulate the fork being gone: audit now reports MISSING.
    reg2.get(rec.record_id).upstream.audit_status = "REPO_MISSING"
    reg2.save()
    reg3 = ProvenanceRegistry(str(tmp_path / "provenance.json"))
    assert reg3.get(rec.record_id) is not None, \
        "provenance must survive fork deletion"
    assert reg3.get(rec.record_id).upstream.upstream_url


def test_registry_rejects_duplicate_ids(reg):
    reg.add(_rec("PROV-DUP"))
    with pytest.raises(GateError):
        reg.add(_rec("PROV-DUP"))


def test_registry_summary_partitions_queues(reg):
    reg.add(_fully_migrated(_rec("PROV-OK")))
    reg.add(_verified(_rec("PROV-PARTIAL")))
    s = reg.summary()
    assert s["total_records"] == 2
    assert s["safe_to_delete"] == 1
    assert s["retained"] == 1
    assert len(reg.safe_to_delete_queue()) == 1
    assert len(reg.retained_queue()) == 1


def test_by_source_lookup(reg):
    reg.add(_verified(_rec("PROV-X", "jayprophit/llama.cpp")))
    assert reg.by_source("jayprophit/llama.cpp").record_id == "PROV-X"
    assert reg.by_source("jayprophit/nope") is None


def test_empty_registry_summary(reg):
    s = reg.summary()
    assert s["total_records"] == 0
    assert s["safe_to_delete"] == 0


def test_to_dict_exposes_audit_view():
    d = _rec().to_dict()
    for key in ("safe_to_delete", "highest_gate", "blockers"):
        assert key in d
    assert d["safe_to_delete"] is False


# =====================================================================
# 5. Predecessor chain records (§ predecessor migration map)
# =====================================================================

@pytest.mark.parametrize("pred", [
    "aetherium", "Aetherial", "aetherial-platform", "Niche_platform",
    "Quantum-OS", "Crossplatform---multiplatform", "QVA-merged",
    "Veyra", "VirtualAssistant",
])
def test_predecessors_start_locked(reg, pred):
    """Every predecessor begins at gate 0 with no deletion authority."""
    rec = ProvenanceRecord(record_id=f"PROV-PRED-{pred[:8].upper()}",
                           source_repo=f"jayprophit/{pred}",
                           source_kind="PREDECESSOR",
                           capability_summary=f"{pred} predecessor work")
    reg.add(rec)
    assert rec.is_safe_to_delete() is False
    assert rec.gates_passed == []
    assert rec.disposition == DISPOSITION_PENDING


def test_qva_merged_must_be_decomposed():
    """QVA-merged crosses a corrected boundary — it cannot be migrated
    wholesale. Its record must carry split destinations."""
    rec = ProvenanceRecord(record_id="PROV-QVA", source_repo="jayprophit/QVA-merged",
                           source_kind="PREDECESSOR",
                           capability_summary="OS/platform/runtime + assistant/"
                                              "identity/interaction")
    rec.primary_destination = "Aetherius-OS + Genesis (SPLIT REQUIRED)"
    assert "SPLIT" in rec.primary_destination
    assert rec.is_safe_to_delete() is False


# =====================================================================
# 6. Live auditor (network tests, skipped when gh is unavailable)
# =====================================================================

def test_gh_availability_probe():
    """Never raises; reports a reason either way."""
    from migration.auditor import gh_available
    ok, reason = gh_available()
    assert isinstance(ok, bool)
    assert isinstance(reason, str) and reason


def test_audit_applies_verified_facts_and_passes_gate_1():
    from migration.auditor import apply_audit
    rec = apply_audit(_rec(), VERIFIED_FORK_FACTS)
    assert rec.upstream.audit_status == AUDIT_VERIFIED
    assert rec.upstream.upstream_full_name == "ggml-org/llama.cpp"
    assert rec.upstream.license_key == "mit"
    assert rec.upstream.fork_default_branch == "master"
    assert GATE_UPSTREAM_VERIFIED in rec.gates_passed


def test_audit_of_non_fork_does_not_pass_gate_1():
    from migration.auditor import apply_audit
    facts = dict(VERIFIED_FORK_FACTS, isFork=False,
                 audit_status=AUDIT_NOT_A_FORK)
    rec = apply_audit(_rec(), facts)
    assert rec.upstream.audit_status == AUDIT_NOT_A_FORK
    assert GATE_UPSTREAM_VERIFIED not in rec.gates_passed


def test_audit_of_missing_repo_does_not_pass_gate_1():
    from migration.auditor import apply_audit
    rec = apply_audit(_rec(), {"audit_status": "REPO_MISSING",
                               "error": "not found"})
    assert GATE_UPSTREAM_VERIFIED not in rec.gates_passed
    assert rec.upstream.audit_error


def test_audit_error_does_not_pass_gate_1():
    from migration.auditor import apply_audit
    rec = apply_audit(_rec(), {"audit_status": "ERROR", "error": "boom"})
    assert GATE_UPSTREAM_VERIFIED not in rec.gates_passed


def test_audit_never_deletes_anything():
    """The auditor is READ-ONLY. No mutation verb may appear in it."""
    import migration.auditor as mod
    src = open(mod.__file__, encoding="utf-8").read()
    for verb in ("repo delete", "repo archive", "--method", "DELETE"):
        assert verb not in src, f"auditor must never {verb}"


@pytest.mark.skipif(shutil.which("gh") is None, reason="gh not installed")
def test_live_audit_of_one_known_fork():
    """A real network call against a real repo. Skipped, never faked."""
    from migration.auditor import audit_batch, gh_available
    ok, _ = gh_available()
    if not ok:
        pytest.skip("gh not authenticated")
    rec = _rec("PROV-LIVE", "jayprophit/llama.cpp")
    result = audit_batch([rec], limit=1)
    assert result["audited"] == 1
    assert rec.upstream.audit_status in (AUDIT_VERIFIED, AUDIT_NOT_A_FORK,
                                         "REPO_MISSING", "ERROR",
                                         "AUTH_FAILED")
    if rec.upstream.audit_status == AUDIT_VERIFIED:
        assert rec.upstream.upstream_full_name
        assert GATE_UPSTREAM_VERIFIED in rec.gates_passed
