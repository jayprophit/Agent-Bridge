"""Tests for the AI Gateway and Knowledge Fabric (§86, §55).

Run: python tests/test_ai_gateway_and_knowledge_fabric.py -v
  or: python -m pytest tests/test_ai_gateway_and_knowledge_fabric.py -v
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from compute.ai_gateway import AetheriusGateway, create_gateway
from compute.cost_engine import default_cost_engine, CostEngine, Budget
from compute.execution_target_registry import seed_local_targets
from compute.instance_registry import InstanceRegistry
from models.inference_contract import (
    AetheriusInferenceRequest, AetheriusInferenceResponse,
    AetheriusRoutingDecision, AetheriusProviderError,
    PRIVACY_PROJECT, PRIVACY_SECRET_LOCAL_ONLY, PRIVACY_CONFIDENTIAL,
    FREE_ONLY, HOBBY_CREDIT_ONLY,
    BUDGET_EXCEEDED, PRIVACY_VIOLATION, PROVIDER_INTERNAL,
    AI_GATEWAY_PATHS, AI_GATEWAY_BASE,
)
from knowledge_fabric.source_adapter import (
    KnowledgeSourceAdapter, SourceMetadata, SourceMetadata,
    compute_content_hash, stable_source_id,
    SOURCE_TYPE_CONVERSATION, SOURCE_TYPE_REPOSITORY,
    SOURCE_TYPE_FILE, SOURCE_TYPE_IMAGE,
    CAP_LIST_CONVERSATIONS, CAP_GET_METADATA, CAP_SEARCH,
    STATE_SPECIFIED, STATE_VERIFIED, STATE_AUTH_REQUIRED,
    ACCESS_OFFICIAL_API,
)
from knowledge_fabric.source_provenance import (
    SourceReference, ProvenanceRecord, DerivedKnowledge,
    CONF_SOURCE_QUOTE, CONF_UNVERIFIED_RESEARCH,
    KIND_EVIDENCE, KIND_REQUIREMENT, KIND_DECISION,
    LIFE_CURRENT, LIFE_SUPERSEDED,
)
from knowledge_fabric.context_broker import (
    ContextBroker, ContextRequest, ContextPackage,
    ROLE_PRIVACY_CEILINGS,
)
from knowledge_fabric.github_adapter import GitHubAdapter


# ---- AI Gateway tests (§86, §87) --------------------------------------------

def test_gateway_creation():
    """Gateway can be created with default registries."""
    gw = create_gateway()
    assert gw is not None
    assert len(gw.execution_targets) >= 2  # at least Windows + Docker/Ollama
    assert gw.cost_engine.default_budget_class == FREE_ONLY


def test_gateway_routes():
    """Gateway exposes canonical API paths (§86)."""
    gw = create_gateway()
    routes = gw.routes
    assert routes["inference"] == "/aetherius/v1/inference"
    assert routes["models"] == "/aetherius/v1/models"
    assert routes["providers"] == "/aetherius/v1/providers"
    assert routes["health"] == "/aetherius/v1/health"
    assert routes["routing_dry_run"] == "/aetherius/v1/routing/dry-run"
    assert AI_GATEWAY_BASE == "/aetherius/v1"


def test_gateway_health():
    """Health endpoint returns provider/target/model counts."""
    gw = create_gateway()
    health = gw.health()
    assert health["status"] == "HEALTHY"
    assert health["execution_targets"] >= 2
    assert "daily_cost_usd" in health
    assert health["daily_cost_usd"] == 0.0


def test_gateway_secret_local_only_blocks_remote():
    """SECRET_LOCAL_ONLY request with remote provider must be blocked (§69, §119)."""
    gw = create_gateway()
    req = AetheriusInferenceRequest(
        capability="coding",
        privacy_classification=PRIVACY_SECRET_LOCAL_ONLY,
        provider_preference="openrouter",  # remote provider
        budget_class=FREE_ONLY,
        messages=[{"role": "user", "content": "test"}],
    )
    resp = gw.infer(req)
    assert resp.error is not None
    assert resp.error.error_class == PRIVACY_VIOLATION
    assert "SECRET_LOCAL_ONLY" in resp.error.message or "must never leave" in resp.error.message.lower()


def test_gateway_confidential_blocks_remote_cloud():
    """CONFIDENTIAL + remote provider preference must be blocked (§69)."""
    gw = create_gateway()
    req = AetheriusInferenceRequest(
        capability="coding",
        privacy_classification=PRIVACY_CONFIDENTIAL,
        provider_preference="openrouter",
        budget_class=FREE_ONLY,
        messages=[{"role": "user", "content": "test"}],
    )
    resp = gw.infer(req)
    assert resp.error is not None
    assert resp.error.error_class == PRIVACY_VIOLATION


def test_gateway_routing_dry_run():
    """Dry-run returns a routing decision without executing (§117)."""
    gw = create_gateway()
    req = AetheriusInferenceRequest(
        capability="coding",
        privacy_classification=PRIVACY_PROJECT,
        budget_class=FREE_ONLY,
        messages=[{"role": "user", "content": "test"}],
    )
    decision = gw.routing_dry_run(req)
    assert decision.request_id == req.request_id
    assert decision.privacy_path == "local-or-approved-cloud"
    assert decision.data_leaving_local is True  # PROJECT allows cloud


def test_gateway_local_preference():
    """Local-only provider preference works without credentials."""
    gw = create_gateway()
    req = AetheriusInferenceRequest(
        capability="coding",
        privacy_classification=PRIVACY_PROJECT,
        provider_preference="local",
        budget_class=FREE_ONLY,
        messages=[{"role": "user", "content": "hello"}],
    )
    # The gateway should not crash; it will fail because no actual provider
    # adapter is configured for "local" in the default ProviderRegistry,
    # but the privacy/budget checks should pass
    resp = gw.infer(req)
    # Either it routes to local or fails gracefully — both are acceptable
    # The key is that privacy + budget checks passed
    if resp.error:
        assert resp.error.error_class in (PROVIDER_INTERNAL, "PROVIDER_INTERNAL")
    else:
        assert resp.provider == "local" or resp.provider == ""


def test_gateway_no_model_found():
    """Request with no eligible model returns PROVIDER_INTERNAL error."""
    gw = create_gateway()
    req = AetheriusInferenceRequest(
        capability="nonexistent-capability-xyz",
        privacy_classification=PRIVACY_PROJECT,
        budget_class=FREE_ONLY,
        messages=[{"role": "user", "content": "test"}],
    )
    resp = gw.infer(req)
    assert resp.error is not None
    assert resp.finish_reason == "error"


# ---- Knowledge Fabric tests (§4, §15, §16, §17, §18) ------------------------

def test_context_broker_creation():
    """ContextBroker can be created and is healthy."""
    broker = ContextBroker()
    health = broker.health()
    assert health["broker_status"] == "HEALTHY"
    assert health["registered_adapters"] == 0
    assert health["remote_disclosure_enabled"] is False


def test_context_broker_register_adapter():
    """Adapters register safely."""
    broker = ContextBroker()

    class DummyAdapter(KnowledgeSourceAdapter):
        adapter_id = "dummy"
        platform = "local"
        source_type = SOURCE_TYPE_CONVERSATION
        state = STATE_VERIFIED

        def list_sources(self, project=None, limit=100):
            return [SourceMetadata(
                source_id="SRC-DUMMY-001",
                source_type=SOURCE_TYPE_CONVERSATION,
                platform="dummy",
                remote_id="conv-001",
                title="Test Conversation",
                privacy_class="PROJECT",
                state="VERIFIED_LIVE",
                last_checked=time.time(),
                evidence="VERIFIED_LIVE",
                adapter_id="dummy",
            )]

        def search(self, query="", project=None, limit=20):
            return self.list_sources(project=project, limit=limit)

    adapter = DummyAdapter()
    broker.register_adapter(adapter)
    assert broker.health()["registered_sources"] == 0  # not indexed yet
    sources = broker.list_sources()
    assert len(sources) == 1
    assert sources[0].source_id == "SRC-DUMMY-001"


def test_context_broker_adapter_failure_graceful():
    """Adapter failure does not crash the broker (§54: test 20)."""
    broker = ContextBroker()

    class BrokenAdapter(KnowledgeSourceAdapter):
        adapter_id = "broken"
        platform = "local"
        source_type = SOURCE_TYPE_CONVERSATION

        def list_sources(self, project=None, limit=100):
            raise RuntimeError("adapter crashed!")

        def search(self, query="", project=None, limit=20):
            raise RuntimeError("search crashed!")

    broker.register_adapter(BrokenAdapter())
    # Should not crash
    sources = broker.list_sources()
    assert len(sources) == 0


def test_context_package_privacy_filter():
    """SECRET_LOCAL_ONLY sources never reach workers with lower privacy ceiling."""
    broker = ContextBroker()

    class SecretAdapter(KnowledgeSourceAdapter):
        adapter_id = "secret_src"
        platform = "local"
        source_type = SOURCE_TYPE_CONVERSATION

        def search(self, query="", project=None, limit=20):
            return [SourceMetadata(
                source_id="SRC-SECRET-001",
                source_type=SOURCE_TYPE_CONVERSATION,
                platform="local",
                remote_id="secret-conv",
                title="Secret Conversation",
                privacy_class=PRIVACY_SECRET_LOCAL_ONLY,
                state="VERIFIED_LIVE",
                last_checked=time.time(),
                evidence="VERIFIED_LIVE",
                adapter_id="secret_src",
            )]

        def list_sources(self, project=None, limit=100):
            return self.search()

    broker.register_adapter(SecretAdapter())

    # Request with PROJECT ceiling — should NOT get SECRET_LOCAL_ONLY content
    req = ContextRequest(
        project="test",
        worker_role="coding_worker",
        privacy_ceiling=PRIVACY_PROJECT,
    )
    package = broker.request_context(req)
    assert len(package.relevant_conversations) == 0  # filtered out

    # Request with SECRET_LOCAL_ONLY ceiling — should get the content
    req2 = ContextRequest(
        project="test",
        worker_role="genesis",
        privacy_ceiling=PRIVACY_SECRET_LOCAL_ONLY,
    )
    package2 = broker.request_context(req2)
    assert len(package2.relevant_conversations) == 1


def test_context_package_role_based():
    """Different worker roles get different privacy ceilings (§17)."""
    assert ROLE_PRIVACY_CEILINGS["coding_worker"] == PRIVACY_PROJECT
    assert ROLE_PRIVACY_CEILINGS["security_reviewer"] == PRIVACY_CONFIDENTIAL
    assert ROLE_PRIVACY_CEILINGS["genesis"] == PRIVACY_SECRET_LOCAL_ONLY


def test_context_package_scoping():
    """Context package is bounded by worker privacy ceiling."""
    broker = ContextBroker()
    req = ContextRequest(
        project="test",
        worker_role="coding_worker",
        privacy_ceiling=PRIVACY_PROJECT,
    )
    # coding_worker ceiling is PROJECT, request says PROJECT → effective PROJECT
    assert req.effective_privacy_ceiling() == PRIVACY_PROJECT

    req2 = ContextRequest(
        project="test",
        worker_role="genesis",
        privacy_ceiling=PRIVACY_PROJECT,
    )
    # genesis ceiling is SECRET_LOCAL_ONLY, request says PROJECT → SECRET_LOCAL_ONLY
    assert req2.effective_privacy_ceiling() == PRIVACY_SECRET_LOCAL_ONLY


def test_source_metadata_hash():
    """Source metadata computes content hash (§9, §10)."""
    src = SourceMetadata(
        source_id="SRC-TEST-001",
        source_type=SOURCE_TYPE_CONVERSATION,
        platform="test",
        remote_id="conv-1",
    )
    assert len(src.content_hash) > 0
    d = src.to_dict()
    assert d["source_id"] == "SRC-TEST-001"
    assert "content_hash" in d


def test_provenance_record():
    """Provenance records track full derivation chain (§97, §115)."""
    ref = SourceReference(
        source_id="SRC-GITHUB-001",
        source_type=SOURCE_TYPE_REPOSITORY,
        platform="github",
        remote_id="jayprophit/Agent-Bridge",
        title="Agent-Bridge",
        content_hash="abc123",
        snippet="def hello(): pass",
        location={"line": 42, "path": "compute/ai_gateway.py"},
    )
    prov = ProvenanceRecord(
        source=ref,
        derived_kind=KIND_EVIDENCE,
        confidence=CONF_SOURCE_QUOTE,
        lifecycle=LIFE_CURRENT,
        extractor="github_adapter",
    )
    assert prov.provenance_id.startswith("prov-")
    assert prov.source.source_id == "SRC-GITHUB-001"
    assert prov.extracted_at > 0

    d = prov.to_dict()
    assert d["source"]["remote_id"] == "jayprophit/Agent-Bridge"
    assert d["derived_kind"] == KIND_EVIDENCE

    # Test supersession
    prov2 = ProvenanceRecord(
        source=ref,
        derived_kind=KIND_EVIDENCE,
        confidence=CONF_SOURCE_QUOTE,
        lifecycle=LIFE_CURRENT,
        extractor="github_adapter",
    )
    prov.supersede(prov2.provenance_id, "updated version")
    assert prov.lifecycle == LIFE_SUPERSEDED
    assert prov2.provenance_id in prov.superseded_by


# ---- GitHub Adapter tests (§19, §55) ----------------------------------------

def test_github_adapter_authenticated():
    """GitHub adapter authenticates via gh CLI and lists repos."""
    adapter = GitHubAdapter()
    if not adapter._check_auth():
        assert adapter.state == STATE_AUTH_REQUIRED
        return  # skip if not authenticated
    repos = adapter.list_sources(limit=5)
    assert isinstance(repos, list)
    assert len(repos) > 0
    assert all(r.platform == "github" for r in repos)
    assert all(r.state in ("VERIFIED", "VERIFIED_LIVE", "VERIFIED_CONFIGURED", "UNKNOWN") for r in repos)
    first = repos[0]
    meta = adapter.get_metadata(first.source_id)
    if meta:
        assert meta.title == first.title
    if adapter._auth_ok:
        assert adapter.state == "VERIFIED"


def test_github_adapter_unreachable_graceful():
    """GitHub adapter does not crash when gh CLI is unavailable."""
    adapter = GitHubAdapter()
    # Simulate unavailable by pointing to a non-existent owner
    adapter.owner = "this_user_does_not_exist_xyz12345"
    sources = adapter.list_sources(limit=5)
    assert isinstance(sources, list)


# ---- File Ingestion Adapter tests (§31, §55) --------------------------------

def test_file_ingestion_adapter():
    """File ingestion adapter indexes files with content hashing."""
    from knowledge_fabric.github_adapter import FileIngestionAdapter

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    compute_dir = os.path.join(repo_root, "compute").replace("\\", "/")
    adapter = FileIngestionAdapter(watch_dirs=[compute_dir])
    sources = adapter.index_directory(compute_dir, extensions=(".py",))
    assert len(sources) > 0
    for src in sources:
        assert len(src.content_hash) > 0
        assert src.source_type == SOURCE_TYPE_FILE
        assert src.platform == "local"
        assert src.evidence == "VERIFIED_LIVE"


def test_file_ingestion_search():
    """File ingestion adapter can search for content."""
    from knowledge_fabric.github_adapter import FileIngestionAdapter

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    compute_dir = os.path.join(repo_root, "compute").replace("\\", "/")
    adapter = FileIngestionAdapter(watch_dirs=[compute_dir])
    results = adapter.search("execution", limit=5)
    assert isinstance(results, list)


def test_image_ingestion_adapter():
    """Image ingestion adapter indexes image files in a bounded directory."""
    from knowledge_fabric.github_adapter import ImageIngestionAdapter

    adapter = ImageIngestionAdapter()
    repo_dir = "C:/Users/jpowe/Desktop/Projects/Agent-Bridge"
    if os.path.isdir(repo_dir):
        sources = adapter.index_images(repo_dir, extensions=(".png", ".jpg", ".jpeg"))
        assert isinstance(sources, list)
        for src in sources:
            assert src.source_type == SOURCE_TYPE_IMAGE
            assert len(src.content_hash) > 0
            assert src.evidence == "VERIFIED_LIVE"


# ---- Incremental sync test (§9) ---------------------------------------------

def test_incremental_sync_hash_change_detection():
    """Content hashing enables incremental sync: unchanged → skip, changed → update."""
    from knowledge_fabric.github_adapter import FileIngestionAdapter

    adapter = FileIngestionAdapter()
    # Hash a known file
    test_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "compute", "execution_target_registry.py"
    )
    test_file = test_file.replace("\\", "/")
    if os.path.isfile(test_file):
        content = adapter.read_content(test_file)
        hash1 = adapter.hash_source(test_file)
        # Re-read — hash should be the same
        hash2 = adapter.hash_source(test_file)
        assert hash1 == hash2
        assert len(hash1) > 0


# ---- Integration: AI Gateway + Knowledge Fabric ------------------------------

def test_gateway_with_context_broker():
    """Gateway can be combined with ContextBroker for scoped retrieval."""
    gw = create_gateway()
    broker = ContextBroker()

    # Register file ingestion adapter (bounded scope)
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    from knowledge_fabric.github_adapter import FileIngestionAdapter
    compute_dir = os.path.join(repo_root, "compute").replace("\\", "/")
    file_adapter = FileIngestionAdapter(watch_dirs=[compute_dir])
    broker.register_adapter(file_adapter)

    # Request context about "execution target"
    req = ContextRequest(
        project="hybrid-cloud",
        worker_role="coding_worker",
        objective="implement execution target registry",
        required_topics=["execution", "target", "registry"],
        privacy_ceiling=PRIVACY_PROJECT,
    )
    package = broker.request_context(req)
    assert package.project == "hybrid-cloud"
    assert package.privacy_ceiling == PRIVACY_PROJECT
    assert package.package_id.startswith("ctx-")
    # Should find files mentioning execution/target
    sources = file_adapter.search("execution", limit=5)
    assert isinstance(sources, list)


# ---- Runner ------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        # AI Gateway
        ("test_gateway_creation", test_gateway_creation),
        ("test_gateway_routes", test_gateway_routes),
        ("test_gateway_health", test_gateway_health),
        ("test_gateway_secret_local_only_blocks_remote",
         test_gateway_secret_local_only_blocks_remote),
        ("test_gateway_confidential_blocks_remote_cloud",
         test_gateway_confidential_blocks_remote_cloud),
        ("test_gateway_routing_dry_run", test_gateway_routing_dry_run),
        ("test_gateway_local_preference", test_gateway_local_preference),
        ("test_gateway_no_model_found", test_gateway_no_model_found),
        # Knowledge Fabric
        ("test_context_broker_creation", test_context_broker_creation),
        ("test_context_broker_register_adapter",
         test_context_broker_register_adapter),
        ("test_context_broker_adapter_failure_graceful",
         test_context_broker_adapter_failure_graceful),
        ("test_context_package_privacy_filter",
         test_context_package_privacy_filter),
        ("test_context_package_role_based",
         test_context_package_role_based),
        ("test_context_package_scoping",
         test_context_package_scoping),
        ("test_source_metadata_hash", test_source_metadata_hash),
        ("test_provenance_record", test_provenance_record),
        # GitHub Adapter
        ("test_github_adapter_authenticated", test_github_adapter_authenticated),
        ("test_github_adapter_unreachable_graceful",
         test_github_adapter_unreachable_graceful),
        # File + Image Ingestion
        ("test_file_ingestion_adapter", test_file_ingestion_adapter),
        ("test_file_ingestion_search", test_file_ingestion_search),
        ("test_image_ingestion_adapter", test_image_ingestion_adapter),
        # Incremental sync
        ("test_incremental_sync_hash_change_detection",
         test_incremental_sync_hash_change_detection),
        # Integration
        ("test_gateway_with_context_broker",
         test_gateway_with_context_broker),
    ]

    passed = 0
    failed = 0
    skipped = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {name}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    total = passed + failed
    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed, {total} total")
    print(f"{'='*60}")
    sys.exit(1 if failed else 0)
