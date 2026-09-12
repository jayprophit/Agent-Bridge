"""Tests for benchmark framework (v0.7)."""
import os
import unittest
from unittest.mock import MagicMock, patch

from benchmarks.benchmark_schema import (
    BenchmarkObservation,
    BenchmarkResult,
    BenchmarkProfile,
    CalibrationOverride,
    BENCHMARK_SCHEMA_VERSION,
    BENCHMARK_SUITE_VERSION,
    TEST_SIMPLE_GENERATION,
    TEST_CODE_GENERATION,
    STATE_COLD,
    STATE_WARM,
)

from benchmarks.benchmark_history import (
    BenchmarkStore,
    BenchmarkHistory,
    ModelBenchmarkSummary,
)

from benchmarks.calibration_engine import (
    CalibrationEngine,
    HardwareRecommendation,
    create_hardware_recommendation_from_tuner,
)


class BenchmarkSchemaTests(unittest.TestCase):
    def test_observation_creation(self):
        """Test creating a benchmark observation."""
        obs = BenchmarkObservation(
            benchmark_id="test-001",
            provider_id="ollama",
            model_id="qwen2.5-coder:3b",
            device_id="device-123",
            test_type=TEST_SIMPLE_GENERATION,
            test_name="simple_greeting",
            cold_or_warm=STATE_WARM,
            tokens_per_second=25.5,
            task_success=True,
        )
        
        self.assertEqual(obs.provider_id, "ollama")
        self.assertEqual(obs.model_id, "qwen2.5-coder:3b")
        self.assertEqual(obs.tokens_per_second, 25.5)
        self.assertEqual(obs.cold_or_warm, STATE_WARM)
    
    def test_observation_tokens_per_second_calculation(self):
        """Test auto-calculation of tokens_per_second from eval_count and duration."""
        obs = BenchmarkObservation(
            eval_count=100,
            eval_duration_ms=2000,  # 2 seconds
        )
        
        # Should auto-calculate: 100 tokens / 2s = 50 tokens/s
        self.assertAlmostEqual(obs.tokens_per_second, 50.0, places=1)
    
    def test_observation_serialization(self):
        """Test observation can be serialized and deserialized."""
        obs = BenchmarkObservation(
            benchmark_id="test-002",
            provider_id="ollama",
            model_id="test-model",
            device_id="device-1",
            test_type=TEST_CODE_GENERATION,
            test_name="python_function",
            cold_or_warm=STATE_COLD,
            load_duration_ms=5000,
            eval_count=50,
            eval_duration_ms=1000,
            task_success=True,
            quality_rating="good",
        )
        
        data = obs.to_dict()
        self.assertEqual(data["benchmark_id"], "test-002")
        self.assertEqual(data["tokens_per_second"], 50.0)
        
        # Deserialize
        obs2 = BenchmarkObservation.from_dict(data)
        self.assertEqual(obs2.benchmark_id, "test-002")
        self.assertEqual(obs2.tokens_per_second, 50.0)
    
    def test_result_aggregation(self):
        """Test benchmark result aggregation."""
        obs1 = BenchmarkObservation(
            benchmark_id="obs-1",
            provider_id="ollama",
            model_id="model-a",
            device_id="dev-1",
            test_type=TEST_SIMPLE_GENERATION,
            test_name="test1",
            tokens_per_second=20.0,
            time_to_first_token_ms=100,
            task_success=True,
        )
        obs2 = BenchmarkObservation(
            benchmark_id="obs-2",
            provider_id="ollama",
            model_id="model-a",
            device_id="dev-1",
            test_type=TEST_CODE_GENERATION,
            test_name="test2",
            tokens_per_second=30.0,
            time_to_first_token_ms=200,
            task_success=True,
        )
        
        # Use BenchmarkHistory to aggregate
        import tempfile
        temp_dir = tempfile.mkdtemp()
        store_path = f"{temp_dir}/test_benchmarks.jsonl"
        store = BenchmarkStore(store_path)
        history = BenchmarkHistory(store)
        
        history.record(obs1)
        history.record(obs2)
        
        result = history.aggregate_model_results("ollama", "model-a")
        
        self.assertEqual(result.model_id, "model-a")
        self.assertEqual(result.sample_count, 2)
        self.assertAlmostEqual(result.avg_tokens_per_second, 25.0, places=1)
        self.assertEqual(result.avg_time_to_first_token_ms, 150)
        
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)


class BenchmarkHistoryTests(unittest.TestCase):
    def setUp(self):
        """Create a temporary store for testing."""
        import tempfile
        self.temp_dir = tempfile.mkdtemp()
        self.store_path = f"{self.temp_dir}/test_benchmarks.jsonl"
        self.store = BenchmarkStore(self.store_path)
        self.history = BenchmarkHistory(self.store)
    
    def tearDown(self):
        """Clean up temp files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_record_and_query(self):
        """Test recording and querying observations."""
        obs = BenchmarkObservation(
            benchmark_id="test-001",
            provider_id="ollama",
            model_id="test-model",
            device_id="device-1",
            test_type=TEST_SIMPLE_GENERATION,
            test_name="simple_test",
            tokens_per_second=25.0,
            task_success=True,
        )
        
        self.history.record(obs)
        
        results = self.history.get_model_history("ollama", "test-model")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].benchmark_id, "test-001")
    
    def test_aggregate_model_results(self):
        """Test aggregating multiple observations into a result."""
        for i in range(3):
            obs = BenchmarkObservation(
                benchmark_id=f"obs-{i}",
                provider_id="ollama",
                model_id="test-model",
                device_id="device-1",
                test_type=TEST_SIMPLE_GENERATION,
                test_name=f"test_{i}",
                tokens_per_second=20.0 + i * 5,
                time_to_first_token_ms=100 + i * 10,
                task_success=True,
            )
            self.history.record(obs)
        
        result = self.history.aggregate_model_results("ollama", "test-model")
        
        self.assertEqual(result.model_id, "test-model")
        self.assertEqual(result.sample_count, 3)
        self.assertAlmostEqual(result.avg_tokens_per_second, 25.0, places=1)
        self.assertEqual(result.task_success_rate, 1.0)
        self.assertIn(result.confidence, ("LOW", "PRELIMINARY"))


class CalibrationEngineTests(unittest.TestCase):
    def test_quantization_override_q4_works(self):
        """Test that calibration recommends q4 when q4 models perform well."""
        engine = CalibrationEngine()
        
        hw_rec = HardwareRecommendation(
            quantization_preference="q8",
            model_size_preference="medium",
        )
        
        # Create mock benchmark result showing q4 works well
        from benchmarks.benchmark_schema import BenchmarkResult
        result = BenchmarkResult(
            model_id="ollama:qwen2.5-coder:3b-q4",
            provider_id="ollama",
            device_id="dev-1",
            avg_tokens_per_second=25.0,
            task_success_rate=1.0,
            sample_count=2,
            confidence="LOW",
        )
        
        device_profile = {
            "device_id": "dev-1",
            "gpu": {"vram_mb": 4096},
            "memory": {"total_mb": 16384},
        }
        
        report = engine.calibrate(hw_rec, {"ollama:qwen2.5-coder:3b-q4": result}, device_profile)
        
        # Should recommend q4
        self.assertEqual(report.final_recommendation["quantization_preference"], "q4")
        self.assertTrue(len(report.overrides) > 0)
        
        override = report.overrides[0]
        self.assertEqual(override.parameter, "quantization_preference")
        self.assertEqual(override.calibrated_recommendation, "q4")
    
    def test_model_size_override_small_better(self):
        """Test that calibration recommends smaller model when it outperforms."""
        engine = CalibrationEngine()
        
        hw_rec = HardwareRecommendation(
            model_size_preference="medium",
            quantization_preference="q8",
        )
        
        # Small model outperforms medium
        small_result = BenchmarkResult(
            model_id="ollama:qwen3:1.7b",
            provider_id="ollama",
            device_id="dev-1",
            avg_tokens_per_second=30.0,
            task_success_rate=1.0,
            sample_count=2,
        )
        medium_result = BenchmarkResult(
            model_id="ollama:qwen2.5-coder:3b",
            provider_id="ollama",
            device_id="dev-1",
            avg_tokens_per_second=20.0,
            task_success_rate=1.0,
            sample_count=2,
        )
        
        device_profile = {
            "device_id": "dev-1",
            "gpu": {"vram_mb": 4096},
            "memory": {"total_mb": 16384},
        }
        
        report = engine.calibrate(
            hw_rec, 
            {"ollama:qwen3:1.7b": small_result, "ollama:qwen2.5-coder:3b": medium_result},
            device_profile
        )
        
        # Should recommend small
        self.assertEqual(report.final_recommendation["model_size_preference"], "small")
    
    def test_concurrency_override_on_errors(self):
        """Test that calibration reduces concurrency when errors are high."""
        engine = CalibrationEngine()
        
        hw_rec = HardwareRecommendation(
            max_parallel_workers=2,
            tool_concurrency=2,
        )
        
        result = BenchmarkResult(
            model_id="ollama:test-model",
            provider_id="ollama",
            device_id="dev-1",
            error_rate=0.5,  # High error rate
            task_success_rate=0.5,
            sample_count=4,
        )
        
        device_profile = {
            "device_id": "dev-1",
            "gpu": {"vram_mb": 4096},
            "memory": {"total_mb": 16384},
        }
        
        report = engine.calibrate(hw_rec, {"ollama:test-model": result}, device_profile)
        
        # Should reduce to 1
        self.assertEqual(report.final_recommendation["max_parallel_workers"], 1)
        self.assertEqual(report.final_recommendation["tool_concurrency"], 1)
    
    def test_vram_override_from_measurement(self):
        """Test that calibration sets VRAM limit based on measurements."""
        engine = CalibrationEngine()
        
        hw_rec = HardwareRecommendation(max_vram_mb=0)
        
        result = BenchmarkResult(
            model_id="ollama:test-model",
            provider_id="ollama",
            device_id="dev-1",
            peak_vram_mb=2000,
            sample_count=2,
        )
        
        device_profile = {
            "device_id": "dev-1",
            "gpu": {"vram_mb": 4096},
            "memory": {"total_mb": 16384},
        }
        
        report = engine.calibrate(hw_rec, {"ollama:test-model": result}, device_profile)
        
        # Should set VRAM limit to measured peak + margin, capped at 80%
        expected = min(int(2000 * 1.2), int(4096 * 0.8))  # 2400 vs 3276 -> 2400
        self.assertEqual(report.final_recommendation["max_vram_mb"], expected)
    
    def test_ram_override_from_measurement(self):
        """Test that calibration sets RAM limit based on measurements."""
        engine = CalibrationEngine()
        
        hw_rec = HardwareRecommendation(max_ram_mb=0)
        
        result = BenchmarkResult(
            model_id="ollama:test-model",
            provider_id="ollama",
            device_id="dev-1",
            peak_ram_mb=3000,
            sample_count=2,
        )
        
        device_profile = {
            "device_id": "dev-1",
            "gpu": {"vram_mb": 4096},
            "memory": {"total_mb": 16384},
        }
        
        report = engine.calibrate(hw_rec, {"ollama:test-model": result}, device_profile)
        
        # Should set RAM limit to measured peak + margin, capped at 70%
        expected = min(int(3000 * 1.2), int(16384 * 0.7))  # 3600 vs 11468 -> 3600
        self.assertEqual(report.final_recommendation["max_ram_mb"], expected)
    
    def test_timeout_override_from_load_time(self):
        """Test that calibration extends timeout based on measured load time."""
        engine = CalibrationEngine()
        
        hw_rec = HardwareRecommendation(
            model_timeout_s=30,
            tool_timeout_s=60,
        )
        
        obs = BenchmarkObservation(
            benchmark_id="obs-1",
            provider_id="ollama",
            model_id="test-model",
            device_id="dev-1",
            test_type=TEST_CODE_GENERATION,
            test_name="test",
            load_duration_ms=25000,  # 25 seconds cold load
            generation_duration_ms=15000,
            task_success=True,
        )
        
        result = BenchmarkResult(
            model_id="ollama:test-model",
            provider_id="ollama",
            device_id="dev-1",
            observations=[obs],
            sample_count=1,
        )
        
        device_profile = {
            "device_id": "dev-1",
            "gpu": {"vram_mb": 4096},
            "memory": {"total_mb": 16384},
        }
        
        report = engine.calibrate(hw_rec, {"ollama:test-model": result}, device_profile)
        
        # Should extend timeout to accommodate load + generation + margin
        # (25000 + 15000) * 1.5 / 1000 + 30 = 60 + 30 = 90
        self.assertGreaterEqual(report.final_recommendation["model_timeout_s"], 60)


class HardwareRecommendationTests(unittest.TestCase):
    def test_create_from_tuner_params(self):
        """Test converting tuner params to hardware recommendation."""
        from device.runtime_tuner import TuningParameters
        
        params = TuningParameters(
            performance_profile="BALANCED",
            model_size_preference="medium",
            quantization_preference="q8",
            context_length=4096,
            max_parallel_workers=2,
            tool_concurrency=2,
            cache_size_mb=1634,
            max_ram_mb=0,
            max_vram_mb=3276,
            default_timeout_s=30,
            tool_timeout_s=60,
            model_timeout_s=120,
        )
        
        hw_rec = create_hardware_recommendation_from_tuner(params)
        
        self.assertEqual(hw_rec.performance_profile, "BALANCED")
        self.assertEqual(hw_rec.model_size_preference, "medium")
        self.assertEqual(hw_rec.quantization_preference, "q8")
        self.assertEqual(hw_rec.max_parallel_workers, 2)
        self.assertEqual(hw_rec.max_vram_mb, 3276)


class TunerCalibrationRegressionTests(unittest.TestCase):
    """Regression: calibration must actually engage (no silent fallback)."""

    def test_benchmark_integration_available(self):
        import device.runtime_tuner as rt
        self.assertTrue(rt.BENCHMARKS_AVAILABLE)

    def test_tune_with_calibration_applies_overrides(self):
        import tempfile
        from types import SimpleNamespace
        from device.runtime_tuner import RuntimeTuner

        device_profiler = MagicMock()
        basic = SimpleNamespace(
            is_mobile=lambda: False, is_desktop=lambda: True,
            device_class="desktop",
            to_dict=lambda: {"device_id": "t",
                             "memory": {"total_mb": 0},
                             "gpu": {"vram_mb": 0, "vendor": ""}})
        full = SimpleNamespace(
            is_mobile=lambda: False, is_desktop=lambda: True,
            device_class="desktop",
            to_dict=lambda: {"device_id": "t",
                             "memory": {"total_mb": 16384},
                             "gpu": {"vram_mb": 4096, "vendor": "NVIDIA"}})
        device_profiler.profile.return_value = basic
        device_profiler.profile_with_hardware.return_value = full

        hardware_profiler = MagicMock()
        hardware_profiler.profile_cpu.return_value = SimpleNamespace(logical_cores=8)
        hardware_profiler.profile_memory.return_value = SimpleNamespace(total_mb=16384)
        hardware_profiler.profile_gpu.return_value = SimpleNamespace(vram_mb=4096)
        hardware_profiler.profile_battery.return_value = SimpleNamespace(
            present=False, level_percent=0, charging=False)

        with tempfile.TemporaryDirectory() as d:
            store = BenchmarkStore(os.path.join(d, "bench.jsonl"))
            history = BenchmarkHistory(store)
            for i, (model, count, dur) in enumerate(
                    [("tiny-1b", 100, 2000), ("mid-5b", 10, 2000)]):
                history.record(BenchmarkObservation(
                    benchmark_id=f"reg-{i}", provider_id="testprov",
                    model_id=model, device_id="t",
                    test_type=TEST_SIMPLE_GENERATION, test_name="t",
                    cold_or_warm=STATE_WARM, eval_count=count,
                    eval_duration_ms=dur, task_success=True))
            params = RuntimeTuner(device_profiler, hardware_profiler) \
                .tune_with_calibration(history, force_refresh=True)

        params_names = [o.parameter for o in (params.calibration_overrides or [])]
        self.assertIn("model_size_preference", params_names)
        self.assertEqual(params.model_size_preference, "small")
        # Full hardware profile must be used (basic profile zeroes RAM/VRAM)
        device_profiler.profile_with_hardware.assert_called()


if __name__ == "__main__":
    unittest.main()