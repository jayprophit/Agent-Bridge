"""Tests for ModelRouter requirement-based routing and fitness integration."""
from __future__ import annotations

import pytest
from unittest.mock import Mock, MagicMock

from models.model_router import ModelRouter, RoutingDecision
from models.model_registry import ModelRegistry, ModelRecord
from models.provider_registry import ProviderRegistry
from task_dag import ModelFitnessRegistry, ModelFitness


class MockModelRecord:
    """Simple mock model record for testing."""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class TestModelRouterFitnessIntegration:
    """Tests for ModelRouter with ModelFitnessRegistry integration."""
    
    def setup_method(self):
        self.model_registry = Mock(spec=ModelRegistry)
        self.provider_registry = Mock(spec=ProviderRegistry)
        self.fitness_registry = ModelFitnessRegistry()
        self.router = ModelRouter(
            model_registry=self.model_registry,
            provider_registry=self.provider_registry,
            fitness_registry=self.fitness_registry,
        )
    
    def test_router_initializes_with_fitness_registry(self):
        assert self.router.fitness_registry is not None
        assert isinstance(self.router.fitness_registry, ModelFitnessRegistry)
    
    def test_router_initializes_without_fitness_registry_creates_default(self):
        router = ModelRouter(self.model_registry, self.provider_registry)
        assert router.fitness_registry is not None
    
    def test_route_by_requirements_returns_routing_decision(self):
        mock_model = MockModelRecord(
            model_id="test-model",
            display_name="Test Model",
            provider="ollama",
            local_or_remote="local",
            installed=True,
            offline_capable=True,
            latency_ms=100,
            tokens_per_second=50,
            tool_calling=True,
            vision=False,
            capability_tags=["coding", "tool_calling"],
            ram_requirement_mb=2048,
            vram_requirement_mb=1024,
            cost_metadata={},
        )
        
        self.model_registry.coding_models.return_value = [mock_model]
        self.model_registry.available_models.return_value = [mock_model]
        
        requirements = {
            "task_type": "coding",
            "capabilities": ["tool_calling"],
            "role": "coder",
        }
        
        decision = self.router.route_by_requirements(requirements)
        
        assert isinstance(decision, RoutingDecision)
        assert decision.selected_model == "test-model"
        assert decision.task_type == "coding"
        assert decision.privacy_satisfied is True
    
    def test_route_by_requirements_respects_resource_constraints(self):
        mock_model = MockModelRecord(
            model_id="large-model",
            display_name="Large Model",
            provider="ollama",
            local_or_remote="local",
            installed=True,
            offline_capable=True,
            latency_ms=100,
            tokens_per_second=50,
            tool_calling=True,
            vision=False,
            capability_tags=["coding"],
            ram_requirement_mb=16384,  # 16GB
            vram_requirement_mb=8192,
            cost_metadata={},
        )
        
        small_model = MockModelRecord(
            model_id="small-model",
            display_name="Small Model",
            provider="ollama",
            local_or_remote="local",
            installed=True,
            offline_capable=True,
            latency_ms=100,
            tokens_per_second=50,
            tool_calling=True,
            vision=False,
            capability_tags=["coding"],
            ram_requirement_mb=2048,  # 2GB
            vram_requirement_mb=1024,
            cost_metadata={},
        )
        
        self.model_registry.coding_models.return_value = [mock_model, small_model]
        self.model_registry.available_models.return_value = [mock_model, small_model]
        
        requirements = {
            "task_type": "coding",
            "capabilities": ["coding"],
            "role": "coder",
            "max_ram_mb": 4096,  # 4GB limit - should exclude large-model
        }
        
        decision = self.router.route_by_requirements(requirements)
        
        # Should select small-model due to RAM constraint
        assert decision.selected_model == "small-model"
    
    def test_get_fitness_comparison_returns_sorted_list(self):
        # Add fitness entries
        fitness1 = ModelFitness(
            model_id="model-a",
            role="coder",
            task_type="coding",
            fitness_score=0.9,
            test_pass_rate=0.95,
        )
        fitness2 = ModelFitness(
            model_id="model-b",
            role="coder",
            task_type="coding",
            fitness_score=0.7,
            test_pass_rate=0.80,
        )
        self.fitness_registry.update(fitness1)
        self.fitness_registry.update(fitness2)
        
        comparison = self.router.get_fitness_comparison("coding", "coder")
        
        assert len(comparison) == 2
        assert comparison[0].model_id == "model-a"  # Higher fitness first
        assert comparison[1].model_id == "model-b"
    
    def test_discover_model_capabilities_returns_report(self):
        mock_model = MockModelRecord(
            model_id="test-model",
            display_name="Test Model",
            provider="ollama",
            local_or_remote="local",
            installed=True,
            offline_capable=True,
            latency_ms=100,
            tokens_per_second=50,
            tool_calling=True,
            vision=False,
            capability_tags=["coding", "tool_calling"],
            ram_requirement_mb=2048,
            vram_requirement_mb=1024,
            cost_metadata={},
        )
        
        self.model_registry.get.return_value = mock_model
        
        report = self.router.discover_model_capabilities("test-model")
        
        assert "model_id" in report
        assert report["model_id"] == "test-model"
        assert "declared_capabilities" in report
        assert "note" in report


class TestModelFitnessRegistry:
    """Tests for ModelFitnessRegistry."""
    
    def setup_method(self):
        self.registry = ModelFitnessRegistry()
    
    def test_update_and_get_fitness(self):
        fitness = ModelFitness(
            model_id="test-model",
            role="coder",
            task_type="coding",
            fitness_score=0.85,
            test_pass_rate=0.9,
        )
        self.registry.update(fitness)
        
        retrieved = self.registry.get("test-model", "coder", "coding")
        
        assert retrieved is not None
        assert retrieved.fitness_score == 0.85
        assert retrieved.test_pass_rate == 0.9
    
    def test_get_best_for_returns_highest_fitness(self):
        fitness1 = ModelFitness(
            model_id="model-a",
            role="coder",
            task_type="coding",
            fitness_score=0.7,
        )
        fitness2 = ModelFitness(
            model_id="model-b",
            role="coder",
            task_type="coding",
            fitness_score=0.9,
        )
        self.registry.update(fitness1)
        self.registry.update(fitness2)
        
        best = self.registry.get_best_for("coder", "coding")
        
        assert best is not None
        assert best.model_id == "model-b"
        assert best.fitness_score == 0.9
    
    def test_get_comparison_returns_sorted(self):
        fitness1 = ModelFitness(
            model_id="model-a",
            role="coder",
            task_type="coding",
            fitness_score=0.7,
        )
        fitness2 = ModelFitness(
            model_id="model-b",
            role="coder",
            task_type="coding",
            fitness_score=0.9,
        )
        fitness3 = ModelFitness(
            model_id="model-c",
            role="coder",
            task_type="coding",
            fitness_score=0.5,
        )
        self.registry.update(fitness1)
        self.registry.update(fitness2)
        self.registry.update(fitness3)
        
        comparison = self.registry.get_comparison("coder", "coding")
        
        assert len(comparison) == 3
        assert comparison[0].model_id == "model-b"
        assert comparison[1].model_id == "model-a"
        assert comparison[2].model_id == "model-c"
    
    def test_get_best_for_none_when_empty(self):
        best = self.registry.get_best_for("coder", "coding")
        assert best is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])