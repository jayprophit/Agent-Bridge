"""Aetherius AI Gateway — operator-owned canonical gateway (§86, §87).

Applications should NOT directly depend on Groq, OpenRouter, HuggingFace,
Cloudflare, Ollama, LM Studio, or any single provider.

Conceptual flow:

  APPLICATION
     ↓
  GENESIS / AETHERIUS
     ↓
  AETHERIUS AI GATEWAY    ← this module
     ↓   AUTHORIZATION
     ↓   PRIVACY / POLICY
     ↓   BUDGET
     ↓   CAPABILITY ROUTER (ModelRouter v0.8)
     ↓   MODEL PLACEMENT
     ↓   PROVIDER / LOCAL TARGET

Routes:
  /aetherius/v1/inference
  /aetherius/v1/models
  /aetherius/v1/providers
  /aetherius/v1/jobs
  /aetherius/v1/agents
  /aetherius/v1/embeddings
  /aetherius/v1/health
  /aetherius/v1/routing/dry-run
"""
from __future__ import annotations

import time
import uuid
from typing import Any

from compute.cost_engine import CostEngine, default_cost_engine
from compute.execution_target_registry import (
    ExecutionTargetRegistry, seed_local_targets,
)
from compute.instance_registry import InstanceRegistry
from models.inference_contract import (
    AetheriusInferenceRequest, AetheriusInferenceResponse,
    AetheriusInferenceEvent, AetheriusRoutingDecision,
    AetheriusProviderError, AetheriusUsageRecord,
    PRIVACY_SECRET_LOCAL_ONLY, PRIVACY_CONFIDENTIAL,
    FREE_ONLY,
    BUDGET_EXCEEDED, PRIVACY_VIOLATION, PROVIDER_INTERNAL,
    AI_GATEWAY_BASE, AI_GATEWAY_PATHS,
)
from models.model_router import ModelRouter, RoutingDecision as ModelRoutingDecision
from models.model_registry import ModelRegistry
from models.provider_registry import ProviderRegistry
from models.provider_adapter import ProviderAdapter

# Map AetheriusInferenceRequest.capability to ModelRouter task types
_CAPABILITY_TO_TASK = {
    "coding": "coding",
    "review": "review",
    "vision": "vision",
    "": "",  # will be mapped below
}


class AetheriusGateway:
    """Canonical operator-owned AI gateway.

    Single entry point for all inference. Applies privacy, cost, health,
    and routing policy before dispatching to a provider/local target.
    """

    def __init__(
        self,
        provider_registry: ProviderRegistry | None = None,
        model_registry: ModelRegistry | None = None,
        execution_targets: ExecutionTargetRegistry | None = None,
        instances: InstanceRegistry | None = None,
        cost_engine: CostEngine | None = None,
    ) -> None:
        self.provider_registry = provider_registry or ProviderRegistry()
        self.model_registry = model_registry or ModelRegistry()
        self.execution_targets = execution_targets or seed_local_targets()
        self.instances = instances or InstanceRegistry()
        self.router = ModelRouter(
            self.model_registry,
            self.provider_registry,
        )
        self.cost_engine = cost_engine or default_cost_engine()
        self._started_at = time.time()
        self._request_count = 0

    def infer(self, request: AetheriusInferenceRequest) -> AetheriusInferenceResponse:
        """Process an inference request through the full gateway pipeline.

        Pipeline:
        1. Privacy enforcement (fail-closed)
        2. Budget/cost check (FREE_FIRST_STRICT)
        3. Capability routing (ModelRouter)
        4. Placement (execution target selection)
        5. Dispatch via provider adapter
        6. Usage/cost recording
        """
        self._request_count += 1

        # Step 1: Privacy enforcement — fail closed
        privacy_result = self._check_privacy(request)
        if privacy_result is not None:
            return privacy_result

        # Step 2: Budget check if a specific provider is preferred
        if request.provider_preference:
            eligible, reason = self.cost_engine.check_eligible(
                request.provider_preference, request.budget_class)
            if not eligible:
                return self._error_response(
                    request, BUDGET_EXCEEDED,
                    f"Provider {request.provider_preference} blocked by budget: {reason}")

        # Step 3: Capability routing via ModelRouter
        task_type = self._capability_to_task(request.capability)
        requirements = {
            "requires_tool_calling": request.requires_tool_calling,
            "requires_vision": request.requires_vision,
            "requires_audio": request.requires_audio_input,
            "requires_structured_output": request.requires_structured_output,
            "min_context": request.min_context_tokens,
            "max_context": request.max_context_tokens,
        }
        context = {
            "local_only": request.privacy_classification == PRIVACY_SECRET_LOCAL_ONLY,
            "preferred_provider": request.provider_preference,
        }

        # Map privacy classification to router's privacy policy
        if request.privacy_classification == PRIVACY_SECRET_LOCAL_ONLY:
            privacy_policy = "LOCAL_ONLY"
        elif request.privacy_classification == PRIVACY_CONFIDENTIAL:
            privacy_policy = "LOCAL_FIRST"
        else:
            privacy_policy = "LOCAL_FIRST"  # safe default

        route: ModelRoutingDecision = self.router.route(
            task_type=task_type,
            requirements=requirements,
            privacy_policy=privacy_policy,
            preferred_provider=request.provider_preference,
            context=context,
        )

        if not route or not route.selected_provider:
            return self._error_response(
                request, PROVIDER_INTERNAL,
                "No eligible model/provider found for this capability request")

        # Step 4: Verify cost eligibility of the selected provider
        eligible, reason = self.cost_engine.check_eligible(
            route.selected_provider, request.budget_class)
        if not eligible:
            # Try fallbacks from routing decision
            for fb in route.alternatives:
                fb_eligible, _ = self.cost_engine.check_eligible(
                    fb, request.budget_class)
                if fb_eligible:
                    route.selected_provider = fb
                    break
            else:
                return self._error_response(
                    request, BUDGET_EXCEEDED,
                    f"Selected provider {route.selected_provider} blocked: {reason}")

        # Step 5: Get the provider adapter and dispatch
        adapter = self.provider_registry.get_adapter(route.selected_provider)
        if adapter is None:
            # For local providers, the Ollama adapter might not be in the registry
            # Return routing info without dispatch
            return self._build_routing_only_response(request, route)

        provider_request = self._to_provider_request(request, route)

        try:
            result = adapter.execute(provider_request)
            usage = AetheriusUsageRecord(
                request_id=request.request_id,
                model_id=result.get("model", route.selected_model),
                provider=route.selected_provider,
                execution_target=route.selected_provider,  # provider is also the target for API
                input_tokens=result.get("usage", {}).get("prompt_tokens", 0),
                output_tokens=result.get("usage", {}).get("completion_tokens", 0),
                cost_usd=result.get("cost_usd", 0.0),
                wall_time_s=result.get("wall_time_s", 0.0),
                first_token_s=result.get("first_token_s", 0.0),
            )
            self.cost_engine.record_usage(
                route.selected_provider,
                usage.input_tokens, usage.output_tokens,
                usage.cost_usd,
                request_id=request.request_id,
                model_id=usage.model_id,
                execution_target=routing_decision_target(route),
                budget_class=request.budget_class,
            )
            routing_decision = self._build_routing_decision(request, route)
            return AetheriusInferenceResponse(
                request_id=request.request_id,
                model_id=route.selected_model,
                model_variant=route.selected_model,
                provider=route.selected_provider,
                execution_target=routing_decision_target(route),
                provider_response=result.get("content", ""),
                finish_reason=result.get("finish_reason", "stop"),
                usage=usage,
                routing=routing_decision,
                cost_usd=usage.cost_usd,
                latency_s=usage.wall_time_s,
                first_token_s=usage.first_token_s,
            )
        except Exception as e:
            err = self._normalise_error(e)
            return AetheriusInferenceResponse(
                request_id=request.request_id,
                provider=route.selected_provider,
                execution_target=routing_decision_target(route),
                error=err,
                routing=self._build_routing_decision(request, route),
                finish_reason="error",
            )

    def routing_dry_run(
        self, request: AetheriusInferenceRequest
    ) -> AetheriusRoutingDecision:
        """No-execution routing mode (§117).

        Returns a routing decision WITHOUT executing the inference workload.
        """
        privacy_path = self._privacy_path(request)
        data_leaves = request.data_leaves_local()

        task_type = self._capability_to_task(request.capability)
        route = self.router.route(
            task_type=task_type,
            requirements={},
            privacy_policy="LOCAL_ONLY" if request.privacy_classification == PRIVACY_SECRET_LOCAL_ONLY
            else "LOCAL_FIRST",
            preferred_provider=request.provider_preference,
        )

        if route and route.selected_model:
            return AetheriusRoutingDecision(
                decision_id=f"dryrun-{uuid.uuid4().hex[:12]}",
                request_id=request.request_id,
                selected_model=route.selected_model,
                selected_provider=route.selected_provider,
                selected_execution_target=routing_decision_target(route),
                reasoning=route.reasoning,
                privacy_path=privacy_path,
                data_leaving_local=data_leaves,
                cost_estimate_usd=0.0,
                fallback_chain=getattr(route, "alternatives", []),
                alternatives=getattr(route, "alternatives", []),
            )

        return AetheriusRoutingDecision(
            decision_id=f"dryrun-{uuid.uuid4().hex[:12]}",
            request_id=request.request_id,
            selected_model=request.model_preference or "",
            selected_provider=request.provider_preference or "",
            selected_execution_target="",
            reasoning="No eligible model/provider found for this capability",
            privacy_path=privacy_path,
            data_leaving_local=data_leaves,
            cost_estimate_usd=0.0,
            fallback_chain=[],
        )

    def infer_stream(
        self,
        request: AetheriusInferenceRequest,
        adapter: ProviderAdapter,
        provider_request: dict[str, Any],
        routing: AetheriusRoutingDecision,
    ):
        """Generator yielding AetheriusInferenceEvent for streaming."""
        try:
            for chunk in adapter.execute_stream(provider_request):
                yield AetheriusInferenceEvent(
                    event_id=uuid.uuid4().hex[:12],
                    request_id=request.request_id,
                    event_type="content",
                    content=chunk.get("content", ""),
                    routing=routing.to_dict(),
                )
            yield AetheriusInferenceEvent(
                event_id=uuid.uuid4().hex[:12],
                request_id=request.request_id,
                event_type="finish",
                finish_reason="stop",
            )
        except Exception as e:
            yield AetheriusInferenceEvent(
                event_id=uuid.uuid4().hex[:12],
                request_id=request.request_id,
                event_type="error",
                error=self._normalise_error(e).to_dict(),
            )

    def health(self) -> dict[str, Any]:
        """Gateway health check (§125)."""
        return {
            "status": "HEALTHY",
            "uptime_s": time.time() - self._started_at,
            "requests_served": self._request_count,
            "providers": {
                pid: {"status": p.get_auth_status() if hasattr(p, "get_auth_status") else "unknown"}
                for pid, p in self.provider_registry._providers.items()
            } if hasattr(self.provider_registry, "_providers") else {},
            "execution_targets": len(self.execution_targets),
            "models_registered": len(self.model_registry),
            "daily_cost_usd": round(self.cost_engine.total_daily_usage(), 8),
            "monthly_cost_usd": round(self.cost_engine.total_monthly_usage(), 8),
        }

    def list_models(
        self, provider: str = "", local_only: bool = False
    ) -> list[dict[str, Any]]:
        """List models from registry (§64)."""
        return self.model_registry.list_models(local_only=local_only)

    def list_providers(self) -> list[dict[str, Any]]:
        """List providers from registry (§60)."""
        return self.provider_registry.list_providers()

    @property
    def routes(self) -> dict[str, str]:
        """Canonical API routes (§86)."""
        return dict(AI_GATEWAY_PATHS)

    # -- Private helpers -------------------------------------------------------

    def _capability_to_task(self, capability: str) -> str:
        """Map Aetherius capability to ModelRouter task type."""
        mapping = {
            "coding": "coding",
            "review": "review",
            "vision": "vision",
            "reasoning": "reasoning",
            "conversation": "conversation",
            "general": "general",
        }
        return mapping.get(capability, "general")

    def _check_privacy(
        self, request: AetheriusInferenceRequest
    ) -> AetheriusInferenceResponse | None:
        """Privacy enforcement — fail closed (§69, §119).

        Returns an error response if the request violates privacy policy,
        or None if the request is allowed.
        """
        if request.privacy_classification == PRIVACY_SECRET_LOCAL_ONLY:
            # SECRET_LOCAL_ONLY: never remote
            # If a remote provider preference is specified, block
            if request.provider_preference and request.provider_preference != "local":
                return self._error_response(
                    request, PRIVACY_VIOLATION,
                    f"SECRET_LOCAL_ONLY must never be routed to remote provider "
                    f"{request.provider_preference!r}")
            # Also check: does this capability require remote?
            if request.data_leaves_local():
                return self._error_response(
                    request, PRIVACY_VIOLATION,
                    "SECRET_LOCAL_ONLY classified content must not leave local")

        if request.privacy_classification == PRIVACY_CONFIDENTIAL:
            # CONFIDENTIAL: local by default, remote only with owner authorization
            if (request.provider_preference and
                    request.provider_preference != "local"):
                # Check if owner has explicitly authorized this provider
                state = self.cost_engine.providers.get(request.provider_preference)
                if not state or not self.cost_engine.get_or_create_budget(
                        "default").owner_approved_paid:
                    return self._error_response(
                        request, PRIVACY_VIOLATION,
                        f"CONFIDENTIAL requires explicit owner authorization "
                        f"for remote provider {request.provider_preference!r}")
            pass

        return None

    def _privacy_path(self, request: AetheriusInferenceRequest) -> str:
        if request.privacy_classification == PRIVACY_SECRET_LOCAL_ONLY:
            return "local-only"
        elif request.privacy_classification == PRIVACY_CONFIDENTIAL:
            return "local-first"
        return "local-or-approved-cloud"

    def _to_provider_request(
        self, request: AetheriusInferenceRequest,
        route: ModelRoutingDecision,
    ) -> dict[str, Any]:
        return {
            "model": route.selected_model,
            "messages": request.messages,
            "tools": request.tools,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "top_p": request.top_p,
            "stream": request.streaming,
            "provider": route.selected_provider,
            "execution_target": routing_decision_target(route),
        }

    def _build_routing_decision(
        self,
        request: AetheriusInferenceRequest,
        route: ModelRoutingDecision,
    ) -> AetheriusRoutingDecision:
        return AetheriusRoutingDecision(
            decision_id=f"route-{uuid.uuid4().hex[:12]}",
            request_id=request.request_id,
            selected_model=route.selected_model,
            selected_provider=route.selected_provider,
            selected_execution_target=routing_decision_target(route),
            reasoning=route.reasoning,
            privacy_path=self._privacy_path(request),
            data_leaving_local=request.data_leaves_local(),
            cost_estimate_usd=0.0,
            fallback_chain=getattr(route, "alternatives", []),
            alternatives=getattr(route, "alternatives", []),
        )

    def _build_routing_only_response(
        self,
        request: AetheriusInferenceRequest,
        route: ModelRoutingDecision,
    ) -> AetheriusInferenceResponse:
        """Build a response with routing info when no adapter is available."""
        return AetheriusInferenceResponse(
            request_id=request.request_id,
            model_id=route.selected_model,
            provider=route.selected_provider,
            execution_target=routing_decision_target(route),
            provider_response=f"[Routed to {route.selected_provider}:{route.selected_model} — "
                              f"adapter not yet available for dispatch. "
                              f"Reasoning: {route.reasoning}]",
            finish_reason="stop",
            routing=self._build_routing_decision(request, route),
            cost_usd=0.0,
            latency_s=0.0,
        )

    def _normalise_error(self, exc: Exception) -> AetheriusProviderError:
        """Translate provider-specific exceptions into canonical error classes (§88)."""
        msg = str(exc)
        msg_lower = msg.lower()
        if "rate" in msg_lower and "limit" in msg_lower:
            return AetheriusProviderError(
                error_class="RATE_LIMITED", message=msg,
                retryable=True, retry_after_s=60.0)
        if "quota" in msg_lower:
            return AetheriusProviderError(
                error_class="QUOTA_EXHAUSTED", message=msg, retryable=True)
        if "unauthorized" in msg_lower or "401" in msg_lower:
            return AetheriusProviderError(
                error_class="AUTHENTICATION_ERROR", message=msg, retryable=False)
        if "context" in msg_lower and "length" in msg_lower:
            return AetheriusProviderError(
                error_class="CONTEXT_EXCEEDED", message=msg, retryable=False)
        if "timeout" in msg_lower:
            return AetheriusProviderError(
                error_class="TIMEOUT", message=msg, retryable=True)
        if "network" in msg_lower or "connection" in msg_lower:
            return AetheriusProviderError(
                error_class="NETWORK_FAILURE", message=msg, retryable=True)
        return AetheriusProviderError(
            error_class="PROVIDER_INTERNAL", message=msg, retryable=True)

    def _error_response(
        self,
        request: AetheriusInferenceRequest,
        error_class: str,
        message: str,
    ) -> AetheriusInferenceResponse:
        err = AetheriusProviderError(error_class=error_class, message=message)
        return AetheriusInferenceResponse(
            request_id=request.request_id,
            provider="",
            execution_target="",
            error=err,
            routing=AetheriusRoutingDecision(
                decision_id=f"err-{uuid.uuid4().hex[:12]}",
                request_id=request.request_id,
                reasoning=message,
            ),
            finish_reason="error",
        )


def routing_decision_target(route: ModelRoutingDecision) -> str:
    """Extract execution target from a ModelRouter RoutingDecision."""
    # ModelRouter doesn't track execution_target directly; use provider
    if hasattr(route, "selected_provider") and route.selected_provider:
        return f"EXEC-{route.selected_provider.upper()}-001"
    return ""


def create_gateway(
    provider_registry: ProviderRegistry | None = None,
    model_registry: ModelRegistry | None = None,
) -> AetheriusGateway:
    """Factory: create a gateway with default registries.

    Integrates:
    - ModelRouter v0.8 (existing capability router)
    - CostEngine (FREE_FIRST_STRICT)
    - ExecutionTargetRegistry (local + cloud targets)
    - InstanceRegistry (running instances)
    - Provider/model registries
    """
    return AetheriusGateway(
        provider_registry=provider_registry or ProviderRegistry(),
        model_registry=model_registry or ModelRegistry(),
        execution_targets=seed_local_targets(),
        instances=InstanceRegistry(),
        cost_engine=default_cost_engine(),
    )


__all__ = [
    "AetheriusGateway",
    "create_gateway",
    "routing_decision_target",
]
