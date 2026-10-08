"""Tests for the hybrid cloud P0 gap-closure modules.

Covers:
- compute/execution_target_registry.py (§63)
- models/inference_contract.py (§87, §88)
- compute/cost_engine.py (§68)
- compute/instance_registry.py (§65)

Run: python -m pytest tests/test_hybrid_cloud_p0.py -v
  or: python tests/test_hybrid_cloud_p0.py
"""
import sys
import os
import time
import json
import uuid

# Ensure repo root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from compute.execution_target_registry import (
    ExecutionTarget, ExecutionTargetRegistry, AcceleratorSpec,
    PRIVACY_LOCAL_ONLY, TRUST_LOCAL,
)
from compute.instance_registry import InstanceRecord, InstanceRegistry
from models.inference_contract import (
    AetheriusInferenceRequest, AetheriusInferenceResponse,
    AetheriusToolCall, AetheriusToolResult, AetheriusUsageRecord,
    AetheriusProviderError, AetheriusModelError, AetheriusRoutingDecision,
    AetheriusInferenceEvent,
    PRIVACY_PUBLIC, PRIVACY_PROJECT, PRIVACY_PERSONAL,
    PRIVACY_CONFIDENTIAL, PRIVACY_SECRET_LOCAL_ONLY,
    FREE_ONLY, HOBBY_CREDIT_ONLY,
    AUTHENTICATION_ERROR, RATE_LIMITED, QUOTA_EXHAUSTED, TIMEOUT,
    NETWORK_FAILURE, PROVIDER_INTERNAL, MODEL_UNAVAILABLE,
    INVALID_REQUEST, SAFETY_REJECTION, UNSUPPORTED_CAPABILITY,
    BUDGET_EXCEEDED, PRIVACY_VIOLATION,
    CONTEXT_EXCEEDED,
    RETRYABLE_ERRORS, NON_RETRYABLE_ERRORS,
    is_retryable_error, is_non_retryable_error,
    AI_GATEWAY_BASE, AI_GATEWAY_PATHS,
)
from compute.cost_engine import (
    CostEngine, Budget, ProviderCostState, CostRecord,
    COST_FREE, COST_CLOUD_ZERO, COST_CLOUD_RECURRING_FREE,
    COST_HOBBY, COST_PAID, COST_UNKNOWN,
    AUTOMATICALLY_ELIGIBLE, FORBIDDEN_UNDER_FREE_FIRST,
    default_cost_engine,
)


# ---- Execution Target Registry tests ----------------------------------------

def test_execution_target_creation():
    """ExecutionTarget records can be created with all §63 fields."""
    target = ExecutionTarget(
        target_id="EXEC-LOCAL-001",
        provider="local",
        type="local_pc",
        owner="Jonathan",
        state="verified",
        architecture="x86_64",
        cpu_cores=8,
        ram_gb=16.0,
        accelerators=[AcceleratorSpec(
            vendor="nvidia", model="rtx-4070", count=1,
            total_vram_gb=12.0, compute_capability="sm_89",
        )],
        storage_gb=1000.0,
        region="local",
        startup_latency_s=0.0,
        cost_class="FREE",
        free_quota={"tokens": None},
        privacy=PRIVACY_LOCAL_ONLY,
        trust_boundary=TRUST_LOCAL,
        supported_models=["qwen3:4b", "qwen2.5-coder:14b"],
        supported_capabilities=["coding", "reasoning", "review"],
        health="HEALTHY",
        last_verified=time.time(),
    )
    assert target.target_id == "EXEC-LOCAL-001"
    d = target.to_dict()
    assert d["provider"] == "local"
    assert d["cpu_cores"] == 8
    assert d["ram_gb"] == 16.0
    assert d["cost_class"] == "FREE"


def test_execution_target_registry_register_and_lookup():
    """Registry accepts targets and prevents duplicate IDs."""
    reg = ExecutionTargetRegistry()
    t1 = ExecutionTarget(target_id="EXEC-OLLAMA-001", provider="local", type="local_ollama")
    t2 = ExecutionTarget(target_id="EXEC-OPENROUTER-001", provider="openrouter",
                         type="api_provider")
    reg.register(t1)
    reg.register(t2)
    assert len(reg) == 2

    found = reg.get("EXEC-OLLAMA-001")
    assert found.provider == "local"

    duplicate_raised = False
    try:
        dup = ExecutionTarget(target_id="EXEC-OLLAMA-001", provider="dup")
        reg.register(dup)
    except ValueError:
        duplicate_raised = True
    assert duplicate_raised


def test_execution_target_registry_by_provider():
    """Can look up targets by provider."""
    reg = ExecutionTargetRegistry()
    reg.register(ExecutionTarget(target_id="EXEC-OLLAMA-001", provider="local", type="local_ollama"))
    reg.register(ExecutionTarget(target_id="EXEC-OR-001", provider="openrouter", type="api_provider"))
    reg.register(ExecutionTarget(target_id="EXEC-OR-002", provider="openrouter", type="api_provider"))
    openrouter_targets = reg.by_provider("openrouter")
    assert len(openrouter_targets) == 2
    assert all(t.provider == "openrouter" for t in openrouter_targets)


def test_execution_target_registry_serialization():
    """Registry survives serialise/deserialise round-trip."""
    reg = ExecutionTargetRegistry()
    reg.register(ExecutionTarget(target_id="EXEC-T-01", provider="local", type="docker"))
    data = reg.to_dict()
    restored = ExecutionTargetRegistry.from_dict(data)
    assert len(restored) == 1
    assert restored.get("EXEC-T-01").provider == "local"


# ---- Inference Contract tests ------------------------------------------------

def test_inference_request_defaults():
    """Request has sensible defaults and valid privacy/budget classes."""
    req = AetheriusInferenceRequest(
        capability="coding",
        messages=[{"role": "user", "content": "hello"}],
    )
    assert req.request_id.startswith("req-")
    assert req.trace_id.startswith("trace-")
    assert req.privacy_classification == PRIVACY_PROJECT
    assert req.budget_class == FREE_ONLY
    assert req.streaming is False


def test_inference_request_privacy_enforcement():
    """SECRET_LOCAL_ONLY must be enforced at validation time."""
    req = AetheriusInferenceRequest(
        privacy_classification=PRIVACY_SECRET_LOCAL_ONLY,
        capability="review",
    )
    assert req.effective_privacy() is True
    assert req.data_leaves_local() is False

    req2 = AetheriusInferenceRequest(
        privacy_classification=PRIVACY_PROJECT,
        capability="coding",
    )
    assert req2.effective_privacy() is False
    assert req2.data_leaves_local() is True


def test_inference_request_validation():
    """Invalid privacy or budget class raises ValueError."""
    raised = False
    try:
        AetheriusInferenceRequest(privacy_classification="BOGUS")
    except ValueError:
        raised = True
    assert raised


def test_inference_request_serialization():
    """Request round-trips through to_dict/from_dict."""
    req = AetheriusInferenceRequest(
        capability="coding",
        model_preference="qwen2.5-coder",
        max_tokens=4096,
        requires_tool_calling=True,
        tools=[{"type": "function", "function": {"name": "read_file"}}],
    )
    d = req.to_dict()
    assert d["capability"] == "coding"
    assert d["max_tokens"] == 4096
    assert d["requires_tool_calling"] is True

    restored = AetheriusInferenceRequest.from_dict(d)
    assert restored.capability == "coding"
    assert restored.max_tokens == 4096


def test_usage_record_add():
    """UsageRecords can be aggregated for multi-turn conversations."""
    u1 = AetheriusUsageRecord(input_tokens=100, output_tokens=50, cost_usd=0.001)
    u2 = AetheriusUsageRecord(input_tokens=200, output_tokens=80, cost_usd=0.002)
    u1.add(u2)
    assert u1.input_tokens == 300
    assert u1.output_tokens == 130
    assert u1.total_tokens() == 430
    assert u1.cost_usd == 0.003


def test_provider_error_classification():
    """Error classes are correctly classified as retryable or not."""
    assert is_retryable_error(RATE_LIMITED) is True
    assert is_retryable_error(QUOTA_EXHAUSTED) is True
    assert is_retryable_error(TIMEOUT) is True
    assert is_retryable_error(NETWORK_FAILURE) is True
    assert is_retryable_error(PROVIDER_INTERNAL) is True
    assert is_retryable_error(MODEL_UNAVAILABLE) is True

    assert is_non_retryable_error(AUTHENTICATION_ERROR) is True
    assert is_non_retryable_error(CONTEXT_EXCEEDED) is True
    assert is_non_retryable_error(INVALID_REQUEST) is True
    assert is_non_retryable_error(SAFETY_REJECTION) is True
    assert is_non_retryable_error(BUDGET_EXCEEDED) is True
    assert is_non_retryable_error(PRIVACY_VIOLATION) is True
    assert is_non_retryable_error(UNSUPPORTED_CAPABILITY) is True


def test_provider_error_normalisation():
    """Provider errors can be normalised from raw provider output."""
    err = AetheriusProviderError(
        error_class=RATE_LIMITED,
        message="rate limit exceeded",
        provider_code="429",
        provider_message="Rate limit reached",
        retryable=True,
        retry_after_s=60.0,
    )
    d = err.to_dict()
    assert d["error_class"] == RATE_LIMITED
    assert d["retryable"] is True
    assert d["retry_after_s"] == 60.0


def test_routing_decision():
    """Routing decisions record the full selection rationale."""
    decision = AetheriusRoutingDecision(
        selected_model="qwen2.5-coder",
        selected_provider="local",
        selected_execution_target="EXEC-LOCAL-001",
        reasoning="cheapest free capable target within LOCAL_FREE policy",
        privacy_path="local-only",
        data_leaving_local=False,
        cost_estimate_usd=0.0,
        fallback_chain=["EXEC-OLLAMA-001", "EXEC-LOCAL-001"],
    )
    d = decision.to_dict()
    assert d["selected_model"] == "qwen2.5-coder"
    assert d["data_leaving_local"] is False
    assert d["fallback_chain"] == ["EXEC-OLLAMA-001", "EXEC-LOCAL-001"]


def test_inference_event_streaming():
    """Streaming events carry content/tool_call/usage/finish markers."""
    evt = AetheriusInferenceEvent(
        event_id=str(uuid.uuid4()),
        request_id="req-test",
        event_type="content",
        content="partial token",
        finish_reason="",
    )
    d = evt.to_dict()
    assert d["event_type"] == "content"
    assert d["content"] == "partial token"


def test_ai_gateway_paths():
    """Gateway path constants match §86 spec."""
    assert AI_GATEWAY_BASE == "/aetherius/v1"
    assert AI_GATEWAY_PATHS["inference"] == "/aetherius/v1/inference"
    assert AI_GATEWAY_PATHS["models"] == "/aetherius/v1/models"
    assert AI_GATEWAY_PATHS["providers"] == "/aetherius/v1/providers"
    assert AI_GATEWAY_PATHS["health"] == "/aetherius/v1/health"


def test_inference_response_serialization():
    """Full inference response serialises including nested objects."""
    req = AetheriusInferenceRequest(capability="coding")
    resp = AetheriusInferenceResponse(
        request_id=req.request_id,
        model_id="qwen3:4b",
        model_variant="q4_K_M",
        provider="local",
        execution_target="EXEC-LOCAL-001",
        provider_response="def hello(): pass",
        finish_reason="stop",
        usage=AetheriusUsageRecord(
            request_id=req.request_id,
            model_id="qwen3:4b",
            provider="local",
            execution_target="EXEC-LOCAL-001",
            input_tokens=10,
            output_tokens=5,
            cost_usd=0.0,
        ),
        cost_usd=0.0,
        latency_s=0.42,
        routing=AetheriusRoutingDecision(
            selected_model="qwen3:4b",
            selected_provider="local",
            selected_execution_target="EXEC-LOCAL-001",
        ),
    )
    d = resp.to_dict()
    assert d["model_id"] == "qwen3:4b"
    assert d["usage"]["input_tokens"] == 10
    assert d["routing"]["selected_provider"] == "local"
    assert d["error"] is None


# ---- Cost Engine tests -------------------------------------------------------

def test_cost_engine_free_first_strict():
    """FREE_FIRST_STRICT allows only local/free providers; costs $0."""
    engine = CostEngine(default_budget_class=FREE_ONLY)
    engine.register_provider(ProviderCostState(
        provider_id="local",
        cost_class=COST_FREE,
        evidence="VERIFIED_LIVE",
        daily_reset_epoch=0,
        monthly_reset_epoch=0,
    ))
    engine.register_provider(ProviderCostState(
        provider_id="openrouter",
        cost_class=COST_CLOUD_RECURRING_FREE,
        evidence="VERIFIED_CONFIGURED",
        daily_reset_epoch=0,
        monthly_reset_epoch=0,
        quota_remaining={"tokens": 1000000},
    ))

    # Local (FREE) should be eligible
    eligible, reason = engine.check_eligible("local")
    assert eligible is True

    # OpenRouter with zero-cost class should be eligible under FREE_FIRST
    eligible, reason = engine.check_eligible("openrouter")
    assert eligible is True

    # Cost should be zero
    assert engine.estimate_cost("local", 1000, 500) == 0.0
    assert engine.estimate_cost("openrouter", 1000, 500) == 0.0


def test_cost_engine_forbids_paid():
    """Under FREE_FIRST_STRICT, paid providers are blocked."""
    engine = CostEngine(default_budget_class=FREE_ONLY)
    engine.register_provider(ProviderCostState(
        provider_id="groq",
        cost_class=COST_PAID,
        evidence="VERIFIED_CONFIGURED",
        daily_reset_epoch=0,
        monthly_reset_epoch=0,
    ))
    eligible, reason = engine.check_eligible("groq")
    assert eligible is False
    assert "FREE_ONLY forbids" in reason


def test_cost_engine_unverified_fails_closed():
    """Providers without verified evidence fail closed."""
    engine = CostEngine(default_budget_class=FREE_ONLY)
    engine.register_provider(ProviderCostState(
        provider_id="mystery-free",
        cost_class=COST_CLOUD_ZERO,
        evidence="STALE_NEEDS_REVERIFY",
        daily_reset_epoch=0,
        monthly_reset_epoch=0,
    ))
    eligible, reason = engine.check_eligible("mystery-free")
    assert eligible is False
    assert "not verified" in reason.lower() or "fails closed" in reason.lower()


def test_cost_engine_quota_exhausted():
    """Quota-exhausted providers are ineligible."""
    engine = CostEngine(default_budget_class=FREE_ONLY)
    engine.register_provider(ProviderCostState(
        provider_id="hf-free",
        cost_class=COST_CLOUD_RECURRING_FREE,
        evidence="VERIFIED_LIVE",
        daily_reset_epoch=0,
        monthly_reset_epoch=0,
        quota_remaining={"tokens": 0},
    ))
    eligible, reason = engine.check_eligible("hf-free")
    assert eligible is False
    assert "quota exhausted" in reason.lower()


def test_cost_engine_budget_hard_stop():
    """Daily budget hard-stops at 100%."""
    engine = CostEngine(default_budget_class=HOBBY_CREDIT_ONLY)
    engine.register_provider(ProviderCostState(
        provider_id="groq",
        cost_class=COST_HOBBY,
        evidence="VERIFIED_CONFIGURED",
        daily_reset_epoch=0,
        monthly_reset_epoch=0,
    ))
    budget = Budget(
        daily_max_usd=1.0, monthly_max_usd=10.0,
        per_task_max_usd=0.1, per_provider_max_usd=5.0,
        owner_approved_paid=True,
    )
    engine.set_budget("default", budget)

    # Record $1 of usage
    engine.record_usage("groq", 100000, 50000, 1.0)
    eligible, reason = engine.check_eligible("groq")
    assert eligible is False
    assert "daily budget" in reason


def test_cost_engine_record_usage():
    """Usage recording updates provider state and creates records."""
    engine = CostEngine(default_budget_class=HOBBY_CREDIT_ONLY)
    engine.register_provider(ProviderCostState(
        provider_id="groq",
        cost_class=COST_HOBBY,
        evidence="VERIFIED_CONFIGURED",
        daily_reset_epoch=0,
        monthly_reset_epoch=0,
    ))
    budget = Budget(daily_max_usd=5.0, monthly_max_usd=50.0,
                    per_task_max_usd=0.5, per_provider_max_usd=20.0,
                    owner_approved_paid=True)
    engine.set_budget("default", budget)

    rec = engine.record_usage("groq", 50000, 10000, 0.35)
    assert rec.cost_usd == 0.35
    assert rec.input_tokens == 50000
    assert len(engine.records) == 1
    assert engine.providers["groq"].daily_usage_usd == 0.35


def test_cost_engine_alerts():
    """Alert thresholds fire at 50%, 80%, 95%, 100% of budget."""
    engine = CostEngine(default_budget_class=HOBBY_CREDIT_ONLY)
    engine.register_provider(ProviderCostState(
        provider_id="groq",
        cost_class=COST_HOBBY,
        evidence="VERIFIED_CONFIGURED",
        daily_reset_epoch=0,
        monthly_reset_epoch=0,
    ))
    budget = Budget(daily_max_usd=10.0, monthly_max_usd=100.0,
                    per_task_max_usd=2.0, per_provider_max_usd=50.0,
                    owner_approved_paid=True)
    engine.set_budget("default", budget)

    engine.record_usage("groq", 50000, 10000, 5.0)  # 50%
    alerts = engine.alerts()
    assert len(alerts) == 1
    assert alerts[0]["threshold"] == 0.50


def test_default_cost_engine():
    """Default engine enforces FREE_FIRST_STRICT with zero-cost budgets."""
    engine = default_cost_engine()
    assert engine.default_budget_class == FREE_ONLY
    assert "local" in engine.providers
    assert engine.providers["local"].cost_class == COST_FREE
    # No budget means no paid spending allowed
    assert engine.total_daily_usage() == 0.0


# ---- Instance Registry tests -------------------------------------------------

def test_instance_registry_crud():
    """Instances can be registered, queried, and unregistered."""
    reg = InstanceRegistry()
    inst = InstanceRecord(
        instance_id="inst-001",
        model_id="qwen3:4b",
        execution_target="EXEC-LOCAL-001",
        provider="local",
        endpoint="http://localhost:11434/v1",
        health="HEALTHY",
        ram_used_mb=2048.0,
        vram_used_mb=1536.0,
    )
    reg.register(inst)
    assert len(reg) == 1

    found = reg.get("inst-001")
    assert found.model_id == "qwen3:4b"
    assert found.health == "HEALTHY"

    # Register a duplicate should fail
    dup = InstanceRecord(instance_id="inst-001", model_id="other")
    duplicate_raised = False
    try:
        reg.register(dup)
    except ValueError:
        duplicate_raised = True
    assert duplicate_raised


def test_instance_registry_queries():
    """Can query instances by model, target, availability."""
    reg = InstanceRegistry()
    reg.register(InstanceRecord(instance_id="i1", model_id="qwen2.5-coder",
                              execution_target="EXEC-LOCAL-001", health="HEALTHY"))
    reg.register(InstanceRecord(instance_id="i2", model_id="qwen2.5-coder",
                              execution_target="EXEC-OR-001", health="HEALTHY"))
    reg.register(InstanceRecord(instance_id="i3", model_id="llama3",
                              execution_target="EXEC-LOCAL-001", health="DEGRADED"))

    coder_instances = reg.by_model("qwen2.5-coder")
    assert len(coder_instances) == 2

    local_instances = reg.by_target("EXEC-LOCAL-001")
    assert len(local_instances) == 2

    available = reg.available()
    # i1 and i2 are HEALTHY and fresh; i3 is DEGRADED but not stale
    # available() returns HEALTHY or DEGRADED that aren't stale
    assert len(available) == 3


def test_instance_registry_gc_stale():
    """Stale instances (no heartbeat) are garbaged by gc_stale."""
    reg = InstanceRegistry()
    reg.register(InstanceRecord(
        instance_id="fresh",
        last_heartbeat=time.time(),
        health="HEALTHY",
    ))
    reg.register(InstanceRecord(
        instance_id="stale",
        last_heartbeat=time.time() - 120,  # 2 min ago
        health="HEALTHY",
    ))
    gc_result = reg.gc_stale(heartbeat_timeout_s=60.0)
    assert "stale" in gc_result
    assert "fresh" not in gc_result
    assert len(reg) == 1


def test_instance_heartbeat_and_health():
    """Heartbeat updates timestamp; health updates are trackable."""
    reg = InstanceRegistry()
    reg.register(InstanceRecord(
        instance_id="i1",
        model_id="qwen3",
        last_heartbeat=time.time() - 10,
        health="DEGRADED",
    ))
    reg.heartbeat("i1")
    reg.update_health("i1", "HEALTHY")
    rec = reg.get("i1")
    assert rec.health == "HEALTHY"
    assert not rec.is_stale(60.0)


def test_instance_serialization():
    """Instances survive serialise/deserialise."""
    reg = InstanceRegistry()
    reg.register(InstanceRecord(
        instance_id="i1",
        model_id="qwen3",
        execution_target="EXEC-LOCAL-001",
        cost_accumulated_usd=0.0015,
    ))
    data = reg.to_dict()
    assert "i1" in data
    assert data["i1"]["model_id"] == "qwen3"
    assert data["i1"]["cost_accumulated_usd"] == 0.0015


# ---- Integration tests -------------------------------------------------------

def test_full_local_routing_flow():
    """End-to-end: request → eligibility → response flow for local routing."""
    # 1. Create an execution target for local Ollama
    reg = ExecutionTargetRegistry()
    local_target = ExecutionTarget(
        target_id="EXEC-OLLAMA-LOCAL",
        provider="local",
        type="local_ollama",
        architecture="x86_64",
        ram_gb=16.0,
        accelerators=[AcceleratorSpec(
            vendor="nvidia", model="gtx-1050-ti", count=1,
            total_vram_gb=4.0, compute_capability="sm_61",
        )],
        cost_class="FREE",
        free_quota={"tokens": None},
        privacy=PRIVACY_LOCAL_ONLY,
        trust_boundary=TRUST_LOCAL,
        health="HEALTHY",
        state="verified",
    )
    reg.register(local_target)

    # 2. Create cost engine with FREE_FIRST_STRICT
    engine = default_cost_engine()

    # 3. Create request with FREE_ONLY budget
    req = AetheriusInferenceRequest(
        capability="coding",
        privacy_classification=PRIVACY_PROJECT,
        budget_class=FREE_ONLY,
        messages=[{"role": "user", "content": "Write a hello world function"}],
        requires_tool_calling=True,
        max_tokens=2048,
    )

    # 4. Check eligibility
    eligible, reason = engine.check_eligible("local")
    assert eligible is True

    # 5. Record zero cost (local is free)
    cost_rec = engine.record_usage("local", 50, 30, 0.0,
                                    request_id=req.request_id,
                                    model_id="qwen3:4b",
                                    execution_target="EXEC-OLLAMA-LOCAL",
                                    budget_class=FREE_ONLY)
    assert cost_rec.cost_usd == 0.0

    # 6. Build response
    response = AetheriusInferenceResponse(
        request_id=req.request_id,
        model_id="qwen3:4b",
        provider="local",
        execution_target="EXEC-OLLAMA-LOCAL",
        provider_response="def hello():\n    print('Hello, World!')",
        finish_reason="stop",
        usage=AetheriusUsageRecord(
            request_id=req.request_id,
            model_id="qwen3:4b",
            provider="local",
            execution_target="EXEC-OLLAMA-LOCAL",
            input_tokens=50,
            output_tokens=30,
            cost_usd=0.0,
        ),
        routing=AetheriusRoutingDecision(
            selected_model="qwen3:4b",
            selected_provider="local",
            selected_execution_target="EXEC-OLLAMA-LOCAL",
            reasoning="FREE_ONLY: cheapest free capable target",
            privacy_path="local",
            data_leaving_local=False,
            cost_estimate_usd=0.0,
        ),
        cost_usd=0.0,
        latency_s=0.42,
    )

    d = response.to_dict()
    assert d["provider"] == "local"
    assert d["routing"]["data_leaving_local"] is False
    assert d["cost_usd"] == 0.0


# ---- Runner ------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        # Execution target registry
        ("test_execution_target_creation", test_execution_target_creation),
        ("test_execution_target_registry_register_and_lookup",
         test_execution_target_registry_register_and_lookup),
        ("test_execution_target_registry_by_provider",
         test_execution_target_registry_by_provider),
        ("test_execution_target_registry_serialization",
         test_execution_target_registry_serialization),
        # Inference contract
        ("test_inference_request_defaults", test_inference_request_defaults),
        ("test_inference_request_privacy_enforcement",
         test_inference_request_privacy_enforcement),
        ("test_inference_request_validation", test_inference_request_validation),
        ("test_inference_request_serialization", test_inference_request_serialization),
        ("test_usage_record_add", test_usage_record_add),
        ("test_provider_error_classification", test_provider_error_classification),
        ("test_provider_error_normalisation", test_provider_error_normalisation),
        ("test_routing_decision", test_routing_decision),
        ("test_inference_event_streaming", test_inference_event_streaming),
        ("test_ai_gateway_paths", test_ai_gateway_paths),
        ("test_inference_response_serialization",
         test_inference_response_serialization),
        # Cost engine
        ("test_cost_engine_free_first_strict", test_cost_engine_free_first_strict),
        ("test_cost_engine_forbids_paid", test_cost_engine_forbids_paid),
        ("test_cost_engine_unverified_fails_closed",
         test_cost_engine_unverified_fails_closed),
        ("test_cost_engine_quota_exhausted", test_cost_engine_quota_exhausted),
        ("test_cost_engine_budget_hard_stop", test_cost_engine_budget_hard_stop),
        ("test_cost_engine_record_usage", test_cost_engine_record_usage),
        ("test_cost_engine_alerts", test_cost_engine_alerts),
        ("test_default_cost_engine", test_default_cost_engine),
        # Instance registry
        ("test_instance_registry_crud", test_instance_registry_crud),
        ("test_instance_registry_queries", test_instance_registry_queries),
        ("test_instance_registry_gc_stale", test_instance_registry_gc_stale),
        ("test_instance_heartbeat_and_health", test_instance_heartbeat_and_health),
        ("test_instance_serialization", test_instance_serialization),
        # Integration
        ("test_full_local_routing_flow", test_full_local_routing_flow),
    ]

    passed = 0
    failed = 0
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

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed, {len(tests)} total")
    print(f"{'='*60}")
    sys.exit(1 if failed else 0)
