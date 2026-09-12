"""NodeRouter (v0.7). Task delegation routing across nodes.

Routes tasks to the most appropriate node based on capabilities, trust,
privacy policies, data locality, and resource constraints.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from nodes.node_descriptor import NodeDescriptor
from nodes.node_registry import NodeRegistry
from nodes.trust_registry import TrustRegistry, OWNER_NODE, TRUSTED_NODE, LIMITED_NODE, UNTRUSTED_NODE


# Privacy policies
PRIVACY_LOCAL_ONLY = "LOCAL_ONLY"
PRIVACY_LOCAL_FIRST = "LOCAL_FIRST"
PRIVACY_BALANCED = "BALANCED"
PRIVACY_REMOTE_ALLOWED = "REMOTE_ALLOWED"
PRIVACY_SPECIFIC_PROVIDER = "SPECIFIC_PROVIDER"
PRIVACY_CURRENT_DEVICE_ONLY = "CURRENT_DEVICE_ONLY"
PRIVACY_TRUSTED_NODES = "TRUSTED_NODES"

PRIVACY_POLICIES = (
    PRIVACY_LOCAL_ONLY,
    PRIVACY_LOCAL_FIRST,
    PRIVACY_BALANCED,
    PRIVACY_REMOTE_ALLOWED,
    PRIVACY_SPECIFIC_PROVIDER,
    PRIVACY_CURRENT_DEVICE_ONLY,
    PRIVACY_TRUSTED_NODES,
)


# Data locality scopes
DATA_LOCALITY_LOCAL = "local"
DATA_LOCALITY_CAN_DELEGATE = "can_delegate"
DATA_LOCALITY_RESTRICTED = "restricted"


@dataclass
class TaskRequirements:
    """Requirements for a task that affect node routing."""
    
    # Required capabilities
    required_tools: list[str] = field(default_factory=list)
    required_tool_families: list[str] = field(default_factory=list)
    required_model_capabilities: list[str] = field(default_factory=list)
    required_agent_capabilities: list[str] = field(default_factory=list)
    required_ide_capabilities: list[str] = field(default_factory=list)
    
    # Resource requirements
    minimum_ram_mb: int = 0
    minimum_vram_mb: int = 0
    accelerator_preference: str = ""  # cuda, metal, vulkan, directml, any
    
    # Hardware capabilities
    requires_filesystem: bool = False
    requires_browser: bool = False
    requires_vision: bool = False
    requires_audio: bool = False
    requires_gpu: bool = False
    
    # Privacy and data
    privacy_policy: str = PRIVACY_LOCAL_FIRST
    data_locality: str = DATA_LOCALITY_LOCAL
    
    # Network
    network_required: bool = False
    
    # Preferences
    preferred_node_id: str = ""
    forbidden_node_ids: list[str] = field(default_factory=list)
    
    # Performance
    latency_priority: bool = False
    performance_priority: bool = False
    battery_sensitive: bool = False
    
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RoutingDecision:
    """Result of a node routing decision."""
    
    decision_id: str
    task_id: str
    
    # Selected node
    selected_node_id: str | None = None
    fallback_node_ids: list[str] = field(default_factory=list)
    
    # Selection reasoning
    reasoning: str = ""
    privacy_satisfied: bool = True
    data_locality_satisfied: bool = True
    
    # Evidence used
    capability_match_score: float = 0.0
    benchmark_evidence_used: bool = False
    trust_level_used: str = ""
    
    # Fallback info
    fallback_used: bool = False
    fallback_reason: str = ""
    
    # Limitations
    limitations: list[str] = field(default_factory=list)
    
    timestamp: float = 0.0
    
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class NodeRouter:
    """Routes tasks to appropriate nodes based on capabilities and policies."""
    
    def __init__(
        self,
        node_registry: NodeRegistry,
        trust_registry: TrustRegistry,
        local_node_id: str,
    ):
        self.node_registry = node_registry
        self.trust_registry = trust_registry
        self.local_node_id = local_node_id
    
    def route(
        self,
        task_id: str,
        requirements: TaskRequirements,
        available_nodes: list[NodeDescriptor] | None = None,
    ) -> RoutingDecision:
        """Route a task to the best available node.
        
        Args:
            task_id: Unique task identifier
            requirements: Task requirements for routing
            available_nodes: Optional pre-filtered node list
            
        Returns:
            RoutingDecision with selected node and reasoning
        """
        decision_id = f"route-{uuid.uuid4().hex[:10]}"
        
        # Get candidate nodes
        if available_nodes is None:
            candidates = self.node_registry.online_nodes()
        else:
            candidates = [n for n in available_nodes if n.online]
        
        # Apply filters in order
        
        # 1. Privacy policy filter
        candidates = self._filter_by_privacy(candidates, requirements)
        
        # 2. Trust filter
        candidates = self._filter_by_trust(candidates, requirements)
        
        # 3. Forbidden nodes
        candidates = [n for n in candidates if n.node_id not in requirements.forbidden_node_ids]
        
        # 3. Capability filter
        candidates = self._filter_by_capabilities(candidates, requirements)
        
        # 4. Resource filter
        candidates = self._filter_by_resources(candidates, requirements)
        
        # 5. Data locality filter
        candidates = self._filter_by_data_locality(candidates, requirements)
        
        # 6. Battery/thermal filter
        candidates = self._filter_by_battery_thermal(candidates, requirements)
        
        if not candidates:
            return RoutingDecision(
                decision_id=decision_id,
                task_id=task_id,
                selected_node_id=None,
                reasoning="No eligible nodes after filtering",
                privacy_satisfied=False,
                limitations=["NO_ELIGIBLE_NODE"],
                timestamp=time.time() if 'time' in globals() else 0.0,
            )
        
        # Score and rank candidates
        scored = self._score_candidates(candidates, requirements)
        
        # Select best
        best_node = scored[0][1]
        
        # Determine fallback
        fallback_nodes = [n.node_id for _, n in scored[1:3]]
        fallback_used = False
        fallback_reason = ""
        
        if requirements.preferred_node_id and best_node.node_id != requirements.preferred_node_id:
            fallback_used = True
            fallback_reason = f"Preferred node {requirements.preferred_node_id} not available or not optimal"
        
        # Build reasoning
        reasoning = self._build_reasoning(best_node, requirements, scored)
        
        return RoutingDecision(
            decision_id=decision_id,
            task_id=task_id,
            selected_node_id=best_node.node_id,
            fallback_node_ids=fallback_nodes,
            reasoning=reasoning,
            privacy_satisfied=True,
            data_locality_satisfied=self._check_data_locality(best_node, requirements),
            capability_match_score=scored[0][0],
            benchmark_evidence_used=self._has_benchmark_evidence(best_node),
            trust_level_used=self.trust_registry.get_trust_level(best_node.node_id),
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
        )
    
    def _filter_by_privacy(self, candidates: list[NodeDescriptor],
                          requirements: TaskRequirements) -> list[NodeDescriptor]:
        """Filter nodes by privacy policy."""
        policy = requirements.privacy_policy
        
        if policy == PRIVACY_LOCAL_ONLY:
            return [n for n in candidates if n.node_id == self.local_node_id]
        
        elif policy == PRIVACY_CURRENT_DEVICE_ONLY:
            return [n for n in candidates if n.node_id == self.local_node_id]
        
        elif policy == PRIVACY_TRUSTED_NODES:
            return [n for n in candidates 
                   if self.trust_registry.is_trusted(n.node_id, TRUSTED_NODE)]
        
        elif policy == PRIVACY_LOCAL_FIRST:
            # Prefer local, but allow trusted nodes as fallback
            # Return both local and trusted nodes, scoring will prefer local
            local_and_trusted = [n for n in candidates 
                                if n.node_id == self.local_node_id 
                                or self.trust_registry.is_trusted(n.node_id, TRUSTED_NODE)]
            return local_and_trusted
        
        elif policy == PRIVACY_SPECIFIC_PROVIDER:
            if requirements.preferred_node_id:
                return [n for n in candidates if n.node_id == requirements.preferred_node_id]
            return candidates
        
        # PRIVACY_BALANCED or PRIVACY_REMOTE_ALLOWED: no filtering
        return candidates
    
    def _filter_by_trust(self, candidates: list[NodeDescriptor],
                        requirements: TaskRequirements) -> list[NodeDescriptor]:
        """Filter nodes by trust requirements."""
        min_trust = requirements.required_tool_families  # Reuse field for min_trust if needed
        # Get min trust from requirements if specified
        min_trust_level = getattr(requirements, 'min_trust_level', LIMITED_NODE)
        
        return [n for n in candidates 
               if self.trust_registry.is_trusted(n.node_id, min_trust_level)]
    
    def _filter_by_capabilities(self, candidates: list[NodeDescriptor],
                               requirements: TaskRequirements) -> list[NodeDescriptor]:
        """Filter nodes by required capabilities."""
        filtered = candidates
        
        # Required tools
        if requirements.required_tools:
            filtered = [n for n in filtered 
                       if all(n.is_capable_of(t) for t in requirements.required_tools)]
        
        # Required model
        if requirements.required_model_capabilities:
            # Check if node has any of the required model capabilities
            filtered = [n for n in filtered 
                       if any(n.has_model(m) for m in requirements.required_model_capabilities)]
        
        # Required filesystem
        if requirements.requires_filesystem:
            filtered = [n for n in filtered if n.filesystem_write]
        
        # Required browser
        if requirements.requires_browser:
            filtered = [n for n in filtered if n.browser_available]
        
        # Required GPU
        if requirements.requires_gpu:
            filtered = [n for n in filtered if n.gpu_available]
        
        # Required vision
        if requirements.requires_vision:
            filtered = [n for n in filtered if "vision" in n.capabilities]
        
        return filtered
    
    def _filter_by_resources(self, candidates: list[NodeDescriptor],
                            requirements: TaskRequirements) -> list[NodeDescriptor]:
        """Filter nodes by resource requirements."""
        filtered = candidates
        
        if requirements.minimum_ram_mb > 0:
            filtered = [n for n in filtered if n.memory_mb >= requirements.minimum_ram_mb]
        
        if requirements.minimum_vram_mb > 0:
            filtered = [n for n in filtered if n.gpu_memory_mb >= requirements.minimum_vram_mb]
        
        return filtered
    
    def _filter_by_data_locality(self, candidates: list[NodeDescriptor],
                                requirements: TaskRequirements) -> list[NodeDescriptor]:
        """Filter nodes by data locality requirements."""
        if requirements.data_locality == DATA_LOCALITY_LOCAL:
            return [n for n in candidates if n.node_id == self.local_node_id]
        
        elif requirements.data_locality == DATA_LOCALITY_RESTRICTED:
            # Only nodes explicitly allowed
            if requirements.preferred_node_id:
                return [n for n in candidates if n.node_id == requirements.preferred_node_id]
            return [n for n in candidates if n.node_id == self.local_node_id]
        
        # CAN_DELEGATE: any trusted node
        return candidates
    
    def _filter_by_battery_thermal(self, candidates: list[NodeDescriptor],
                                  requirements: TaskRequirements) -> list[NodeDescriptor]:
        """Filter nodes by battery/thermal constraints."""
        filtered = candidates
        
        if requirements.battery_sensitive:
            # Prefer plugged-in or non-battery devices
            plugged_in = [n for n in filtered if not n.is_battery_powered() or n.battery_percent > 50]
            if plugged_in:
                filtered = plugged_in
        
        # Thermal: avoid degraded nodes
        filtered = [n for n in filtered if n.current_load < 0.9]
        
        return filtered
    
    def _score_candidates(self, candidates: list[NodeDescriptor],
                         requirements: TaskRequirements) -> list[tuple[float, NodeDescriptor]]:
        """Score and rank candidate nodes."""
        scored = []
        
        for node in candidates:
            score = 0.0
            
            # Prefer local node
            if node.node_id == self.local_node_id:
                score += 50
            
            # Prefer higher trust
            trust_bonus = {
                OWNER_NODE: 30,
                TRUSTED_NODE: 20,
                LIMITED_NODE: 10,
                UNTRUSTED_NODE: 0,
            }.get(node.trust_level, 0)
            score += trust_bonus
            
            # Capability match bonus
            for tool in requirements.required_tools:
                if node.is_capable_of(tool):
                    score += 10
            
            # Resource headroom
            if requirements.minimum_ram_mb > 0 and node.memory_mb > 0:
                headroom = (node.memory_mb - requirements.minimum_ram_mb) / max(node.memory_mb, 1)
                score += headroom * 10
            
            if requirements.minimum_vram_mb > 0 and node.gpu_memory_mb > 0:
                headroom = (node.gpu_memory_mb - requirements.minimum_vram_mb) / max(node.gpu_memory_mb, 1)
                score += headroom * 10
            
            # Prefer lower load
            score += (1.0 - node.current_load) * 10
            
            # Battery bonus
            if node.battery_percent > 0:
                if node.battery_percent > 50:
                    score += 5
                elif node.battery_percent < 20:
                    score -= 10
            
            # Benchmark evidence bonus
            if self._has_benchmark_evidence(node):
                score += 5
            
            scored.append((score, node))
        
        scored.sort(key=lambda x: -x[0])
        return scored
    
    def _has_benchmark_evidence(self, node: NodeDescriptor) -> bool:
        """Check if node has benchmark evidence for its models."""
        # This would check benchmark history - simplified for now
        return "benchmark_verified" in node.capabilities
    
    def _build_reasoning(self, node: NodeDescriptor,
                        requirements: TaskRequirements,
                        scored: list[tuple[float, NodeDescriptor]]) -> str:
        """Build human-readable reasoning for the selection."""
        parts = []
        parts.append(f"Selected node: {node.display_name or node.node_id} ({node.node_id})")
        
        if node.node_id == self.local_node_id:
            parts.append("(local device)")
        else:
            parts.append(f"(remote node, trust: {node.trust_level})")
        
        parts.append(f"Trust level: {node.trust_level}")
        
        if requirements.required_tools:
            tools_match = all(node.is_capable_of(t) for t in requirements.required_tools)
            parts.append(f"Required tools: {'matched' if tools_match else 'NOT matched'}")
        
        if requirements.minimum_ram_mb:
            parts.append(f"RAM: {node.memory_mb}MB (req: {requirements.minimum_ram_mb}MB)")
        
        if requirements.minimum_vram_mb:
            parts.append(f"VRAM: {node.gpu_memory_mb}MB (req: {requirements.minimum_vram_mb}MB)")
        
        parts.append(f"Load: {node.current_load:.0%}")
        parts.append(f"Score: {scored[0][0]:.1f}" if scored else "")
        
        if requirements.privacy_policy != PRIVACY_BALANCED:
            parts.append(f"Policy: {requirements.privacy_policy}")
        
        return " | ".join(parts)
    
    def _check_data_locality(self, node: NodeDescriptor,
                            requirements: TaskRequirements) -> bool:
        """Check if data locality requirements are satisfied."""
        if requirements.data_locality == DATA_LOCALITY_LOCAL:
            return node.node_id == self.local_node_id
        elif requirements.data_locality == DATA_LOCALITY_RESTRICTED:
            if requirements.preferred_node_id:
                return node.node_id == requirements.preferred_node_id
            return node.node_id == self.local_node_id
        return True
    
    def preview_route(
        self,
        task_id: str,
        requirements: TaskRequirements,
    ) -> list[tuple[float, NodeDescriptor]]:
        """Preview routing without committing - returns scored candidates."""
        candidates = self.node_registry.online_nodes()
        candidates = self._filter_by_privacy(candidates, requirements)
        candidates = self._filter_by_trust(candidates, requirements)
        candidates = [n for n in candidates if n.node_id not in requirements.forbidden_node_ids]
        candidates = self._filter_by_capabilities(candidates, requirements)
        candidates = self._filter_by_resources(candidates, requirements)
        candidates = self._filter_by_data_locality(candidates, requirements)
        candidates = self._filter_by_battery_thermal(candidates, requirements)
        return self._score_candidates(candidates, requirements)


def create_node_router(
    node_registry: NodeRegistry,
    trust_registry: TrustRegistry,
    local_node_id: str,
) -> NodeRouter:
    """Factory to create a NodeRouter."""
    return NodeRouter(node_registry, trust_registry, local_node_id)