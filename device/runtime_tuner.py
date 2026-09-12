"""RuntimeTuner (v0.7). Automatic performance configuration.

RuntimeTuner automatically configures runtime parameters based on:
- Hardware capabilities
- Resource constraints
- Battery/power state
- Thermal conditions
- User preferences
- Benchmark calibration evidence

It selects appropriate performance profiles and tunes parameters for optimal performance.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any

from device.device_profile import (
    DEVICE_CLASS_DESKTOP, DEVICE_CLASS_LAPTOP, DEVICE_CLASS_PHONE,
    DEVICE_CLASS_SERVER, DEVICE_CLASS_SMARTWATCH, DEVICE_CLASS_TABLET,
    PERFORMANCE_PROFILES, PROFILE_BALANCED, PROFILE_LOW_RESOURCE,
    PROFILE_MOBILE, PROFILE_MOBILE_POWER_SAVE, PROFILE_PERFORMANCE,
    PROFILE_SERVER, PROFILE_ULTRA_LOW_RESOURCE, PROFILE_WORKSTATION
)
from device.device_profiler import DeviceProfiler
from device.hardware_profiler import HardwareProfiler

# Benchmark integration (imported lazily inside tune_with_calibration).
# A module-level import here creates a device<->benchmarks import cycle
# (benchmarks.calibration_engine needs device.device_profile), which left
# BENCHMARKS_AVAILABLE=False depending on import order and silently disabled
# all calibration. Never import benchmarks at module top level here.
BENCHMARKS_AVAILABLE = True


@dataclass
class TuningParameters:
    """Runtime tuning parameters."""
    performance_profile: str = PROFILE_BALANCED
    
    # Model parameters
    model_size_preference: str = "balanced"  # "tiny", "small", "medium", "large", "auto"
    quantization_preference: str = "auto"  # "q4", "q8", "f16", "auto"
    context_length: int = 4096
    batch_size: int = 1
    
    # Execution parameters
    max_parallel_workers: int = 1
    tool_concurrency: int = 1
    cache_size_mb: int = 512
    
    # Resource limits
    max_ram_mb: int = 0  # 0 = no limit
    max_vram_mb: int = 0  # 0 = no limit
    
    # Timeouts
    default_timeout_s: int = 30
    tool_timeout_s: int = 60
    model_timeout_s: int = 120
    
    # Power/battery
    battery_policy: str = "balanced"  # "performance", "balanced", "power_save"
    thermal_throttling: bool = False
    
    # Background workload
    background_workload_allowed: bool = True
    background_priority: str = "normal"  # "low", "normal", "high"
    
    # Calibration metadata (populated by tune_with_calibration)
    calibration_report: Any = None
    calibration_overrides: list = field(default_factory=list)
    
    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        # Remove non-serializable calibration_report
        if "calibration_report" in data:
            del data["calibration_report"]
        return data


class RuntimeTuner:
    """Automatic runtime performance tuning."""
    
    def __init__(self, device_profiler: DeviceProfiler, hardware_profiler: HardwareProfiler):
        self.device_profiler = device_profiler
        self.hardware_profiler = hardware_profiler
        self._cached_parameters: TuningParameters | None = None
        self._cache_time: float = 0.0
        self._cache_ttl: float = 300.0  # 5 minutes cache
    
    def tune(self, force_refresh: bool = False) -> TuningParameters:
        """Generate optimal tuning parameters.
        
        Args:
            force_refresh: Force re-tuning even if cached.
            
        Returns:
            TuningParameters with optimal configuration.
        """
        now = time.monotonic()
        
        if not force_refresh and self._cached_parameters:
            if now - self._cache_time < self._cache_ttl:
                return self._cached_parameters
        
        # Get device and hardware profiles
        device_profile = self.device_profiler.profile(force_refresh)
        cpu_info = self.hardware_profiler.profile_cpu(force_refresh)
        gpu_info = self.hardware_profiler.profile_gpu(force_refresh)
        memory_info = self.hardware_profiler.profile_memory(force_refresh)
        battery_info = self.hardware_profiler.profile_battery()
        
        # Generate tuning parameters
        params = TuningParameters()
        
        # Select performance profile
        params.performance_profile = self._select_performance_profile(
            device_profile, cpu_info, memory_info, battery_info
        )
        
        # Tune model parameters
        params.model_size_preference = self._select_model_size(params.performance_profile)
        params.quantization_preference = self._select_quantization(params.performance_profile, memory_info)
        params.context_length = self._select_context_length(params.performance_profile, memory_info)
        
        # Tune execution parameters
        params.max_parallel_workers = self._select_parallel_workers(device_profile, cpu_info, memory_info)
        params.tool_concurrency = self._select_tool_concurrency(params.performance_profile)
        params.cache_size_mb = self._select_cache_size(memory_info)
        
        # Set resource limits
        params.max_ram_mb = self._select_ram_limit(memory_info)
        params.max_vram_mb = self._select_vram_limit(gpu_info)
        
        # Set timeouts
        params.default_timeout_s = self._select_timeout(params.performance_profile)
        params.tool_timeout_s = params.default_timeout_s * 2
        params.model_timeout_s = params.default_timeout_s * 4
        
        # Set battery policy
        params.battery_policy = self._select_battery_policy(battery_info, params.performance_profile)
        params.thermal_throttling = self._detect_thermal_throttling()
        
        # Set background workload policy
        params.background_workload_allowed = self._select_background_workload(device_profile)
        params.background_priority = self._select_background_priority(params.performance_profile)
        
        # Cache the parameters
        self._cached_parameters = params
        self._cache_time = now
        
        return params
    
    def tune_with_calibration(
        self, 
        benchmark_history: "BenchmarkHistory" | None = None,
        force_refresh: bool = False,
    ) -> TuningParameters:
        """Generate tuning parameters with benchmark calibration.
        
        This extends the base tune() method by incorporating benchmark
        evidence to override hardware-based recommendations.
        
        Args:
            benchmark_history: BenchmarkHistory instance with observations.
            force_refresh: Force re-tuning even if cached.
            
        Returns:
            TuningParameters calibrated with benchmark evidence.
        """
        # First get hardware-based recommendation
        hardware_params = self.tune(force_refresh=force_refresh)

        if benchmark_history is None:
            return hardware_params
        try:
            from benchmarks import CalibrationEngine
            from benchmarks.calibration_engine import (
                create_hardware_recommendation_from_tuner,
            )
        except ImportError:
            return hardware_params
        
        # Check if we have any benchmark data
        tested_models = benchmark_history.get_all_models_tested()
        if not tested_models:
            return hardware_params
        
        # Convert hardware params to HardwareRecommendation
        hw_rec = create_hardware_recommendation_from_tuner(hardware_params)
        
        # Aggregate benchmark results for all tested models
        benchmark_results = {}
        for provider_id, model_id in tested_models:
            result = benchmark_history.aggregate_model_results(provider_id, model_id)
            if result.sample_count > 0:
                benchmark_results[f"{provider_id}:{model_id}"] = result
        
        if not benchmark_results:
            return hardware_params
        
        # Get full hardware profile for resource limits (basic profile()
        # has zeroed memory/GPU fields, which would silently drop the
        # RAM/VRAM calibration overrides).
        if hasattr(self.device_profiler, "profile_with_hardware"):
            device_profile = self.device_profiler.profile_with_hardware(
                self.hardware_profiler, force_refresh)
        else:
            device_profile = self.device_profiler.profile(force_refresh)
        device_dict = device_profile.to_dict()
        
        # Run calibration
        engine = CalibrationEngine()
        calibration_report = engine.calibrate(hw_rec, benchmark_results, device_dict)
        
        # Apply calibrated parameters
        calibrated_params = TuningParameters()
        final_rec = calibration_report.final_recommendation
        
        for field_name in calibrated_params.__dataclass_fields__:
            if field_name in final_rec:
                setattr(calibrated_params, field_name, final_rec[field_name])
            else:
                # Fall back to hardware recommendation
                setattr(calibrated_params, field_name, getattr(hardware_params, field_name))
        
        # Attach calibration metadata
        calibrated_params.calibration_report = calibration_report
        calibrated_params.calibration_overrides = calibration_report.overrides
        
        # Cache the calibrated parameters
        self._cached_parameters = calibrated_params
        self._cache_time = time.monotonic()
        
        return calibrated_params
    
    def _select_performance_profile(self, device_profile, cpu_info, memory_info, battery_info) -> str:
        """Select appropriate performance profile."""
        ram_gb = memory_info.total_mb / 1024
        
        # Ultra low resource devices
        if ram_gb < 2:
            return PROFILE_ULTRA_LOW_RESOURCE
        
        # Mobile devices
        if device_profile.is_mobile():
            if battery_info.present and battery_info.level_percent < 20:
                return PROFILE_MOBILE_POWER_SAVE
            return PROFILE_MOBILE
        
        # Low resource desktop
        if ram_gb < 8:
            return PROFILE_LOW_RESOURCE
        
        # Server-class hardware
        if device_profile.device_class == DEVICE_CLASS_SERVER:
            return PROFILE_SERVER
        
        # Workstation-class hardware
        if device_profile.device_class == DEVICE_CLASS_DESKTOP and ram_gb >= 32:
            return PROFILE_WORKSTATION
        
        # Performance laptops/desktops
        if ram_gb >= 16:
            return PROFILE_PERFORMANCE
        
        # Default balanced
        return PROFILE_BALANCED
    
    def _select_model_size(self, performance_profile: str) -> str:
        """Select preferred model size."""
        size_map = {
            PROFILE_ULTRA_LOW_RESOURCE: "tiny",
            PROFILE_MOBILE: "small",
            PROFILE_MOBILE_POWER_SAVE: "tiny",
            PROFILE_LOW_RESOURCE: "small",
            PROFILE_BALANCED: "medium",
            PROFILE_PERFORMANCE: "large",
            PROFILE_WORKSTATION: "large",
            PROFILE_SERVER: "auto"
        }
        return size_map.get(performance_profile, "medium")
    
    def _select_quantization(self, performance_profile: str, memory_info) -> str:
        """Select preferred quantization."""
        ram_gb = memory_info.total_mb / 1024
        
        # Low memory: use aggressive quantization
        if ram_gb < 8:
            return "q4"
        
        # Medium memory: balanced quantization
        if ram_gb < 16:
            return "q8"
        
        # High memory: full precision
        return "f16"
    
    def _select_context_length(self, performance_profile: str, memory_info) -> int:
        """Select appropriate context length."""
        ram_gb = memory_info.total_mb / 1024
        
        # Low memory: smaller context
        if ram_gb < 8:
            return 2048
        
        # Medium memory: standard context
        if ram_gb < 16:
            return 4096
        
        # High memory: large context
        if ram_gb >= 32:
            return 8192
        
        return 4096
    
    def _select_parallel_workers(self, device_profile, cpu_info, memory_info) -> int:
        """Select number of parallel workers."""
        # Mobile devices: single worker
        if device_profile.is_mobile():
            return 1
        
        # Low memory: limited parallelism
        if memory_info.total_mb < 8192:  # < 8GB
            return 1
        
        # Desktop with good specs: more parallelism
        if cpu_info.logical_cores >= 8 and memory_info.total_mb >= 16384:  # >= 8 cores, >= 16GB
            return min(4, cpu_info.logical_cores // 2)
        
        # Default: conservative parallelism
        return 2
    
    def _select_tool_concurrency(self, performance_profile: str) -> int:
        """Select tool concurrency level."""
        concurrency_map = {
            PROFILE_ULTRA_LOW_RESOURCE: 1,
            PROFILE_MOBILE: 1,
            PROFILE_MOBILE_POWER_SAVE: 1,
            PROFILE_LOW_RESOURCE: 1,
            PROFILE_BALANCED: 2,
            PROFILE_PERFORMANCE: 3,
            PROFILE_WORKSTATION: 4,
            PROFILE_SERVER: 4
        }
        return concurrency_map.get(performance_profile, 2)
    
    def _select_cache_size(self, memory_info) -> int:
        """Select cache size based on available memory."""
        ram_gb = memory_info.total_mb / 1024
        
        # Use 10% of RAM for cache, capped at reasonable limits
        cache_mb = int(memory_info.total_mb * 0.1)
        
        # Minimum cache
        cache_mb = max(cache_mb, 128)
        
        # Maximum cache (don't use too much)
        cache_mb = min(cache_mb, 2048)
        
        return cache_mb
    
    def _select_ram_limit(self, memory_info) -> int:
        """Select RAM limit (0 = no limit)."""
        ram_gb = memory_info.total_mb / 1024
        
        # For low memory systems, set a limit to prevent OOM
        if ram_gb < 8:
            return int(memory_info.total_mb * 0.7)  # Use 70% of RAM
        
        # For higher memory systems, no limit
        return 0
    
    def _select_vram_limit(self, gpu_info) -> int:
        """Select VRAM limit (0 = no limit)."""
        if gpu_info.vram_mb > 0:
            # Use 80% of VRAM
            return int(gpu_info.vram_mb * 0.8)
        
        return 0
    
    def _select_timeout(self, performance_profile: str) -> int:
        """Select default timeout based on performance profile."""
        timeout_map = {
            PROFILE_ULTRA_LOW_RESOURCE: 60,
            PROFILE_MOBILE: 30,
            PROFILE_MOBILE_POWER_SAVE: 45,
            PROFILE_LOW_RESOURCE: 30,
            PROFILE_BALANCED: 30,
            PROFILE_PERFORMANCE: 20,
            PROFILE_WORKSTATION: 15,
            PROFILE_SERVER: 15
        }
        return timeout_map.get(performance_profile, 30)
    
    def _select_battery_policy(self, battery_info, performance_profile: str) -> str:
        """Select battery policy."""
        if not battery_info.present:
            return "balanced"
        
        # Low battery: power save
        if battery_info.level_percent < 20:
            return "power_save"
        
        # Charging: performance
        if battery_info.charging:
            return "performance"
        
        # Medium battery: balanced
        if battery_info.level_percent < 50:
            return "balanced"
        
        # High battery: use performance profile
        if performance_profile in (PROFILE_PERFORMANCE, PROFILE_WORKSTATION):
            return "performance"
        
        return "balanced"
    
    def _detect_thermal_throttling(self) -> bool:
        """Detect if thermal throttling is occurring."""
        # This would require platform-specific thermal sensors
        # For now, return False
        return False
    
    def _select_background_workload(self, device_profile) -> bool:
        """Select if background workload is allowed."""
        # Desktop systems: allow background
        if device_profile.is_desktop():
            return True
        
        # Mobile systems: may have restrictions
        return False
    
    def _select_background_priority(self, performance_profile: str) -> str:
        """Select background priority."""
        priority_map = {
            PROFILE_ULTRA_LOW_RESOURCE: "low",
            PROFILE_MOBILE: "low",
            PROFILE_MOBILE_POWER_SAVE: "low",
            PROFILE_LOW_RESOURCE: "low",
            PROFILE_BALANCED: "normal",
            PROFILE_PERFORMANCE: "normal",
            PROFILE_WORKSTATION: "high",
            PROFILE_SERVER: "high"
        }
        return priority_map.get(performance_profile, "normal")
    
    def update_on_battery_change(self, battery_level: int, charging: bool) -> TuningParameters:
        """Update tuning parameters when battery state changes.
        
        Args:
            battery_level: Current battery level percentage.
            charging: Whether device is charging.
            
        Returns:
            Updated TuningParameters.
        """
        # Force re-tune with new battery state
        return self.tune(force_refresh=True)
    
    def update_on_thermal_change(self, thermal_state: str) -> TuningParameters:
        """Update tuning parameters when thermal state changes.
        
        Args:
            thermal_state: Thermal state ("normal", "throttling", "critical").
            
        Returns:
            Updated TuningParameters.
        """
        # Force re-tune with new thermal state
        return self.tune(force_refresh=True)
    
    def get_cached_parameters(self) -> TuningParameters | None:
        """Get cached tuning parameters if available."""
        if self._cached_parameters and time.monotonic() - self._cache_time < self._cache_ttl:
            return self._cached_parameters
        return None
    
    def clear_cache(self) -> None:
        """Clear cached tuning parameters."""
        self._cached_parameters = None
        self._cache_time = 0.0