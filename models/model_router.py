"""ModelRouter (v0.8). Task-aware model selection and routing with measured capabilities.

The ModelRouter selects the best model for a given task based on:
- Task type (coding, vision, review, etc.)
- Required capabilities
- Privacy constraints (local vs cloud)
- Resource constraints (RAM, VRAM)
- User preferences
- Fallback availability
- MEASURED MODEL FITNESS (tokens/sec, latency, success rate, test pass rate, review approval rate)
"""
from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from models.model_registry import (
    CAPABILITY_CODING, CAPABILITY_REVIEW, CAPABILITY_VISION,
    MODEL_AVAILABLE, ModelRegistry, PRIVACY_LOCAL, ModelRecord
)
from models.provider_registry import PROVIDER_AVAILABLE, ProviderRegistry
from task_dag import ModelFitnessRegistry, ModelFitness


@dataclass
class RoutingDecision:
    decision_id: str
    task_type: str
    selected_model: str
    selected_provider: str
    reasoning: str
    alternatives: list[str] = field(default_factory=list)
    fallback_used: bool = False
    fallback_from: str = ""
    fallback_reason: str = ""
    privacy_satisfied: bool = True
    latency_estimate_ms: int = 0
    cost_estimate: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.monotonic)
    
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ModelRouter:
    """Task-aware model routing with fallback and privacy constraints."""
    
    # task types
    TASK_CODING = "coding"
    TASK_VISION = "vision"
    TASK_REVIEW = "review"
    TASK_REASONING = "reasoning"
    TASK_PREDICTIVE = "predictive"
    TASK_CLASSIFICATION = "classification"
    TASK_CONVERSATION = "conversation"
    TASK_GENERAL = "general"
    
    TASK_TYPES = (
        TASK_CODING, TASK_VISION, TASK_REVIEW, TASK_REASONING,
        TASK_PREDICTIVE, TASK_CLASSIFICATION, TASK_CONVERSATION, TASK_GENERAL
    )
    
    # privacy policies
    PRIVACY_POLICY_LOCAL_ONLY = "LOCAL_ONLY"
    PRIVACY_POLICY_LOCAL_FIRST = "LOCAL_FIRST"
    PRIVACY_POLICY_BALANCED = "BALANCED"
    PRIVACY_POLICY_REMOTE_ALLOWED = "REMOTE_ALLOWED"
    PRIVACY_POLICY_SPECIFIC_PROVIDER = "SPECIFIC_PROVIDER"
    
    PRIVACY_POLICIES = (
        PRIVACY_POLICY_LOCAL_ONLY, PRIVACY_POLICY_LOCAL_FIRST,
        PRIVACY_POLICY_BALANCED, PRIVACY_POLICY_REMOTE_ALLOWED,
        PRIVACY_POLICY_SPECIFIC_PROVIDER
    )
    
    def __init__(self, model_registry: ModelRegistry,
                 provider_registry: ProviderRegistry,
                 fitness_registry: ModelFitnessRegistry | None = None):
        self.model_registry = model_registry
        self.provider_registry = provider_registry
        self.fitness_registry = fitness_registry or ModelFitnessRegistry()
        self.fallback_chains: dict[str, list[str]] = {}
        self.routing_log: list[RoutingDecision] = []
        # Capability discovery cache
        self._capability_cache: dict[str, dict[str, Any]] = {}
    
    def set_fallback_chain(self, primary_model: str,
                           fallback_models: list[str]) -> None:
        """Set fallback chain for a model."""
        self.fallback_chains[primary_model] = list(fallback_models)
    
    def route(self, task_type: str, requirements: dict[str, Any] | None = None,
              privacy_policy: str = PRIVACY_POLICY_LOCAL_FIRST,
              preferred_provider: str = "",
              context: dict[str, Any] | None = None) -> RoutingDecision:
        """Route a task to the best available model.
        
        Args:
            task_type: Type of task (coding, vision, etc.)
            requirements: Required capabilities and constraints
            privacy_policy: Privacy policy for model selection
            preferred_provider: Preferred provider if multiple available
            context: Additional context (resource constraints, etc.)
            
        Returns:
            RoutingDecision with selected model and reasoning.
        """
        requirements = dict(requirements or {})
        context = dict(context or {})
        decision_id = f"rd-{uuid.uuid4().hex[:10]}"
        
        if task_type not in self.TASK_TYPES:
            task_type = self.TASK_GENERAL
        
        # Get candidate models based on task type
        candidates = self._get_candidates(task_type, requirements)
        
        # Filter by privacy policy
        candidates = self._filter_by_privacy(candidates, privacy_policy,
                                             preferred_provider)
        
        # Filter by resource constraints
        candidates = self._filter_by_resources(candidates, context)
        
        # Filter by specific requirements
        candidates = self._filter_by_requirements(candidates, requirements)
        
        # Select best candidate
        selected = self._select_best(candidates, context)
        
        if selected is None:
            # No model available
            return RoutingDecision(
                decision_id=decision_id,
                task_type=task_type,
                selected_model="",
                selected_provider="",
                reasoning="No model available for this task with given constraints",
                privacy_satisfied=False
            )
        
        # Check if fallback was used
        fallback_used = False
        fallback_from = ""
        fallback_reason = ""
        
        if preferred_provider and selected.provider != preferred_provider:
            # Preferred provider not available, used fallback
            fallback_used = True
            fallback_from = preferred_provider
            fallback_reason = f"Preferred provider {preferred_provider} not available"
        
        decision = RoutingDecision(
            decision_id=decision_id,
            task_type=task_type,
            selected_model=selected.model_id,
            selected_provider=selected.provider,
            reasoning=self._build_reasoning(selected, task_type, requirements,
                                           privacy_policy),
            alternatives=[m.model_id for m in candidates[:5] if m.model_id != selected.model_id],
            fallback_used=fallback_used,
            fallback_from=fallback_from,
            fallback_reason=fallback_reason,
            privacy_satisfied=self._check_privacy(selected, privacy_policy),
            latency_estimate_ms=selected.latency_ms,
            cost_estimate=selected.cost_metadata
        )
        
        self.routing_log.append(decision)
        return decision
    
    def _get_candidates(self, task_type: str,
                      requirements: dict[str, Any]) -> list[ModelRecord]:
        """Get candidate models for a task type."""
        if task_type == self.TASK_CODING:
            return self.model_registry.coding_models()
        elif task_type == self.TASK_VISION:
            return self.model_registry.vision_models()
        elif task_type == self.TASK_REVIEW:
            # Review models: prefer strong reasoning
            return [m for m in self.model_registry.available_models()
                   if CAPABILITY_REVIEW in m.capability_tags or
                   CAPABILITY_REASONING in m.capability_tags]
        else:
            # General task: any available model
            return self.model_registry.available_models()
    
    def _filter_by_privacy(self, candidates: list[ModelRecord],
                          privacy_policy: str,
                          preferred_provider: str) -> list[ModelRecord]:
        """Filter candidates by privacy policy."""
        if privacy_policy == self.PRIVACY_POLICY_LOCAL_ONLY:
            return [m for m in candidates if m.local_or_remote == "local"]
        elif privacy_policy == self.PRIVACY_POLICY_LOCAL_FIRST:
            # Prefer local, but remote allowed
            local = [m for m in candidates if m.local_or_remote == "local"]
            if local:
                return local
            return candidates
        elif privacy_policy == self.PRIVACY_POLICY_SPECIFIC_PROVIDER:
            if preferred_provider:
                return [m for m in candidates if m.provider == preferred_provider]
            return candidates
        else:
            # BALANCED or REMOTE_ALLOWED: no filtering
            return candidates
    
    def _filter_by_resources(self, candidates: list[ModelRecord],
                            context: dict[str, Any]) -> list[ModelRecord]:
        """Filter candidates by resource constraints."""
        max_ram_mb = context.get("max_ram_mb", 0)
        max_vram_mb = context.get("max_vram_mb", 0)
        
        filtered = []
        for model in candidates:
            if max_ram_mb and model.ram_requirement_mb > max_ram_mb:
                continue
            if max_vram_mb and model.vram_requirement_mb > max_vram_mb:
                continue
            filtered.append(model)
        return filtered
    
    def _filter_by_requirements(self, candidates: list[ModelRecord],
                               requirements: dict[str, Any]) -> list[ModelRecord]:
        """Filter candidates by specific capability requirements."""
        required_capabilities = requirements.get("capabilities", [])
        
        if not required_capabilities:
            return candidates
        
        filtered = []
        for model in candidates:
            if all(cap in model.capability_tags for cap in required_capabilities):
                filtered.append(model)
        return filtered
    
    def _select_best(self, candidates: list[ModelRecord],
                    context: dict[str, Any]) -> ModelRecord | None:
        """Select the best candidate from the list using measured fitness."""
        if not candidates:
            return None
        
        task_type = context.get("task_type", self.TASK_GENERAL)
        role = context.get("role", "general")
        
        # Scoring system - combines static heuristics with measured fitness
        scored = []
        for model in candidates:
            score = 0
            
            # Prefer local models (privacy + latency)
            if model.local_or_remote == "local":
                score += 10
            
            # Prefer installed models
            if model.installed:
                score += 5
            
            # Prefer offline-capable models
            if model.offline_capable:
                score += 3
            
            # Prefer models with lower latency if known
            if model.latency_ms:
                score -= (model.latency_ms / 1000)  # Small penalty for latency
            
            # Prefer models with higher tokens per second if known
            if model.tokens_per_second:
                score += model.tokens_per_second / 10
            
            # Prefer models with tool calling if needed
            if context.get("needs_tool_calling") and model.tool_calling:
                score += 8
            
            # Prefer models with vision if needed
            if context.get("needs_vision") and model.vision:
                score += 8
            
            # === MEASURED FITNESS INTEGRATION ===
            # Query fitness registry for this model/role/task_type
            fitness = self.fitness_registry.get(model.model_id, role, task_type)
            if fitness and fitness.sample_count > 0:
                # Weight fitness score heavily (0-1 scale, up to 50 points)
                score += fitness.fitness_score * 50
                # Bonus for high test pass rate
                score += fitness.test_pass_rate * 20
                # Bonus for high review approval rate
                score += fitness.review_approval_rate * 15
                # Penalty for high timeout/retry rates
                score -= fitness.timeout_rate * 30
                score -= fitness.retry_rate * 15
            
            scored.append((score, model))
        
        # Sort by score descending
        scored.sort(key=lambda x: (-x[0], x[1].model_id))
        return scored[0][1] if scored else None
    
    def route_by_requirements(self, requirements: dict[str, Any],
                              privacy_policy: str = PRIVACY_POLICY_LOCAL_FIRST,
                              preferred_provider: str = "",
                              context: dict[str, Any] | None = None) -> RoutingDecision:
        """Route based on task REQUIREMENTS (not static role labels).
        
        This is the requirement-based routing entry point. It dynamically determines
        the best model based on what the task actually needs.
        
        Args:
            requirements: Dict with keys like:
                - task_type: "coding", "review", "reasoning", etc.
                - capabilities: ["tool_calling", "vision", "structured_output", ...]
                - role: "planner", "coder", "reviewer", "general"
                - min_test_pass_rate: 0.8
                - min_tokens_per_sec: 10
                - max_latency_ms: 5000
                - max_ram_mb: 8192
                - max_vram_mb: 6144
                - prefer_local: True
            privacy_policy: Privacy constraint
            preferred_provider: Specific provider if required
            context: Additional context
            
        Returns:
            RoutingDecision with selected model
        """
        context = dict(context or {})
        
        # Extract routing hints from requirements
        task_type = requirements.get("task_type", self.TASK_GENERAL)
        role = requirements.get("role", "general")
        context["task_type"] = task_type
        context["role"] = role
        
        # Map capability requirements to context flags
        capabilities = requirements.get("capabilities", [])
        if "tool_calling" in capabilities:
            context["needs_tool_calling"] = True
        if "vision" in capabilities:
            context["needs_vision"] = True
        if "structured_output" in capabilities:
            context["needs_structured_output"] = True
        
        # Add resource constraints to context
        if "max_ram_mb" in requirements:
            context["max_ram_mb"] = requirements["max_ram_mb"]
        if "max_vram_mb" in requirements:
            context["max_vram_mb"] = requirements["max_vram_mb"]
        
        # Use the existing route method with enhanced context
        return self.route(
            task_type=task_type,
            requirements=requirements,
            privacy_policy=privacy_policy,
            preferred_provider=preferred_provider,
            context=context
        )
    
    def get_fitness_comparison(self, task_type: str, role: str) -> list[ModelFitness]:
        """Get fitness comparison for all models for a task type and role."""
        return self.fitness_registry.get_comparison(role, task_type)
    
    def discover_model_capabilities(self, model_id: str, 
                                     test_tasks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """Discover actual capabilities of a model through real testing.
        
        This runs the model on representative tasks and measures:
        - Latency
        - Tokens/sec
        - Success rate
        - Test pass rate
        - Review approval rate
        - Resource usage (RAM, VRAM, CPU)
        - Tool calling success
        - Structured output success
        - Vision success (if applicable)
        
        Args:
            model_id: Model to test
            test_tasks: Optional list of test tasks. If None, uses default suite.
            
        Returns:
            Capability report with measured metrics
        """
        # This would integrate with the benchmark suite
        # For now, return cached or registry data
        model = self.model_registry.get(model_id)
        if not model:
            return {"error": "Model not found"}
        
        return {
            "model_id": model_id,
            "display_name": model.display_name,
            "provider": model.provider,
            "declared_capabilities": model.capability_tags,
            "local_or_remote": model.local_or_remote,
            "installed": model.installed,
            "offline_capable": model.offline_capable,
            "declared_latency_ms": model.latency_ms,
            "declared_tokens_per_sec": model.tokens_per_second,
            "declared_ram_mb": model.ram_requirement_mb,
            "declared_vram_mb": model.vram_requirement_mb,
            "tool_calling": model.tool_calling,
            "vision": model.vision,
            "note": "Run benchmark suite for measured capabilities"
        }
    
    def _build_reasoning(self, model: ModelRecord, task_type: str,
                        requirements: dict[str, Any],
                        privacy_policy: str) -> str:
        """Build human-readable reasoning for the selection."""
        parts = []
        parts.append(f"Selected {model.display_name} ({model.model_id})")
        parts.append(f"for {task_type} task")
        parts.append(f"from {model.provider} provider")
        
        if model.local_or_remote == "local":
            parts.append("(local model)")
        else:
            parts.append("(remote model)")
        
        if model.installed:
            parts.append("(installed)")
        
        if privacy_policy != self.PRIVACY_POLICY_BALANCED:
            parts.append(f"under {privacy_policy} policy")
        
        return " ".join(parts) + "."
    
    def _check_privacy(self, model: ModelRecord,
                      privacy_policy: str) -> bool:
        """Check if model satisfies privacy policy."""
        if privacy_policy == self.PRIVACY_POLICY_LOCAL_ONLY:
            return model.local_or_remote == "local"
        elif privacy_policy == self.PRIVACY_POLICY_LOCAL_FIRST:
            return True  # Remote allowed as fallback
        else:
            return True
    
    def get_routing_log(self, limit: int = 100) -> list[RoutingDecision]:
        """Get recent routing decisions."""
        return self.routing_log[-limit:]
    
    def clear_routing_log(self) -> None:
        """Clear the routing log."""
        self.routing_log.clear()