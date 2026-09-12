"""Calibration engine (v0.7). Converts benchmark evidence into tuner overrides.

The calibration engine takes hardware-based recommendations and benchmark
observations to produce calibrated runtime configurations.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, TYPE_CHECKING

from benchmarks.benchmark_schema import (
    BenchmarkResult,
    CalibrationOverride,
    CalibrationReport,
    BENCHMARK_SCHEMA_VERSION,
    BENCHMARK_SUITE_VERSION,
)
from device.device_profile import (
    PROFILE_BALANCED, PROFILE_LOW_RESOURCE, PROFILE_PERFORMANCE,
    PROFILE_WORKSTATION, PROFILE_SERVER, PERFORMANCE_PROFILES,
)

if TYPE_CHECKING:  # lazy at runtime to avoid device<->benchmarks import cycle
    from device.runtime_tuner import TuningParameters


@dataclass
class HardwareRecommendation:
    """Initial hardware-based recommendation from RuntimeTuner."""
    performance_profile: str = PROFILE_BALANCED
    model_size_preference: str = "medium"
    quantization_preference: str = "q8"
    context_length: int = 4096
    max_parallel_workers: int = 2
    tool_concurrency: int = 2
    cache_size_mb: int = 512
    max_ram_mb: int = 0
    max_vram_mb: int = 0
    default_timeout_s: int = 30
    tool_timeout_s: int = 60
    model_timeout_s: int = 120
    
    def to_tuning_params(self) -> "TuningParameters":
        from device.runtime_tuner import TuningParameters  # lazy: breaks import cycle
        params = TuningParameters()
        params.performance_profile = self.performance_profile
        params.model_size_preference = self.model_size_preference
        params.quantization_preference = self.quantization_preference
        params.context_length = self.context_length
        params.max_parallel_workers = self.max_parallel_workers
        params.tool_concurrency = self.tool_concurrency
        params.cache_size_mb = self.cache_size_mb
        params.max_ram_mb = self.max_ram_mb
        params.max_vram_mb = self.max_vram_mb
        params.default_timeout_s = self.default_timeout_s
        params.tool_timeout_s = self.tool_timeout_s
        params.model_timeout_s = self.model_timeout_s
        return params
    
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CalibrationEngine:
    """Converts benchmark evidence into calibrated recommendations."""
    
    def __init__(self):
        self.overrides: list[CalibrationOverride] = []
    
    def calibrate(
        self,
        hardware_rec: HardwareRecommendation,
        benchmark_results: dict[str, BenchmarkResult],
        device_profile: dict[str, Any],
    ) -> CalibrationReport:
        """Generate calibrated recommendations from hardware + benchmark evidence."""
        self.overrides = []
        
        # Start with hardware recommendation
        calibrated = HardwareRecommendation()
        for field_name in hardware_rec.__dataclass_fields__:
            setattr(calibrated, field_name, getattr(hardware_rec, field_name))
        
        # Apply benchmark-based overrides
        self._apply_quantization_override(calibrated, benchmark_results)
        self._apply_model_size_override(calibrated, benchmark_results)
        self._apply_concurrency_override(calibrated, benchmark_results)
        self._apply_context_override(calibrated, benchmark_results)
        self._apply_vram_override(calibrated, benchmark_results, device_profile)
        self._apply_ram_override(calibrated, benchmark_results, device_profile)
        self._apply_timeout_override(calibrated, benchmark_results)
        
        # Build report
        report = CalibrationReport(
            device_id=device_profile.get("device_id", ""),
            hardware_profile=device_profile,
            benchmark_results=benchmark_results,
            overrides=self.overrides,
            final_recommendation=calibrated.to_dict(),
            confidence=self._calculate_overall_confidence(benchmark_results),
        )
        
        return report
    
    def _apply_quantization_override(
        self, 
        calibrated: HardwareRecommendation, 
        results: dict[str, BenchmarkResult]
    ) -> None:
        """Override quantization based on benchmark performance."""
        # Look for evidence that lower quantization works well
        q4_works = False
        q8_slow = False
        
        for model_id, result in results.items():
            if result.avg_tokens_per_second:
                # Check if we have both q4 and q8 data (by model name pattern)
                if "q4" in model_id.lower() and result.avg_tokens_per_second > 15:
                    q4_works = True
                if "q8" in model_id.lower() and result.avg_tokens_per_second < 10:
                    q8_slow = True
        
        # Also check reliability at different quantizations
        for model_id, result in results.items():
            if result.task_success_rate is not None and result.task_success_rate >= 0.8:
                if "q4" in model_id.lower():
                    q4_works = True
        
        if q4_works and calibrated.quantization_preference in ("q8", "f16", "auto"):
            self.overrides.append(CalibrationOverride(
                parameter="quantization_preference",
                hardware_recommendation=calibrated.quantization_preference,
                calibrated_recommendation="q4",
                evidence_summary="Q4 models show adequate throughput and reliability in benchmarks",
                confidence="LOW" if not q8_slow else "MEDIUM",
            ))
            calibrated.quantization_preference = "q4"
        elif q8_slow and calibrated.quantization_preference == "q8":
            self.overrides.append(CalibrationOverride(
                parameter="quantization_preference",
                hardware_recommendation="q8",
                calibrated_recommendation="q4",
                evidence_summary="Q8 models show low throughput in benchmarks",
                confidence="MEDIUM",
            ))
            calibrated.quantization_preference = "q4"
    
    def _apply_model_size_override(
        self, 
        calibrated: HardwareRecommendation, 
        results: dict[str, BenchmarkResult]
    ) -> None:
        """Override model size based on benchmark evidence."""
        # Find best performing model size class
        small_models = []  # 0.5B - 3B
        medium_models = []  # 3B - 7B
        large_models = []   # 7B+
        
        for model_id, result in results.items():
            # Extract parameter size from model_id
            size_class = self._get_size_class(model_id)
            if result.avg_tokens_per_second and result.task_success_rate is not None:
                score = result.avg_tokens_per_second * result.task_success_rate
                if size_class == "small":
                    small_models.append((model_id, score, result))
                elif size_class == "medium":
                    medium_models.append((model_id, score, result))
                else:
                    large_models.append((model_id, score, result))
        
        # If small models outperform medium, downgrade
        best_small = max(small_models, key=lambda x: x[1]) if small_models else None
        best_medium = max(medium_models, key=lambda x: x[1]) if medium_models else None
        
        if best_small and best_medium:
            if best_small[1] > best_medium[1] * 1.2:  # 20% better
                if calibrated.model_size_preference in ("medium", "large"):
                    self.overrides.append(CalibrationOverride(
                        parameter="model_size_preference",
                        hardware_recommendation=calibrated.model_size_preference,
                        calibrated_recommendation="small",
                        evidence_summary=f"Small model {best_small[0]} outperforms medium {best_medium[0]} in benchmarks",
                        confidence="LOW",
                    ))
                    calibrated.model_size_preference = "small"
        
        # If large models fail or are too slow, avoid them
        if calibrated.model_size_preference == "large":
            for model_id, result in results.items():
                if self._get_size_class(model_id) == "large":
                    if result.error_rate and result.error_rate > 0.3:
                        self.overrides.append(CalibrationOverride(
                            parameter="model_size_preference",
                            hardware_recommendation="large",
                            calibrated_recommendation="medium",
                            evidence_summary=f"Large model {model_id} has high error rate",
                            confidence="MEDIUM",
                        ))
                        calibrated.model_size_preference = "medium"
                        break
    
    def _get_size_class(self, model_id: str) -> str:
        """Extract size class from model identifier."""
        model_lower = model_id.lower()
        # Look for parameter size patterns
        import re
        for pattern in [r"(\d+\.?\d*)b", r":(\d+\.?\d*)b"]:
            match = re.search(pattern, model_lower)
            if match:
                size = float(match.group(1))
                if size < 3:
                    return "small"
                elif size < 7:
                    return "medium"
                else:
                    return "large"
        return "unknown"
    
    def _apply_concurrency_override(
        self, 
        calibrated: HardwareRecommendation, 
        results: dict[str, BenchmarkResult]
    ) -> None:
        """Override concurrency based on benchmark reliability."""
        # Check if high concurrency causes issues
        high_error_at_concurrency = False
        
        for result in results.values():
            if result.error_rate and result.error_rate > 0.2:
                high_error_at_concurrency = True
                break
            if result.tool_call_reliability is not None and result.tool_call_reliability < 0.5:
                high_error_at_concurrency = True
                break
        
        if high_error_at_concurrency and calibrated.max_parallel_workers > 1:
            self.overrides.append(CalibrationOverride(
                parameter="max_parallel_workers",
                hardware_recommendation=calibrated.max_parallel_workers,
                calibrated_recommendation=1,
                evidence_summary="Benchmarks show reliability issues at higher concurrency",
                confidence="MEDIUM",
            ))
            calibrated.max_parallel_workers = 1
            calibrated.tool_concurrency = 1
    
    def _apply_context_override(
        self, 
        calibrated: HardwareRecommendation, 
        results: dict[str, BenchmarkResult]
    ) -> None:
        """Override context length based on benchmark performance."""
        # Check if models struggle with longer contexts
        # For now, if we see timeouts or errors, reduce context
        for result in results.values():
            if result.error_rate and result.error_rate > 0.3:
                if calibrated.context_length > 4096:
                    self.overrides.append(CalibrationOverride(
                        parameter="context_length",
                        hardware_recommendation=calibrated.context_length,
                        calibrated_recommendation=4096,
                        evidence_summary="Benchmarks show errors at longer contexts",
                        confidence="LOW",
                    ))
                    calibrated.context_length = 4096
                    break
    
    def _apply_vram_override(
        self, 
        calibrated: HardwareRecommendation, 
        results: dict[str, BenchmarkResult],
        device_profile: dict[str, Any]
    ) -> None:
        """Override VRAM budget based on benchmark measurements."""
        gpu_info = device_profile.get("gpu", {})
        vram_total = gpu_info.get("vram_mb", 0)
        
        if vram_total == 0:
            return
        
        # Find peak VRAM usage in benchmarks
        peak_vram = 0
        for result in results.values():
            if result.peak_vram_mb:
                peak_vram = max(peak_vram, result.peak_vram_mb)
        
        if peak_vram > 0:
            # Set limit to peak + 20% margin, capped at 80% of total
            recommended = min(int(peak_vram * 1.2), int(vram_total * 0.8))
            if calibrated.max_vram_mb == 0 or calibrated.max_vram_mb > recommended:
                self.overrides.append(CalibrationOverride(
                    parameter="max_vram_mb",
                    hardware_recommendation=calibrated.max_vram_mb,
                    calibrated_recommendation=recommended,
                    evidence_summary=f"Measured peak VRAM {peak_vram}MB, recommending {recommended}MB limit",
                    confidence="MEDIUM",
                ))
                calibrated.max_vram_mb = recommended
    
    def _apply_ram_override(
        self, 
        calibrated: HardwareRecommendation, 
        results: dict[str, BenchmarkResult],
        device_profile: dict[str, Any]
    ) -> None:
        """Override RAM budget based on benchmark measurements."""
        memory_info = device_profile.get("memory", {})
        ram_total = memory_info.get("total_mb", 0)
        
        if ram_total == 0:
            return
        
        # Find peak RAM usage in benchmarks
        peak_ram = 0
        for result in results.values():
            if result.peak_ram_mb:
                peak_ram = max(peak_ram, result.peak_ram_mb)
        
        if peak_ram > 0:
            # Set limit to peak + 20% margin, capped at 70% of total for safety
            recommended = min(int(peak_ram * 1.2), int(ram_total * 0.7))
            if calibrated.max_ram_mb == 0 or calibrated.max_ram_mb > recommended:
                self.overrides.append(CalibrationOverride(
                    parameter="max_ram_mb",
                    hardware_recommendation=calibrated.max_ram_mb,
                    calibrated_recommendation=recommended,
                    evidence_summary=f"Measured peak RAM {peak_ram}MB, recommending {recommended}MB limit",
                    confidence="MEDIUM",
                ))
                calibrated.max_ram_mb = recommended
    
    def _apply_timeout_override(
        self, 
        calibrated: HardwareRecommendation, 
        results: dict[str, BenchmarkResult]
    ) -> None:
        """Override timeouts based on benchmark durations."""
        max_load_time = 0
        max_gen_time = 0
        
        for result in results.values():
            for obs in result.observations:
                if obs.load_duration_ms:
                    max_load_time = max(max_load_time, obs.load_duration_ms)
                if obs.generation_duration_ms:
                    max_gen_time = max(max_gen_time, obs.generation_duration_ms)
        
        # Model timeout should accommodate cold load + generation with margin
        if max_load_time > 0:
            recommended_model_timeout = int((max_load_time + max_gen_time) * 1.5 / 1000) + 30
            if calibrated.model_timeout_s < recommended_model_timeout:
                self.overrides.append(CalibrationOverride(
                    parameter="model_timeout_s",
                    hardware_recommendation=calibrated.model_timeout_s,
                    calibrated_recommendation=recommended_model_timeout,
                    evidence_summary=f"Max observed load+gen time: {max_load_time + max_gen_time}ms",
                    confidence="MEDIUM",
                ))
                calibrated.model_timeout_s = recommended_model_timeout
        
        # Tool timeout based on tool call benchmarks
        for result in results.values():
            for obs in result.observations:
                if obs.tool_call_requested and obs.total_duration_ms:
                    recommended_tool_timeout = int(obs.total_duration_ms * 1.5 / 1000) + 10
                    if calibrated.tool_timeout_s < recommended_tool_timeout:
                        self.overrides.append(CalibrationOverride(
                            parameter="tool_timeout_s",
                            hardware_recommendation=calibrated.tool_timeout_s,
                            calibrated_recommendation=recommended_tool_timeout,
                            evidence_summary=f"Tool call took {obs.total_duration_ms}ms",
                            confidence="LOW",
                        ))
                        calibrated.tool_timeout_s = recommended_tool_timeout
    
    def _calculate_overall_confidence(self, results: dict[str, BenchmarkResult]) -> str:
        """Calculate overall confidence from all benchmark results."""
        if not results:
            return "PRELIMINARY"
        
        confidences = [r.confidence for r in results.values()]
        
        if all(c == "HIGH" for c in confidences):
            return "HIGH"
        elif all(c in ("HIGH", "MEDIUM") for c in confidences):
            return "MEDIUM"
        elif all(c in ("HIGH", "MEDIUM", "LOW") for c in confidences):
            return "LOW"
        else:
            return "PRELIMINARY"


def create_hardware_recommendation_from_tuner(params) -> HardwareRecommendation:
    """Convert RuntimeTuner TuningParameters to HardwareRecommendation."""
    return HardwareRecommendation(
        performance_profile=params.performance_profile,
        model_size_preference=params.model_size_preference,
        quantization_preference=params.quantization_preference,
        context_length=params.context_length,
        max_parallel_workers=params.max_parallel_workers,
        tool_concurrency=params.tool_concurrency,
        cache_size_mb=params.cache_size_mb,
        max_ram_mb=params.max_ram_mb,
        max_vram_mb=params.max_vram_mb,
        default_timeout_s=params.default_timeout_s,
        tool_timeout_s=params.tool_timeout_s,
        model_timeout_s=params.model_timeout_s,
    )