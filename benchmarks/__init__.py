"""Model benchmarking framework (v0.7).

Provides standardized benchmark execution, history storage, and calibration
integration for automatic runtime tuning.
"""
from __future__ import annotations

from benchmarks.benchmark_schema import (
    BenchmarkObservation,
    BenchmarkResult,
    BenchmarkProfile,
    CalibrationOverride,
    CalibrationReport,
    BENCHMARK_SCHEMA_VERSION,
    BENCHMARK_SUITE_VERSION,
    TEST_SIMPLE_GENERATION,
    TEST_CODE_GENERATION,
    TEST_STRUCTURED_OUTPUT,
    TEST_TOOL_CALL,
    TEST_CONTEXT_TEST,
    TEST_VISION_PROBE,
    TEST_REVIEW,
    STATE_COLD,
    STATE_WARM,
    CAPABILITY_EVIDENCE_LEVELS,
)

from benchmarks.benchmark_history import (
    BenchmarkStore,
    BenchmarkHistory,
    ModelBenchmarkSummary,
)

from benchmarks.benchmark_runner import (
    BenchmarkRunner,
    BenchmarkTest,
    DEFAULT_BENCHMARK_TESTS,
    ResourceMonitor,
    create_ollama_provider,
)

from benchmarks.calibration_engine import (
    CalibrationEngine,
    HardwareRecommendation,
    create_hardware_recommendation_from_tuner,
)

__all__ = [
    # Schema
    "BenchmarkObservation",
    "BenchmarkResult", 
    "BenchmarkProfile",
    "CalibrationOverride",
    "CalibrationReport",
    "BENCHMARK_SCHEMA_VERSION",
    "BENCHMARK_SUITE_VERSION",
    "TEST_SIMPLE_GENERATION",
    "TEST_CODE_GENERATION",
    "TEST_STRUCTURED_OUTPUT",
    "TEST_TOOL_CALL",
    "TEST_CONTEXT_TEST",
    "TEST_VISION_PROBE",
    "TEST_REVIEW",
    "STATE_COLD",
    "STATE_WARM",
    "CAPABILITY_EVIDENCE_LEVELS",
    # History
    "BenchmarkStore",
    "BenchmarkHistory",
    "ModelBenchmarkSummary",
    # Runner
    "BenchmarkRunner",
    "BenchmarkTest",
    "DEFAULT_BENCHMARK_TESTS",
    "ResourceMonitor",
    "create_ollama_provider",
    # Calibration
    "CalibrationEngine",
    "HardwareRecommendation",
    "create_hardware_recommendation_from_tuner",
]