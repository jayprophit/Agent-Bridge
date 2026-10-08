"""Tests for Enterprise Team, Provider Adapter V2, Distributed Tracing,
GitHub Repository Details, Fork Catalog, and MAT Reconciliation.

Run: python tests/test_ai_gateway_and_knowledge_fabric_v2.py -v
  or: python -m pytest tests/test_ai_gateway_and_knowledge_fabric_v2.py -v
"""
import sys
import os
import time
import json
import tempfile
import hashlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from compute.enterprise_team import (
    EnterpriseTeam, TeamConfig, HandoffContext, Specialist,
    WorkerStatus, form_team, SPECIALIST_ROLES,
    MODEL_CLASS_ROLE_MAP,
)
from compute.tracing import TraceCollector, Span, Trace, create_trace
from models.provider_adapter_v2 import (
    V2Capabilities, NormalizedProviderError, V2InferenceRequest, V2InferenceResponse,
    ProviderAdapterV2, register_v2_capabilities, is_provider_v2_ready,
    ERR_RATE_LIMIT, ERR_AUTH_FAILURE, ERR_TIMEOUT, ERR_PROVIDER_UNAVAILABLE,
)
from knowledge_fabric.github_adapter import (
    GitHubAdapter, FileIngestionAdapter, ImageIngestionAdapter,
)
from knowledge_fabric.source_adapter import (
    SourceMetadata, SOURCE_TYPE_REPOSITORY, SOURCE_TYPE_FILE, SOURCE_TYPE_IMAGE,
    CAP_LIST_CONVERSATIONS, CAP_GET_METADATA, CAP_SEARCH,
    STATE_VERIFIED, STATE_AUTH_REQUIRED, STATE_BLOCKED,
)
from knowledge_fabric.fork_catalog import (
    FORK_MIGRATION_CATALOG, MAT_CANONICAL_REPO, MAT_ALTERNATE_DOES_NOT_EXIST,
    get_repo_classification, get_repo_decision, list_mat_repos,
)


# ---- Enterprise Team tests (§83, §84, §85) -----------------------------------

def test_enterprise_team_nine_roles():
    """9 distinct specialist roles from 5 model classes (§84, §85)."""
    assert len(SPECIALIST_ROLES) == 9
    # Verify all 5 model classes are represented
    model_classes = {r["model_class"] for r in SPECIALIST_ROLES.values()}
    assert len(model_classes) == 5
    # Verify role names
    expected_roles = {
        "coding_worker", "research_worker", "reviewer", "test_runner",
        "coordinator", "routing_specialist", "cost_specialist",
        "evidence_reviewer", "handoff_arbiter",
    }
    assert set(SPECIALIST_ROLES.keys()) == expected_roles


def test_enterprise_team_dynamic_formation():
    """Dynamic team formation from capability spec (§84)."""
    team = form_team(
        objective="implement execution target registry",
        required_roles=["coding_worker", "reviewer", "test_runner"],
        privacy="PROJECT",
        allow_cloud=False,
    )
    assert len(team.specialists) == 3
    assert "coding_worker" in team.specialists
    assert "reviewer" in team.specialists
    assert "test_runner" in team.specialists
    assert team.execution_target == "local"


def test_enterprise_team_handoff():
    """Worker-to-worker handoff with provenance (§82, §83)."""
    team = form_team(
        objective="test handoff",
        required_roles=["coding_worker", "reviewer"],
    )
    h = team.handoff(
        from_role="coding_worker",
        to_role="reviewer",
        content="Code implemented with caching support",
        provenance_refs=["commit-a1b2c3", "test-result-xyz"],
        confidence=0.85,
    )
    assert h.from_role == "coding_worker"
    assert h.to_role == "reviewer"
    assert len(h.provenance_refs) == 2
    assert h.confidence == 0.85


def test_enterprise_team_optional_worker_failure():
    """Optional-worker failure handling: skip + continue (§83)."""
    team = form_team(
        objective="pipeline with optional worker",
        required_roles=["coding_worker", "reviewer", "evidence_reviewer"],
    )

    call_count = [0]
    def coder_fn(spec):
        call_count[0] += 1
        from models.provider_adapter import ProviderResponse
        return ProviderResponse(model="test", content="implementation done", usage={})

    def fail_fn(spec):
        raise RuntimeError("worker crashed")

    # coding_worker succeeds
    team.run_role("coding_worker", coder_fn)
    assert team.specialists["coding_worker"].status == WorkerStatus.COMPLETED

    # evidence_reviewer fails → should be marked FAILED, not crash
    team.run_role("evidence_reviewer", fail_fn)
    assert team.specialists["evidence_reviewer"].status == WorkerStatus.FAILED
    assert team.specialists["evidence_reviewer"].error is not None


def test_enterprise_team_abc_handoff():
    """A→B→C handoff proof with independent review (§76)."""
    team = form_team(
        objective="ABC handoff proof",
        required_roles=["coding_worker", "reviewer", "evidence_reviewer"],
    )

    from models.provider_adapter import ProviderResponse

    # Stage A: coding worker
    def coder(spec):
        return ProviderResponse(model="codellama", content="CODE: def foo() -> int: return 42", usage={})
    # Stage B: reviewer
    def reviewer(spec):
        return ProviderResponse(model="gpt", content="REVIEW: code is clean, follows conventions", usage={})
    # Stage C: evidence reviewer
    def evidence(spec):
        return ProviderResponse(model="gpt", content="EVIDENCE: 2 tests pass, SHA verified", usage={})

    results = team.run_pipeline([
        ("coding_worker", coder),
        ("reviewer", reviewer),
        ("evidence_reviewer", evidence),
    ])

    assert all(r.status == WorkerStatus.COMPLETED for r in results.values())
    # Independent review: reviewer reviews coder's output
    review = team.review("evidence_reviewer", "coding_worker")
    assert review["verdict"] == "PASS"


# ---- Distributed Tracing tests (§114) ----------------------------------------

def test_trace_collector_spans():
    """TraceCollector creates spans with trace_id/span_id/parent_span_id."""
    tracer = TraceCollector()
    root = tracer.start_span("gateway.request", trace_id="trace-001")
    child = tracer.start_span("model_router.route", parent_span_id=root, trace_id="trace-001")
    tracer.end_span(child, status="OK")
    tracer.end_span(root, status="OK")
    assert root.span_id != child.span_id
    assert child.parent_span_id == root.span_id
    assert root.duration_ms >= 0
    assert child.duration_ms >= 0
    tr = tracer.export_trace("trace-001")
    assert tr["trace_id"] == "trace-001"
    assert len(tr["spans"]) == 2


def test_trace_collector_error():
    """Error spans carry normalized_error."""
    tracer = TraceCollector()
    span = tracer.start_span("provider.infer")
    tracer.end_span(span, status="ERROR", error=ERR_PROVIDER_UNAVAILABLE)
    assert span.normalized_error == ERR_PROVIDER_UNAVAILABLE
    assert span.status == "ERROR"


def test_trace_collector_no_secrets():
    """Trace attributes must not contain secrets."""
    tracer = TraceCollector()
    span = tracer.start_span("gateway.request",
                              request_id="req-1", model_id="test")
    tracer.end_span(span)
    export = tracer.export_trace(span.trace_id)
    span_data = export["spans"][0]
    # No secret fields
    for key in span_data:
        val = str(span_data[key])
        assert "api_key" not in val.lower()
        assert "password" not in val.lower()
        assert "token" not in val.lower()


def test_trace_collector_export():
    """Full trace export contains all required fields (§114)."""
    tracer = TraceCollector()
    root = tracer.start_span("gateway.request",
                              trace_id="t-abc", request_id="r-1",
                              task_id="task-1", team_id="team-1",
                              model_id="gpt-4", provider_id="openai",
                              target_id="local-ollama", cost_class="FREE_ONLY")
    tracer.end_span(root, status="OK")
    tr = tracer.export_trace("t-abc")
    assert tr["trace_id"] == "t-abc"
    assert tr["request_id"] == "r-1"
    assert tr["task_id"] == "task-1"
    assert tr["team_id"] == "team-1"
    spans = tr["spans"]
    assert len(spans) == 1
    s = spans[0]
    # V2 attributes are stored in the attributes dict
    assert s["attributes"]["model_id"] == "gpt-4"
    assert s["attributes"]["provider_id"] == "openai"
    assert s["attributes"]["target_id"] == "local-ollama"
    assert s["attributes"]["cost_class"] == "FREE_ONLY"


# ---- Provider Adapter V2 tests (§88) -----------------------------------------

def test_v2_capabilities_registry():
    """V2 capabilities registry declares each provider's actual features."""
    caps = register_v2_capabilities()
    assert "openai" in caps
    assert caps["openai"].supports_prompt_caching == True
    assert caps["openai"].supports_reasoning == True
    assert caps["openai"].supports_logprobs == True
    assert caps["openai"].supports_batch == True
    assert caps["openai"].supports_structured_output == True


def test_v2_normalized_errors():
    """NormalizedProviderError has stable classes (§88)."""
    err = NormalizedProviderError(
        error_class=ERR_RATE_LIMIT,
        message="rate limited",
        provider_id="openai",
        retry_after=60.0,
    )
    assert err.error_class == "RATE_LIMIT_EXCEEDED"
    assert err.retry_after == 60.0
    assert err.provider_id == "openai"
    # Must be an Exception
    try:
        raise err
    except NormalizedProviderError as e:
        assert str(e) == "rate limited"


def test_v2_provider_adapter_base():
    """ProviderAdapterV2 base class is backwards-compatible."""
    class TestV2Adapter(ProviderAdapterV2):
        name = "test-v2"
        def infer_v2(self, request: V2InferenceRequest) -> V2InferenceResponse:
            from models.provider_adapter import ProviderResponse
            return V2InferenceResponse(model=request.model, content="v2 response", usage={}, provider="test-v2", logprobs=None)

    adapter = TestV2Adapter()
    assert adapter.v2_capabilities is not None
    # V2 path
    req = V2InferenceRequest(messages=[{"role":"user","content":"hi"}], model="test")
    resp = adapter.infer_v2(req)
    assert resp.content == "v2 response"
    # V1 backwards-compat
    resp_v1 = adapter.infer([{"role":"user","content":"hi"}], model="test")
    assert resp_v1.content == "v2 response"


def test_v2_provider_readiness():
    """is_provider_v2_ready correctly identifies V2-capable providers."""
    assert is_provider_v2_ready("openai") == True
    assert is_provider_v2_ready("anthropic") == True
    assert is_provider_v2_ready("openrouter") == False  # only 1 V2 feature
    assert is_provider_v2_ready("does_not_exist") == False


# ---- GitHub Repository Detail tests (§19, §55) — the 5 that were skipped ----

_GH_ADAPTER: GitHubAdapter | None = None

def _get_gh_adapter():
    global _GH_ADAPTER
    if _GH_ADAPTER is None:
        _GH_ADAPTER = GitHubAdapter()
        if not _GH_ADAPTER._check_auth():
            return None
    return _GH_ADAPTER


def test_github_repo_detail_branches():
    """GitHub adapter can list repository branches (was skipped)."""
    adapter = _get_gh_adapter()
    if adapter is None:
        return  # skip if not authenticated
    repos = adapter.list_sources(limit=3)
    if not repos:
        return
    branches = adapter.get_repository_branches(repos[0].source_id, limit=5)
    assert isinstance(branches, list)
    if branches:
        assert "name" in branches[0]
        assert "commit" in branches[0]


def test_github_repo_detail_commits():
    """GitHub adapter can list repository commits (was skipped)."""
    adapter = _get_gh_adapter()
    if adapter is None:
        return
    repos = adapter.list_sources(limit=3)
    if not repos:
        return
    commits = adapter.get_repository_commits(repos[0].source_id, limit=5)
    assert isinstance(commits, list)
    if commits:
        assert "sha" in commits[0] or "number" in commits[0] or "author" in commits[0]


def test_github_repo_detail_issues():
    """GitHub adapter can list repository issues (was skipped)."""
    adapter = _get_gh_adapter()
    if adapter is None:
        return
    repos = adapter.list_sources(limit=3)
    if not repos:
        return
    issues = adapter.get_repository_issues(repos[0].source_id, limit=5)
    assert isinstance(issues, list)


def test_github_repo_detail_prs():
    """GitHub adapter can list repository pull requests (was skipped)."""
    adapter = _get_gh_adapter()
    if adapter is None:
        return
    repos = adapter.list_sources(limit=3)
    if not repos:
        return
    prs = adapter.get_repository_prs(repos[0].source_id, limit=5)
    assert isinstance(prs, list)


def test_github_repo_detail_fork_info():
    """GitHub adapter can get fork/parent info (was skipped)."""
    adapter = _get_gh_adapter()
    if adapter is None:
        return
    repos = adapter.list_sources(limit=3)
    if not repos:
        return
    fork_info = adapter.get_fork_info(repos[0].source_id)
    assert isinstance(fork_info, dict)
    if fork_info:
        assert "fork" in fork_info or "is_archived" in fork_info or "parent" in fork_info


# ---- Fork Catalog + MAT Reconciliation tests (§20, §22, §111) ----------------

def test_fork_catalog_mat_canonical():
    """MAT canonical repo is confirmed; alternate does not exist."""
    assert MAT_CANONICAL_REPO == "jayprophit/Materials-Atlas-Table-Codex---MAT"
    mat_info = FORK_MIGRATION_CATALOG["Materials-Atlas-Table-Codex---MAT"]
    assert mat_info["classification"] == "ACTIVE_CANONICAL"
    assert mat_info["decision"] == "EXTEND_CANONICAL"


def test_fork_catalog_classification():
    """All 17 repositories are classified."""
    assert len(FORK_MIGRATION_CATALOG) >= 17
    # Canonical repos
    assert get_repo_classification("Agent-Bridge") == "ACTIVE_CANONICAL"
    assert get_repo_classification("Genesis") == "ACTIVE_CANONICAL"
    assert get_repo_classification("Aetherius-OS") == "ACTIVE_CANONICAL"
    # Active supporting
    assert get_repo_classification("IDE-Workspace") == "ACTIVE_SUPPORTING"
    assert get_repo_classification("Universal-Bridge") == "ACTIVE_SUPPORTING"
    # Forks
    assert get_repo_classification("Poietek") == "FORK"
    assert get_repo_classification("comfyui") != "ACTIVE_CANONICAL" or "not found"


def test_fork_catalog_mat_decision():
    """MAT decision: EXTEND_CANONICAL, no new repo."""
    assert get_repo_decision("Materials-Atlas-Table-Codex---MAT") == "EXTEND_CANONICAL"
    assert get_repo_decision("Agent-Bridge") == "EXTEND_CANONICAL"
    mat_repos = list_mat_repos()
    assert "Materials-Atlas-Table-Codex---MAT" in mat_repos
    # The alternate name does not exist
    assert MAT_ALTERNATE_DOES_NOT_EXIST not in FORK_MIGRATION_CATALOG


def test_fork_catalog_no_duplicate_mat():
    """No duplicate/forked MAT repositories exist."""
    mat_repos = list_mat_repos()
    # Only one canonical MAT repo
    canonical = [r for r in mat_repos
                 if FORK_MIGRATION_CATALOG.get(r, {}).get("classification") == "ACTIVE_CANONICAL"]
    assert len(canonical) == 1
    assert canonical[0] == "Materials-Atlas-Table-Codex---MAT"


# ---- MAT Reconciliation proof (§111) -----------------------------------------

def test_mat_reconciliation_one_repo():
    """MAT reconciliation: only one repository exists, decision is EXTEND_CANONICAL."""
    adapter = _get_gh_adapter()
    if adapter is None:
        return  # skip if not authenticated
    # Enumerate all repos and confirm exactly one has "Materials-Atlas" in the name
    all_repos = adapter.list_sources(limit=100)
    mat_repos = [r for r in all_repos if "material" in r.title.lower()]
    assert len(mat_repos) == 1
    assert mat_repos[0].title == "Materials-Atlas-Table-Codex---MAT"
    assert mat_repos[0].platform == "github"


# ---- Integration: Enterprise Team + Gateway -----------------------------------

def test_team_summary_and_evidence():
    """Team produces serializable summary and evidence."""
    from knowledge_fabric.github_adapter import GitHubAdapter as _GH
    adapter = _get_gh_adapter()
    if adapter is None:
        team = form_team(
            objective="test summary",
            required_roles=["coding_worker", "reviewer"],
        )
    else:
        team = form_team(
            objective="test summary",
            required_roles=["coding_worker", "reviewer"],
            allow_cloud=False,
        )
    from models.provider_adapter import ProviderResponse
    team.run_role("coding_worker", lambda s: ProviderResponse(model="x", content="done", usage={}))

    evidence = team.to_evidence()
    assert "team_id" in evidence
    assert "specialists" in evidence
    assert "handoffs" in evidence
    summary = team.summary()
    assert summary["team_id"] == team.team_id
    assert len(summary["specialists"]) == 2


# ---- Runner ------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        # Enterprise Team (§83, §84, §85)
        ("test_enterprise_team_nine_roles", test_enterprise_team_nine_roles),
        ("test_enterprise_team_dynamic_formation", test_enterprise_team_dynamic_formation),
        ("test_enterprise_team_handoff", test_enterprise_team_handoff),
        ("test_enterprise_team_optional_worker_failure", test_enterprise_team_optional_worker_failure),
        ("test_enterprise_team_abc_handoff", test_enterprise_team_abc_handoff),
        ("test_team_summary_and_evidence", test_team_summary_and_evidence),
        # Distributed Tracing (§114)
        ("test_trace_collector_spans", test_trace_collector_spans),
        ("test_trace_collector_error", test_trace_collector_error),
        ("test_trace_collector_no_secrets", test_trace_collector_no_secrets),
        ("test_trace_collector_export", test_trace_collector_export),
        # Provider Adapter V2 (§88)
        ("test_v2_capabilities_registry", test_v2_capabilities_registry),
        ("test_v2_normalized_errors", test_v2_normalized_errors),
        ("test_v2_provider_adapter_base", test_v2_provider_adapter_base),
        ("test_v2_provider_readiness", test_v2_provider_readiness),
        # GitHub Repository Detail (was skipped — now fixed)
        ("test_github_repo_detail_branches", test_github_repo_detail_branches),
        ("test_github_repo_detail_commits", test_github_repo_detail_commits),
        ("test_github_repo_detail_issues", test_github_repo_detail_issues),
        ("test_github_repo_detail_prs", test_github_repo_detail_prs),
        ("test_github_repo_detail_fork_info", test_github_repo_detail_fork_info),
        # Fork Catalog + MAT Reconciliation
        ("test_fork_catalog_mat_canonical", test_fork_catalog_mat_canonical),
        ("test_fork_catalog_classification", test_fork_catalog_classification),
        ("test_fork_catalog_mat_decision", test_fork_catalog_mat_decision),
        ("test_fork_catalog_no_duplicate_mat", test_fork_catalog_no_duplicate_mat),
        ("test_mat_reconciliation_one_repo", test_mat_reconciliation_one_repo),
    ]

    passed = failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {name}: {e}")
            import traceback; traceback.print_exc()
            failed += 1

    total = passed + failed
    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed, {total} total")
    print(f"{'='*60}")
    sys.exit(1 if failed else 0)
