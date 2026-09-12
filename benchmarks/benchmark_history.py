"""Benchmark history and storage (v0.7).

Provides local JSON/JSONL storage for benchmark observations with
query capabilities and version handling.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from benchmarks.benchmark_schema import (
    BenchmarkObservation,
    BenchmarkResult,
    BENCHMARK_SCHEMA_VERSION,
    BENCHMARK_SUITE_VERSION,
    CAPABILITY_EVIDENCE_LEVELS,
)


class BenchmarkStore:
    """Thread-safe local benchmark storage using JSONL format."""
    
    def __init__(self, store_path: str | None = None):
        if store_path is None:
            store_path = os.path.join(
                os.path.expanduser("~"), ".agent_bridge", "benchmarks.jsonl"
            )
        self.store_path = Path(store_path)
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._cache: list[BenchmarkObservation] = []
        self._cache_valid = False
    
    def _load_cache(self) -> None:
        """Load all observations into memory cache."""
        with self._lock:
            self._cache = []
            if self.store_path.exists():
                try:
                    with open(self.store_path, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                data = json.loads(line)
                                # Handle schema version migration if needed
                                data = self._migrate_observation(data)
                                obs = BenchmarkObservation.from_dict(data)
                                self._cache.append(obs)
                            except Exception:
                                # Skip malformed lines
                                pass
                except Exception:
                    # File read error, cache stays empty
                    pass
            self._cache_valid = True
    
    def _migrate_observation(self, data: dict[str, Any]) -> dict[str, Any]:
        """Migrate observation from older schema versions."""
        schema_ver = data.get("schema_version", "1.0.0")
        if schema_ver == BENCHMARK_SCHEMA_VERSION:
            return data
        # For now, just add missing fields with defaults
        # Future versions can add proper migration logic here
        return data
    
    def append(self, observation: BenchmarkObservation) -> None:
        """Append a new observation to the store."""
        with self._lock:
            # Ensure IDs are set
            if not observation.benchmark_id:
                observation.benchmark_id = f"bench-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}-{id(observation) & 0xFFFF:04x}"
            observation.schema_version = BENCHMARK_SCHEMA_VERSION
            observation.suite_version = BENCHMARK_SUITE_VERSION
            
            # Write to JSONL
            with open(self.store_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(observation.to_dict(), separators=(",", ":")) + "\n")
            
            # Update cache
            if self._cache_valid:
                self._cache.append(observation)
    
    def append_many(self, observations: list[BenchmarkObservation]) -> None:
        """Append multiple observations atomically."""
        with self._lock:
            for obs in observations:
                if not obs.benchmark_id:
                    obs.benchmark_id = f"bench-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}-{id(obs) & 0xFFFF:04x}"
                obs.schema_version = BENCHMARK_SCHEMA_VERSION
                obs.suite_version = BENCHMARK_SUITE_VERSION
            
            with open(self.store_path, "a", encoding="utf-8") as f:
                for obs in observations:
                    f.write(json.dumps(obs.to_dict(), separators=(",", ":")) + "\n")
            
            if self._cache_valid:
                self._cache.extend(observations)
    
    def query(
        self,
        provider_id: str | None = None,
        model_id: str | None = None,
        device_id: str | None = None,
        test_type: str | None = None,
        since: str | None = None,
        limit: int | None = None,
    ) -> list[BenchmarkObservation]:
        """Query observations with filters."""
        if not self._cache_valid:
            self._load_cache()
        
        with self._lock:
            results = self._cache
            
            if provider_id:
                results = [o for o in results if o.provider_id == provider_id]
            if model_id:
                results = [o for o in results if o.model_id == model_id]
            if device_id:
                results = [o for o in results if o.device_id == device_id]
            if test_type:
                results = [o for o in results if o.test_type == test_type]
            if since:
                results = [o for o in results if o.timestamp >= since]
            
            # Sort by timestamp descending (newest first)
            results.sort(key=lambda o: o.timestamp, reverse=True)
            
            if limit:
                results = results[:limit]
            
            return results
    
    def get_latest_for_model(self, provider_id: str, model_id: str) -> list[BenchmarkObservation]:
        """Get latest observation for each test type for a model."""
        if not self._cache_valid:
            self._load_cache()
        
        with self._lock:
            model_obs = [o for o in self._cache 
                        if o.provider_id == provider_id and o.model_id == model_id]
            
            # Group by test_type, keep latest
            by_test = {}
            for obs in model_obs:
                key = obs.test_type
                if key not in by_test or obs.timestamp > by_test[key].timestamp:
                    by_test[key] = obs
            
            return list(by_test.values())
    
    def get_all_observations(self) -> list[BenchmarkObservation]:
        """Get all observations (newest first)."""
        if not self._cache_valid:
            self._load_cache()
        with self._lock:
            results = list(self._cache)
            results.sort(key=lambda o: o.timestamp, reverse=True)
            return results
    
    def count(self, provider_id: str | None = None, model_id: str | None = None) -> int:
        """Count observations matching filters."""
        if not self._cache_valid:
            self._load_cache()
        with self._lock:
            results = self._cache
            if provider_id:
                results = [o for o in results if o.provider_id == provider_id]
            if model_id:
                results = [o for o in results if o.model_id == model_id]
            return len(results)


class BenchmarkHistory:
    """Higher-level benchmark history with aggregation capabilities."""
    
    def __init__(self, store: BenchmarkStore | None = None):
        self.store = store or BenchmarkStore()
    
    def record(self, observation: BenchmarkObservation) -> None:
        """Record a new benchmark observation."""
        self.store.append(observation)
    
    def record_many(self, observations: list[BenchmarkObservation]) -> None:
        """Record multiple observations."""
        self.store.append_many(observations)
    
    def get_model_history(
        self, 
        provider_id: str, 
        model_id: str,
        test_type: str | None = None
    ) -> list[BenchmarkObservation]:
        """Get all observations for a specific model."""
        return self.store.query(
            provider_id=provider_id,
            model_id=model_id,
            test_type=test_type,
        )
    
    def get_latest_results(self, provider_id: str, model_id: str) -> list[BenchmarkObservation]:
        """Get latest observation per test type for a model."""
        return self.store.get_latest_for_model(provider_id, model_id)
    
    def aggregate_model_results(
        self, 
        provider_id: str, 
        model_id: str
    ) -> BenchmarkResult:
        """Aggregate observations into a BenchmarkResult for a model."""
        observations = self.get_model_history(provider_id, model_id)
        
        if not observations:
            return BenchmarkResult(
                model_id=model_id,
                provider_id=provider_id,
            )
        
        result = BenchmarkResult(
            model_id=model_id,
            provider_id=provider_id,
            device_id=observations[0].device_id if observations else "",
            observations=observations,
            sample_count=len(observations),
        )
        
        # Calculate aggregated metrics
        self._calculate_aggregates(result)
        self._calculate_reliability(result)
        self._determine_confidence(result)
        
        return result
    
    def _calculate_aggregates(self, result: BenchmarkResult) -> None:
        """Calculate average performance metrics."""
        valid_tps = [o.tokens_per_second for o in result.observations 
                     if o.tokens_per_second is not None]
        valid_ttft = [o.time_to_first_token_ms for o in result.observations 
                      if o.time_to_first_token_ms is not None]
        valid_gen = [o.generation_duration_ms for o in result.observations 
                     if o.generation_duration_ms is not None]
        
        if valid_tps:
            result.avg_tokens_per_second = sum(valid_tps) / len(valid_tps)
        if valid_ttft:
            result.avg_time_to_first_token_ms = int(sum(valid_ttft) / len(valid_ttft))
        if valid_gen:
            result.avg_generation_duration_ms = int(sum(valid_gen) / len(valid_gen))
        
        # Resource profiles
        ram_vals = [o.ram_peak_mb for o in result.observations if o.ram_peak_mb]
        vram_vals = [o.vram_peak_mb for o in result.observations if o.vram_peak_mb]
        
        if ram_vals:
            result.typical_ram_mb = int(sum(ram_vals) / len(ram_vals))
            result.peak_ram_mb = max(ram_vals)
        if vram_vals:
            result.typical_vram_mb = int(sum(vram_vals) / len(vram_vals))
            result.peak_vram_mb = max(vram_vals)
    
    def _calculate_reliability(self, result: BenchmarkResult) -> None:
        """Calculate reliability metrics from observations."""
        # Tool call reliability
        tool_obs = [o for o in result.observations if o.tool_call_requested]
        if tool_obs:
            valid = sum(1 for o in tool_obs if o.tool_call_valid is True)
            result.tool_call_reliability = valid / len(tool_obs)
        
        # Structured output reliability
        struct_obs = [o for o in result.observations if o.structured_output_requested]
        if struct_obs:
            valid = sum(1 for o in struct_obs if o.structured_output_valid is True)
            result.structured_output_reliability = valid / len(struct_obs)
        
        # Task success rate
        task_obs = [o for o in result.observations if o.task_success is not None]
        if task_obs:
            success = sum(1 for o in task_obs if o.task_success)
            result.task_success_rate = success / len(task_obs)
        
        # Error rate
        error_obs = [o for o in result.observations if o.error is not None]
        if result.observations:
            result.error_rate = len(error_obs) / len(result.observations)
    
    def _determine_confidence(self, result: BenchmarkResult) -> None:
        """Determine confidence level based on sample count and consistency."""
        count = result.sample_count
        
        if count >= 10:
            result.confidence = "HIGH"
        elif count >= 5:
            result.confidence = "MEDIUM"
        elif count >= 2:
            result.confidence = "LOW"
        else:
            result.confidence = "PRELIMINARY"
        
        # Downgrade if high error rate
        if result.error_rate and result.error_rate > 0.3:
            if result.confidence == "HIGH":
                result.confidence = "MEDIUM"
            elif result.confidence == "MEDIUM":
                result.confidence = "LOW"
            elif result.confidence == "LOW":
                result.confidence = "PRELIMINARY"
    
    def get_all_models_tested(self) -> list[tuple[str, str]]:
        """Get list of (provider_id, model_id) pairs that have observations."""
        if not self.store._cache_valid:
            self.store._load_cache()
        
        with self.store._lock:
            pairs = set()
            for obs in self.store._cache:
                pairs.add((obs.provider_id, obs.model_id))
            return sorted(pairs)


class ModelBenchmarkSummary:
    """Lightweight summary of model benchmark performance for routing."""
    
    def __init__(self, history: BenchmarkHistory):
        self.history = history
        self._cache: dict[str, BenchmarkResult] = {}
    
    def get_summary(self, provider_id: str, model_id: str) -> BenchmarkResult:
        """Get or compute benchmark summary for a model."""
        key = f"{provider_id}:{model_id}"
        if key not in self._cache:
            self._cache[key] = self.history.aggregate_model_results(provider_id, model_id)
        return self._cache[key]
    
    def compare_models(
        self, 
        models: list[tuple[str, str]], 
        metric: str = "tokens_per_second"
    ) -> list[tuple[str, str, float | None]]:
        """Compare models on a specific metric."""
        results = []
        for provider_id, model_id in models:
            summary = self.get_summary(provider_id, model_id)
            value = getattr(summary, f"avg_{metric}", None)
            if value is None:
                # Try direct attribute
                value = getattr(summary, metric, None)
            results.append((provider_id, model_id, value))
        return sorted(results, key=lambda x: (x[2] is None, -(x[2] or 0)))
    
    def get_best_for_task(
        self,
        candidates: list[tuple[str, str]],
        task_type: str,
        require_tool_calling: bool = False,
        require_structured_output: bool = False,
    ) -> tuple[str, str] | None:
        """Select best model for a task based on benchmark evidence."""
        scored = []
        
        for provider_id, model_id in candidates:
            summary = self.get_summary(provider_id, model_id)
            score = 0.0
            
            # Prefer models with benchmark data
            if summary.sample_count > 0:
                score += 10
            
            # Prefer higher confidence
            confidence_bonus = {
                "HIGH": 8, "MEDIUM": 5, "LOW": 2, "PRELIMINARY": 1
            }.get(summary.confidence, 0)
            score += confidence_bonus
            
            # Task-specific scoring
            if task_type == "coding":
                # Prefer models with good tool calling and structured output
                if summary.tool_call_reliability is not None:
                    score += summary.tool_call_reliability * 15
                if summary.structured_output_reliability is not None:
                    score += summary.structured_output_reliability * 10
                if summary.avg_tokens_per_second:
                    score += min(summary.avg_tokens_per_second / 10, 10)
            
            elif task_type == "tool_use":
                if summary.tool_call_reliability is not None:
                    score += summary.tool_call_reliability * 25
                if summary.task_success_rate is not None:
                    score += summary.task_success_rate * 15
            
            elif task_type == "general":
                if summary.avg_tokens_per_second:
                    score += min(summary.avg_tokens_per_second / 5, 15)
                if summary.avg_time_to_first_token_ms:
                    score += max(0, 10 - summary.avg_time_to_first_token_ms / 100)
            
            # Requirements filtering
            if require_tool_calling and (summary.tool_call_reliability or 0) < 0.5:
                score -= 50
            if require_structured_output and (summary.structured_output_reliability or 0) < 0.5:
                score -= 50
            
            scored.append((score, provider_id, model_id, summary))
        
        if not scored:
            return None
        
        scored.sort(key=lambda x: -x[0])
        best = scored[0]
        return (best[1], best[2]) if best[0] > -10 else None