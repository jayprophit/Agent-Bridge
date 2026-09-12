"""ModelRouter (v0.7). Task-aware model selection and routing.

The ModelRouter selects the best model for a given task based on:
- Task type (coding, vision, review, etc.)
- Required capabilities
- Privacy constraints (local vs cloud)
- Resource constraints (RAM, VRAM)
- User preferences
- Fallback availability
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
                 provider_registry: ProviderRegistry):
        self.model_registry = model_registry
        self.provider_registry = provider_registry
        self.fallback_chains: dict[str, list[str]] = {}
        self.routing_log: list[RoutingDecision] = []
    
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
        """Select the best candidate from the list."""
        if not candidates:
            return None
        
        # Scoring system
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
            
            scored.append((score, model))
        
        # Sort by score descending
        scored.sort(key=lambda x: (-x[0], x[1].model_id))
        return scored[0][1] if scored else None
    
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