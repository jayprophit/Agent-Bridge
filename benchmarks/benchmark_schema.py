"""Benchmark schema (v0.7). Data classes for benchmark observations and results.

Defines the canonical schema for benchmark data with versioning support.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


# Schema versioning
BENCHMARK_SCHEMA_VERSION = "1.0.0"
BENCHMARK_SUITE_VERSION = "1.0.0"


# Capability evidence levels
EVIDENCE_DECLARED = "DECLARED"
EVIDENCE_PROVIDER_REPORTED = "PROVIDER_REPORTED"
EVIDENCE_PROBE_VERIFIED = "PROBE_VERIFIED"
EVIDENCE_BENCHMARK_VERIFIED = "BENCHMARK_VERIFIED"
EVIDENCE_UNKNOWN = "UNKNOWN"
EVIDENCE_FAILED_PROBE = "FAILED_PROBE"

# Tool calling evidence sub-types
TOOL_NATIVE = "NATIVE_TOOL_CALLING"
TOOL_BRIDGE_STRUCTURED = "BRIDGE_STRUCTURED_ACTION"
TOOL_STRUCTURED_JSON = "STRUCTURED_JSON"
TOOL_CONTENT_INTENT = "CONTENT_TOOL_INTENT"

CAPABILITY_EVIDENCE_LEVELS = (
    EVIDENCE_DECLARED,
    EVIDENCE_PROVIDER_REPORTED,
    EVIDENCE_PROBE_VERIFIED,
    EVIDENCE_BENCHMARK_VERIFIED,
    EVIDENCE_UNKNOWN,
    EVIDENCE_FAILED_PROBE,
)


# Benchmark test types
TEST_SIMPLE_GENERATION = "SIMPLE_GENERATION"
TEST_CODE_GENERATION = "CODE_GENERATION"
TEST_STRUCTURED_OUTPUT = "STRUCTURED_OUTPUT"
TEST_TOOL_CALL = "TOOL_CALL"
TEST_CONTEXT_TEST = "CONTEXT_TEST"
TEST_VISION_PROBE = "VISION_PROBE"
TEST_REVIEW = "REVIEW"

BENCHMARK_TEST_TYPES = (
    TEST_SIMPLE_GENERATION,
    TEST_CODE_GENERATION,
    TEST_STRUCTURED_OUTPUT,
    TEST_TOOL_CALL,
    TEST_CONTEXT_TEST,
    TEST_VISION_PROBE,
    TEST_REVIEW,
)


# Cold/warm state
STATE_COLD = "COLD"
STATE_WARM = "WARM"
STATE_UNKNOWN = "UNKNOWN"

BENCHMARK_STATES = (STATE_COLD, STATE_WARM, STATE_UNKNOWN)


@dataclass
class BenchmarkObservation:
    """Single benchmark observation for a model on a specific test."""
    
    # Identifiers
    benchmark_id: str = ""
    schema_version: str = BENCHMARK_SCHEMA_VERSION
    suite_version: str = BENCHMARK_SUITE_VERSION
    
    # Provider/Model/Device context
    provider_id: str = ""
    model_id: str = ""
    device_id: str = ""
    
    # Timing
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    
    # Test specification
    test_type: str = ""
    test_name: str = ""
    cold_or_warm: str = STATE_UNKNOWN
    
    # Provider-reported timing (from Ollama /api/chat response)
    load_duration_ms: int | None = None
    prompt_eval_count: int | None = None
    prompt_eval_duration_ms: int | None = None
    eval_count: int | None = None
    eval_duration_ms: int | None = None
    total_duration_ms: int | None = None
    
    # Derived metrics
    time_to_first_token_ms: int | None = None
    generation_duration_ms: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    tokens_per_second: float | None = None
    
    # Resource measurements
    ram_before_mb: int | None = None
    ram_peak_mb: int | None = None
    ram_after_mb: int | None = None
    
    # Provider process RAM (if detectable)
    provider_ram_before_mb: int | None = None
    provider_ram_peak_mb: int | None = None
    provider_ram_after_mb: int | None = None
    
    # System RAM
    system_ram_before_mb: int | None = None
    system_ram_peak_mb: int | None = None
    system_ram_after_mb: int | None = None
    
    # Total attributed RAM (client + provider if measured, else estimated)
    total_attributed_ram_mb: int | None = None
    ram_attribution_method: str = ""  # "MEASURED" or "ESTIMATED"
    
    vram_before_mb: int | None = None
    vram_peak_mb: int | None = None
    vram_after_mb: int | None = None
    
    cpu_utilization_percent: float | None = None
    gpu_utilization_percent: float | None = None
    
    # GPU offload information
    gpu_offload_layers: int | None = None
    gpu_offload_total_layers: int | None = None
    
    # Capability verification
    tool_call_requested: bool = False
    tool_call_valid: bool | None = None
    tool_call_malformed: int | None = None
    tool_call_repair_attempts: int | None = None
    # Tool calling evidence subtype
    tool_call_evidence: str = ""  # NATIVE_TOOL_CALLING, BRIDGE_STRUCTURED_ACTION, STRUCTURED_JSON, CONTENT_TOOL_INTENT
    
    structured_output_requested: bool = False
    structured_output_valid: bool | None = None
    
    # Outcome
    task_success: bool | None = None
    timeout: bool = False
    cancelled: bool = False
    error: str | None = None
    
    # Quality classification
    quality_rating: str | None = None  # "excellent", "good", "acceptable", "poor", "failed"
    
    # Limitations / notes
    limitations: list[str] = field(default_factory=list)
    
    def __post_init__(self) -> None:
        if self.tokens_per_second is None and self.eval_count and self.eval_duration_ms:
            if self.eval_duration_ms > 0:
                self.tokens_per_second = (self.eval_count * 1000.0) / self.eval_duration_ms
    
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BenchmarkObservation":
        # Filter to only known fields
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)


@dataclass
class BenchmarkResult:
    """Aggregated benchmark result for a model across test types."""
    
    model_id: str = ""
    provider_id: str = ""
    device_id: str = ""
    
    observations: list[BenchmarkObservation] = field(default_factory=list)
    
    # Aggregated metrics
    avg_tokens_per_second: float | None = None
    avg_time_to_first_token_ms: int | None = None
    avg_generation_duration_ms: int | None = None
    
    # Reliability metrics
    tool_call_reliability: float | None = None  # 0.0 - 1.0
    structured_output_reliability: float | None = None
    task_success_rate: float | None = None
    error_rate: float | None = None
    
    # Resource profiles
    typical_ram_mb: int | None = None
    peak_ram_mb: int | None = None
    typical_vram_mb: int | None = None
    peak_vram_mb: int | None = None
    
    # Capability evidence
    capability_evidence: dict[str, str] = field(default_factory=dict)
    
    # Confidence
    sample_count: int = 0
    confidence: str = "PRELIMINARY"  # "PRELIMINARY", "LOW", "MEDIUM", "HIGH"
    
    # Timestamp of aggregation
    aggregated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    
    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["observations"] = [obs.to_dict() for obs in self.observations]
        return data


@dataclass
class BenchmarkProfile:
    """Configuration profile for running benchmarks."""
    
    profile_id: str = ""
    name: str = ""
    description: str = ""
    
    # Test selection
    include_tests: list[str] = field(default_factory=lambda: [
        TEST_SIMPLE_GENERATION,
        TEST_CODE_GENERATION,
        TEST_STRUCTURED_OUTPUT,
        TEST_TOOL_CALL,
    ])
    
    # Per-test configuration
    test_configs: dict[str, dict[str, Any]] = field(default_factory=dict)
    
    # Execution parameters
    warmup_runs: int = 1
    measurement_runs: int = 2
    max_concurrent: int = 1
    
    # Safety limits
    max_total_duration_s: int = 300
    max_memory_pressure_percent: int = 80
    skip_on_timeout: bool = True
    
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CalibrationOverride:
    """Records a calibration-based override of hardware recommendation."""
    
    parameter: str = ""
    hardware_recommendation: Any = None
    calibrated_recommendation: Any = None
    evidence_summary: str = ""
    confidence: str = "PRELIMINARY"
    benchmark_ids: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CalibrationReport:
    """Full calibration report combining hardware and benchmark evidence."""
    
    device_id: str = ""
    hardware_profile: dict[str, Any] = field(default_factory=dict)
    benchmark_results: dict[str, BenchmarkResult] = field(default_factory=dict)
    overrides: list[CalibrationOverride] = field(default_factory=list)
    
    final_recommendation: dict[str, Any] = field(default_factory=dict)
    confidence: str = "PRELIMINARY"
    
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    
    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["benchmark_results"] = {
            k: v.to_dict() for k, v in self.benchmark_results.items()
        }
        data["overrides"] = [o.to_dict() for o in self.overrides]
        return data