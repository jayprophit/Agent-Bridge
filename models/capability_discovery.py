"""Model Capability Discovery & Benchmarking Suite (v0.1).

Performs real capability testing on models and updates the ModelFitnessRegistry
with measured metrics for requirement-based routing.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from benchmarks.benchmark_runner import (
    BenchmarkRunner, BenchmarkTest, DEFAULT_BENCHMARK_TESTS, 
    create_ollama_provider, ResourceMonitor
)
from benchmarks.benchmark_history import BenchmarkHistory
from benchmarks.benchmark_schema import (
    BenchmarkProfile, STATE_COLD, STATE_WARM,
    TEST_SIMPLE_GENERATION, TEST_CODE_GENERATION, TEST_STRUCTURED_OUTPUT,
    TEST_TOOL_CALL, TEST_CONTEXT_TEST, TEST_VISION_PROBE, TEST_REVIEW
)
from models.model_registry import ModelRegistry
from models.provider_registry import ProviderRegistry
from models.model_router import ModelRouter
from task_dag import ModelFitnessRegistry, ModelFitness


@dataclass
class CapabilityTestSuite:
    """A suite of tests for a specific capability."""
    capability_name: str
    tests: list[BenchmarkTest]
    min_pass_rate: float = 0.7
    weight: float = 1.0  # weight in overall fitness


# Extended capability test suites
CAPABILITY_SUITES = {
    "coding": CapabilityTestSuite(
        capability_name="coding",
        tests=[
            BenchmarkTest(
                test_type=TEST_CODE_GENERATION,
                name="python_add_function",
                prompt=(
                    "Write a Python function `add_numbers(a, b)` that takes two numbers "
                    "and returns their sum. Include a docstring."
                ),
                max_tokens=256,
                timeout_s=90,
            ),
            BenchmarkTest(
                test_type=TEST_CODE_GENERATION,
                name="python_fibonacci",
                prompt=(
                    "Write a Python function `fibonacci(n)` that returns the nth Fibonacci number. "
                    "Use iteration, not recursion. Include type hints and docstring."
                ),
                max_tokens=512,
                timeout_s=90,
            ),
            BenchmarkTest(
                test_type=TEST_CODE_GENERATION,
                name="python_class",
                prompt=(
                    "Write a Python class `DataProcessor` with methods: "
                    "`load(path)`, `transform()`, `save(path)`. Include type hints."
                ),
                max_tokens=512,
                timeout_s=90,
            ),
        ],
        min_pass_rate=0.6,
        weight=2.0
    ),
    "reasoning": CapabilityTestSuite(
        capability_name="reasoning",
        tests=[
            BenchmarkTest(
                test_type=TEST_REVIEW,
                name="logic_puzzle",
                prompt=(
                    "If all Bloops are Razzies and all Razzies are Lazzies, "
                    "are all Bloops definitely Lazzies? Explain your reasoning step by step."
                ),
                max_tokens=512,
                timeout_s=90,
            ),
            BenchmarkTest(
                test_type=TEST_REVIEW,
                name="code_review",
                prompt=(
                    "Review this code for bugs and improvements:\n\n"
                    "def calculate_fibonacci(n):\n"
                    "    if n <= 0:\n"
                    "        return 0\n"
                    "    elif n == 1:\n"
                    "        return 1\n"
                    "    else:\n"
                    "        return calculate_fibonacci(n - 1) + calculate_fibonacci(n - 1)\n\n"
                    "Identify the bug and provide the corrected version."
                ),
                max_tokens=512,
                timeout_s=90,
            ),
        ],
        min_pass_rate=0.5,
        weight=1.5
    ),
    "tool_calling": CapabilityTestSuite(
        capability_name="tool_calling",
        tests=[
            BenchmarkTest(
                test_type=TEST_TOOL_CALL,
                name="search_and_list",
                prompt=(
                    "Search for information about Python's list append method, "
                    "then list the current directory contents."
                ),
                max_tokens=512,
                timeout_s=120,
                tools=[
                    {
                        "type": "function",
                        "function": {
                            "name": "search",
                            "description": "Search for information",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "query": {"type": "string"},
                                },
                                "required": ["query"],
                            },
                        },
                    },
                    {
                        "type": "function",
                        "function": {
                            "name": "filesystem.list",
                            "description": "List directory contents",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "path": {"type": "string", "default": "."},
                                },
                            },
                        },
                    },
                ],
                expect_tool_call=True,
            ),
        ],
        min_pass_rate=0.5,
        weight=1.5
    ),
    "structured_output": CapabilityTestSuite(
        capability_name="structured_output",
        tests=[
            BenchmarkTest(
                test_type=TEST_STRUCTURED_OUTPUT,
                name="json_person",
                prompt=(
                    'Return a JSON object with fields: name (string), age (integer), '
                    'city (string). Use the name "Alice", age 30, city "New York".'
                ),
                max_tokens=128,
                timeout_s=60,
                structured_output_schema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "age": {"type": "integer"},
                        "city": {"type": "string"},
                    },
                    "required": ["name", "age", "city"],
                },
                expect_structured_output=True,
            ),
        ],
        min_pass_rate=0.7,
        weight=1.0
    ),
    "simple_generation": CapabilityTestSuite(
        capability_name="simple_generation",
        tests=[
            BenchmarkTest(
                test_type=TEST_SIMPLE_GENERATION,
                name="simple_greeting",
                prompt="Say hello in one short sentence.",
                max_tokens=64,
                timeout_s=60,
            ),
            BenchmarkTest(
                test_type=TEST_CONTEXT_TEST,
                name="repeat_text",
                prompt=(
                    "I will give you a short text. Repeat it back to me.\n\n"
                    "Text: The quick brown fox jumps over the lazy dog."
                ),
                max_tokens=128,
                timeout_s=60,
            ),
        ],
        min_pass_rate=0.8,
        weight=1.0
    ),
}


class ModelCapabilityDiscoverer:
    """Discovers actual model capabilities through real benchmarking."""
    
    def __init__(
        self,
        model_registry: ModelRegistry,
        provider_registry: ProviderRegistry,
        fitness_registry: ModelFitnessRegistry,
        benchmark_history: BenchmarkHistory | None = None,
        device_id: str = "local",
    ):
        self.model_registry = model_registry
        self.provider_registry = provider_registry
        self.fitness_registry = fitness_registry
        self.benchmark_history = benchmark_history or BenchmarkHistory()
        self.device_id = device_id
        self.discovery_log: list[dict[str, Any]] = []
    
    def discover_model(
        self,
        model_id: str,
        capabilities_to_test: list[str] | None = None,
        provider_id: str = "ollama",
        endpoint: str = "http://127.0.0.1:11434",
        include_cold: bool = True,
    ) -> dict[str, Any]:
        """Run full capability discovery for a model.
        
        Args:
            model_id: Model to test
            capabilities_to_test: List of capability names to test.
                If None, tests all available suites.
            provider_id: Provider to use (ollama, lm_studio, etc.)
            endpoint: Provider endpoint
            include_cold: Whether to include cold-start measurements
            
        Returns:
            Discovery report with measured metrics and updated fitness
        """
        if capabilities_to_test is None:
            capabilities_to_test = list(CAPABILITY_SUITES.keys())
        
        provider = create_ollama_provider(endpoint)
        runner = BenchmarkRunner(
            provider=provider,
            device_id=self.device_id,
            store=self.benchmark_history,
        )
        
        model = self.model_registry.get(model_id)
        if not model:
            return {"error": f"Model {model_id} not found in registry"}
        
        report = {
            "model_id": model_id,
            "display_name": model.display_name,
            "provider": provider_id,
            "timestamp": time.time(),
            "capabilities_tested": [],
            "capability_results": {},
            "overall_fitness": None,
        }
        
        all_observations = []
        
        for cap_name in capabilities_to_test:
            if cap_name not in CAPABILITY_SUITES:
                report["capability_results"][cap_name] = {"error": "Unknown capability suite"}
                continue
            
            suite = CAPABILITY_SUITES[cap_name]
            report["capabilities_tested"].append(cap_name)
            
            # Run benchmark tests for this capability
            observations = runner.run_model_benchmarks(
                model_id=model_id,
                tests=suite.tests,
                include_cold=include_cold,
            )
            all_observations.extend(observations)
            
            # Analyze results
            cap_result = self._analyze_capability_results(
                model_id, cap_name, suite, observations
            )
            report["capability_results"][cap_name] = cap_result
        
        # Compute overall fitness
        overall = self._compute_overall_fitness(model_id, report["capability_results"])
        report["overall_fitness"] = overall
        
        # Update fitness registry
        self._update_fitness_registry(model_id, report["capability_results"], overall)
        
        # Log discovery
        self.discovery_log.append(report)
        
        return report
    
    def _analyze_capability_results(
        self,
        model_id: str,
        capability: str,
        suite: CapabilityTestSuite,
        observations: list,
    ) -> dict[str, Any]:
        """Analyze benchmark observations for a capability."""
        if not observations:
            return {"pass_rate": 0.0, "tests_run": 0, "error": "No observations"}
        
        total = len(observations)
        successful = sum(1 for o in observations if o.task_success)
        pass_rate = successful / total if total > 0 else 0.0
        
        # Calculate metrics
        latencies = [o.total_duration_ms for o in observations if o.total_duration_ms and o.task_success]
        tokens_per_sec = [o.tokens_per_second for o in observations if o.tokens_per_second and o.task_success]
        
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        avg_tokens_per_sec = sum(tokens_per_sec) / len(tokens_per_sec) if tokens_per_sec else 0
        
        # Tool call validation
        tool_call_valid = [o.tool_call_valid for o in observations if o.tool_call_requested]
        tool_call_rate = sum(1 for v in tool_call_valid if v is True) / len(tool_call_valid) if tool_call_valid else None
        
        # Structured output validation
        structured_valid = [o.structured_output_valid for o in observations if o.structured_output_requested]
        structured_rate = sum(1 for v in structured_valid if v is True) / len(structured_valid) if structured_valid else None
        
        # Quality ratings
        quality_counts = {}
        for o in observations:
            q = o.quality_rating
            quality_counts[q] = quality_counts.get(q, 0) + 1
        
        return {
            "pass_rate": pass_rate,
            "tests_run": total,
            "tests_passed": successful,
            "avg_latency_ms": avg_latency,
            "avg_tokens_per_sec": avg_tokens_per_sec,
            "tool_call_rate": tool_call_rate,
            "structured_output_rate": structured_rate,
            "quality_distribution": quality_counts,
            "meets_min_pass_rate": pass_rate >= suite.min_pass_rate,
            "suite_weight": suite.weight,
        }
    
    def _compute_overall_fitness(
        self,
        model_id: str,
        capability_results: dict[str, dict],
    ) -> ModelFitness:
        """Compute overall fitness from capability results."""
        total_weight = 0
        weighted_score = 0
        
        # Aggregate metrics
        all_latencies = []
        all_tokens_per_sec = []
        all_pass_rates = []
        all_tool_call_rates = []
        all_structured_rates = []
        
        for cap_name, result in capability_results.items():
            if "error" in result:
                continue
            
            suite = CAPABILITY_SUITES.get(cap_name)
            if not suite:
                continue
            
            weight = suite.weight
            total_weight += weight
            
            # Capability score based on pass rate
            cap_score = result.get("pass_rate", 0.0)
            weighted_score += cap_score * weight
            
            # Collect metrics
            if result.get("avg_latency_ms"):
                all_latencies.append(result["avg_latency_ms"])
            if result.get("avg_tokens_per_sec"):
                all_tokens_per_sec.append(result["avg_tokens_per_sec"])
            if result.get("pass_rate") is not None:
                all_pass_rates.append(result["pass_rate"])
            if result.get("tool_call_rate") is not None:
                all_tool_call_rates.append(result["tool_call_rate"])
            if result.get("structured_output_rate") is not None:
                all_structured_rates.append(result["structured_output_rate"])
        
        overall_score = weighted_score / total_weight if total_weight > 0 else 0.0
        
        # Estimate resource usage from model registry
        model = self.model_registry.get(model_id)
        ram_mb = model.ram_requirement_mb if model else 0
        vram_mb = model.vram_requirement_mb if model else 0
        
        fitness = ModelFitness(
            model_id=model_id,
            role="general",  # Will be updated per role
            task_type="general",
            avg_latency_ms=sum(all_latencies) / len(all_latencies) if all_latencies else 0,
            p95_latency_ms=sorted(all_latencies)[int(len(all_latencies) * 0.95)] if len(all_latencies) > 1 else (all_latencies[0] if all_latencies else 0),
            tokens_per_sec=sum(all_tokens_per_sec) / len(all_tokens_per_sec) if all_tokens_per_sec else 0,
            test_pass_rate=sum(all_pass_rates) / len(all_pass_rates) if all_pass_rates else 0,
            review_approval_rate=sum(all_structured_rates) / len(all_structured_rates) if all_structured_rates else 0,
            ram_mb=ram_mb,
            vram_mb=vram_mb,
            cpu_percent=0,  # Would need system monitoring
            success_rate=sum(all_pass_rates) / len(all_pass_rates) if all_pass_rates else 0,
            timeout_rate=0,  # Would need tracking
            retry_rate=0,  # Would need tracking
            fitness_score=overall_score,
            sample_count=sum(r.get("tests_run", 0) for r in capability_results.values()),
            last_updated=time.time(),
        )
        
        return fitness
    
    def _update_fitness_registry(
        self,
        model_id: str,
        capability_results: dict[str, dict],
        overall_fitness: ModelFitness,
    ) -> None:
        """Update fitness registry for all relevant role/task_type combinations."""
        roles = ["planner", "coder", "reviewer", "general"]
        task_types = ["coding", "review", "reasoning", "general"]
        
        for role in roles:
            for task_type in task_types:
                fitness = ModelFitness(
                    model_id=model_id,
                    role=role,
                    task_type=task_type,
                    avg_latency_ms=overall_fitness.avg_latency_ms,
                    p95_latency_ms=overall_fitness.p95_latency_ms,
                    tokens_per_sec=overall_fitness.tokens_per_sec,
                    test_pass_rate=overall_fitness.test_pass_rate,
                    review_approval_rate=overall_fitness.review_approval_rate,
                    ram_mb=overall_fitness.ram_mb,
                    vram_mb=overall_fitness.vram_mb,
                    cpu_percent=overall_fitness.cpu_percent,
                    success_rate=overall_fitness.success_rate,
                    timeout_rate=overall_fitness.timeout_rate,
                    retry_rate=overall_fitness.retry_rate,
                    fitness_score=overall_fitness.fitness_score,
                    sample_count=overall_fitness.sample_count,
                    last_updated=time.time(),
                )
                # Adjust score per role/task_type
                if role == "coder" and task_type == "coding":
                    fitness.fitness_score *= 1.1  # Boost for coding role
                elif role == "reviewer" and task_type == "review":
                    fitness.fitness_score *= 1.1
                elif role == "planner" and task_type == "reasoning":
                    fitness.fitness_score *= 1.1
                
                # Cap at 1.0
                fitness.fitness_score = min(1.0, fitness.fitness_score)
                
                self.fitness_registry.update(fitness)
    
    def discover_all_models(
        self,
        provider_id: str = "ollama",
        endpoint: str = "http://127.0.0.1:11434",
    ) -> dict[str, Any]:
        """Run capability discovery on all available models."""
        models = self.model_registry.available_models()
        results = {}
        
        for model in models:
            if not model.installed:
                continue
            
            print(f"Discovering capabilities for {model.display_name} ({model.model_id})...")
            result = self.discover_model(
                model_id=model.model_id,
                provider_id=provider_id,
                endpoint=endpoint,
            )
            results[model.model_id] = result
        
        return results
    
    def get_discovery_report(self) -> dict[str, Any]:
        """Get summary of all discoveries."""
        return {
            "total_discoveries": len(self.discovery_log),
            "models_tested": list(set(r["model_id"] for r in self.discovery_log)),
            "discoveries": self.discovery_log,
        }


def run_full_capability_discovery(
    model_registry: ModelRegistry,
    provider_registry: ProviderRegistry,
    fitness_registry: ModelFitnessRegistry,
    benchmark_history: BenchmarkHistory | None = None,
    device_id: str = "local",
) -> dict[str, Any]:
    """Convenience function to run full capability discovery on all models."""
    discoverer = ModelCapabilityDiscoverer(
        model_registry=model_registry,
        provider_registry=provider_registry,
        fitness_registry=fitness_registry,
        benchmark_history=benchmark_history,
        device_id=device_id,
    )
    return discoverer.discover_all_models()


if __name__ == "__main__":
    # Quick test
    registry = ModelRegistry()
    provider_reg = ProviderRegistry()
    fitness = ModelFitnessRegistry()
    history = BenchmarkHistory()
    
    discoverer = ModelCapabilityDiscoverer(
        model_registry=registry,
        provider_registry=provider_reg,
        fitness_registry=fitness,
        benchmark_history=history,
    )
    
    # Test with one model
    result = discoverer.discover_model("qwen2.5-coder:3b-instruct-q4_K_M")
    print(json.dumps(result, indent=2, default=str))