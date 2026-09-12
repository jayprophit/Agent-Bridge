"""Benchmark runner (v0.7). Executes benchmark tests against providers.

Runs standardized benchmark workloads and produces BenchmarkObservation records.
"""
from __future__ import annotations

import json
import os
import psutil
import time
import uuid
from dataclasses import dataclass
from typing import Any

from benchmarks.benchmark_schema import (
    BenchmarkObservation,
    BenchmarkProfile,
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
    STATE_UNKNOWN,
    CAPABILITY_EVIDENCE_LEVELS,
    TOOL_NATIVE,
    TOOL_BRIDGE_STRUCTURED,
    TOOL_STRUCTURED_JSON,
    TOOL_CONTENT_INTENT,
)

from benchmarks.benchmark_history import BenchmarkStore


@dataclass
class BenchmarkTest:
    """Definition of a single benchmark test."""
    test_type: str
    name: str
    prompt: str
    system_prompt: str | None = None
    temperature: float = 0.1
    max_tokens: int = 512
    tools: list[dict[str, Any]] | None = None
    structured_output_schema: dict[str, Any] | None = None
    expect_tool_call: bool = False
    expect_structured_output: bool = False
    timeout_s: int = 120


# Default benchmark tests
DEFAULT_BENCHMARK_TESTS = [
    BenchmarkTest(
        test_type=TEST_SIMPLE_GENERATION,
        name="simple_greeting",
        prompt="Say hello in one short sentence.",
        max_tokens=64,
        timeout_s=60,
    ),
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
    BenchmarkTest(
        test_type=TEST_CONTEXT_TEST,
        name="short_context",
        prompt=(
            "I will give you a short text. Repeat it back to me.\n\n"
            "Text: The quick brown fox jumps over the lazy dog."
        ),
        max_tokens=128,
        timeout_s=60,
    ),
]


class ResourceMonitor:
    """Monitors system resources during benchmark execution.
    
    Tracks:
    - Client process (Python benchmark process)
    - Provider process (e.g., Ollama server)
    - Model runner process (if detectable)
    - System-wide RAM before/during/after
    """
    
    # Known provider process names to look for
    PROVIDER_PROCESS_NAMES = {
        "ollama": ["ollama.exe", "ollama"],
        "lm_studio": ["LM Studio.exe", "lm-studio"],
        "llama_cpp": ["llama-server", "llama.cpp"],
        "vllm": ["vllm", "python -m vllm"],
    }
    
    def __init__(self, provider_id: str = ""):
        self.client_process = psutil.Process(os.getpid())
        self.provider_id = provider_id.lower()
        self.provider_process = None
        self._find_provider_process()
        
        # RAM tracking
        self._client_ram_before = None
        self._provider_ram_before = None
        self._system_ram_before = None
        self._client_peak = 0
        self._provider_peak = 0
        self._system_peak = 0
        
        # VRAM tracking
        self._baseline_vram = None
        self._peak_vram = 0
    
    def _find_provider_process(self) -> None:
        """Try to find the provider process by name."""
        try:
            provider_names = self.PROVIDER_PROCESS_NAMES.get(self.provider_id, [])
            for proc in psutil.process_iter(['pid', 'name', 'exe', 'cmdline']):
                try:
                    name = (proc.info.get('name') or '').lower()
                    exe = (proc.info.get('exe') or '').lower()
                    cmdline = ' '.join(proc.info.get('cmdline') or []).lower()
                    
                    for provider_name in provider_names:
                        if provider_name.lower() in name or provider_name.lower() in exe or provider_name.lower() in cmdline:
                            self.provider_process = psutil.Process(proc.info['pid'])
                            return
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception:
            pass
    
    def start(self) -> dict[str, int | None]:
        """Record baseline measurements."""
        # Client process RAM
        self._client_ram_before = self.client_process.memory_info().rss // (1024 * 1024)
        self._client_peak = self._client_ram_before
        
        # Provider process RAM
        self._provider_ram_before = 0
        if self.provider_process:
            try:
                self._provider_ram_before = self.provider_process.memory_info().rss // (1024 * 1024)
                self._provider_peak = self._provider_ram_before
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                self.provider_process = None
                self._provider_ram_before = 0
        
        # System RAM
        try:
            sys_mem = psutil.virtual_memory()
            self._system_ram_before = sys_mem.used // (1024 * 1024)
            self._system_peak = self._system_ram_before
        except Exception:
            self._system_ram_before = 0
        
        # VRAM
        vram = self._get_vram_mb()
        self._baseline_vram = vram
        self._peak_vram = vram or 0
        
        return {
            "ram_before_mb": self._client_ram_before,
            "vram_before_mb": self._baseline_vram,
            "provider_ram_before_mb": self._provider_ram_before if self.provider_process else None,
            "system_ram_before_mb": self._system_ram_before,
        }
    
    def sample(self) -> None:
        """Sample current resource usage and update peaks."""
        # Client
        try:
            ram = self.client_process.memory_info().rss // (1024 * 1024)
            self._client_peak = max(self._client_peak, ram)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        
        # Provider
        if self.provider_process:
            try:
                ram = self.provider_process.memory_info().rss // (1024 * 1024)
                self._provider_peak = max(self._provider_peak, ram)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                self.provider_process = None
        
        # System
        try:
            sys_mem = psutil.virtual_memory()
            sys_used = sys_mem.used // (1024 * 1024)
            self._system_peak = max(self._system_peak, sys_used)
        except Exception:
            pass
        
        # VRAM
        vram = self._get_vram_mb()
        if vram:
            self._peak_vram = max(self._peak_vram, vram)
    
    def stop(self) -> dict[str, int | None]:
        """Record final measurements."""
        # Client
        try:
            client_ram_after = self.client_process.memory_info().rss // (1024 * 1024)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            client_ram_after = 0
        
        # Provider
        provider_ram_after = 0
        if self.provider_process:
            try:
                provider_ram_after = self.provider_process.memory_info().rss // (1024 * 1024)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        # System
        try:
            sys_mem = psutil.virtual_memory()
            system_ram_after = sys_mem.used // (1024 * 1024)
        except Exception:
            system_ram_after = 0
        
        # VRAM
        vram_after = self._get_vram_mb()
        
        # Calculate attributed RAM (client + provider if found, otherwise estimated)
        if self.provider_process:
            total_attributed = self._client_peak + self._provider_peak
            attribution = "MEASURED"
        else:
            # Estimate: if system peak is much higher than client peak, assume provider used the difference
            total_attributed = self._client_peak
            if self._system_peak > self._client_peak * 2:
                total_attributed = self._system_peak
            attribution = "ESTIMATED"
        
        return {
            "ram_after_mb": client_ram_after,
            "ram_peak_mb": self._client_peak,
            "vram_after_mb": vram_after,
            "vram_peak_mb": self._peak_vram,
            "provider_ram_after_mb": provider_ram_after if self.provider_process else None,
            "provider_ram_peak_mb": self._provider_peak if self.provider_process else None,
            "system_ram_after_mb": system_ram_after,
            "system_ram_peak_mb": self._system_peak,
            "total_attributed_ram_mb": total_attributed,
            "ram_attribution_method": attribution,
        }
    
    def _get_vram_mb(self) -> int | None:
        """Attempt to get VRAM usage. Returns None if unavailable."""
        try:
            import subprocess
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")
                if lines:
                    return int(lines[0].strip())
        except Exception:
            pass
        return None


class BenchmarkRunner:
    """Runs benchmark tests against a provider adapter."""
    
    def __init__(
        self,
        provider,
        device_id: str,
        profile: BenchmarkProfile | None = None,
        store=None,
    ):
        self.provider = provider
        self.device_id = device_id
        self.profile = profile or BenchmarkProfile()
        self.store = store
        provider_id = getattr(provider, 'provider_id', '')
        self.resource_monitor = ResourceMonitor(provider_id)
    
    def run_benchmark(
        self,
        model_id: str,
        test: BenchmarkTest,
        cold_or_warm: str = STATE_WARM,
    ) -> BenchmarkObservation:
        """Run a single benchmark test."""
        obs = BenchmarkObservation(
            benchmark_id=f"bench-{uuid.uuid4().hex[:12]}",
            provider_id=self.provider.provider_id,
            model_id=model_id,
            device_id=self.device_id,
            test_type=test.test_type,
            test_name=test.name,
            cold_or_warm=cold_or_warm,
            tool_call_requested=test.expect_tool_call,
            structured_output_requested=test.expect_structured_output,
        )
        
        # Prepare messages
        messages = []
        if test.system_prompt:
            messages.append({"role": "system", "content": test.system_prompt})
        messages.append({"role": "user", "content": test.prompt})
        
        # Start resource monitoring
        resource_start = self.resource_monitor.start()
        obs.ram_before_mb = resource_start.get("ram_before_mb")
        obs.vram_before_mb = resource_start.get("vram_before_mb")
        obs.provider_ram_before_mb = resource_start.get("provider_ram_before_mb")
        obs.system_ram_before_mb = resource_start.get("system_ram_before_mb")
        
        start_time = time.perf_counter()
        
        try:
            # Execute the appropriate method
            if test.expect_tool_call:
                result = self.provider.tool_call(
                    model_id=model_id,
                    messages=messages,
                    tools=test.tools or [],
                    temperature=test.temperature,
                    max_tokens=test.max_tokens,
                )
            else:
                result = self.provider.generate(
                    model_id=model_id,
                    messages=messages,
                    temperature=test.temperature,
                    max_tokens=test.max_tokens,
                )
            
            wall_duration_ms = int((time.perf_counter() - start_time) * 1000)
            
            # Process result
            self._process_result(obs, result, wall_duration_ms)
            obs.task_success = result.get("ok", False)
            
            if not result.get("ok"):
                obs.error = result.get("error", "unknown error")
                obs.quality_rating = "failed"
            else:
                obs.quality_rating = self._assess_quality(obs, test)
            
        except Exception as e:
            wall_duration_ms = int((time.perf_counter() - start_time) * 1000)
            obs.error = str(e)[:500]
            obs.task_success = False
            obs.quality_rating = "failed"
            obs.limitations.append(f"Exception: {type(e).__name__}")
        
        # Stop resource monitoring
        resource_end = self.resource_monitor.stop()
        obs.ram_after_mb = resource_end.get("ram_after_mb")
        obs.ram_peak_mb = resource_end.get("ram_peak_mb")
        obs.vram_after_mb = resource_end.get("vram_after_mb")
        obs.vram_peak_mb = resource_end.get("vram_peak_mb")
        obs.provider_ram_after_mb = resource_end.get("provider_ram_after_mb")
        obs.provider_ram_peak_mb = resource_end.get("provider_ram_peak_mb")
        obs.system_ram_after_mb = resource_end.get("system_ram_after_mb")
        obs.system_ram_peak_mb = resource_end.get("system_ram_peak_mb")
        obs.total_attributed_ram_mb = resource_end.get("total_attributed_ram_mb")
        obs.ram_attribution_method = resource_end.get("ram_attribution_method", "")
        
        # Store if store provided
        if self.store:
            # Support both BenchmarkStore.append and BenchmarkHistory.record
            if hasattr(self.store, 'record'):
                self.store.record(obs)
            elif hasattr(self.store, 'append'):
                self.store.append(obs)
        
        return obs
    
    def _process_result(
        self, 
        obs: BenchmarkObservation, 
        result: dict[str, Any],
        wall_duration_ms: int,
    ) -> None:
        """Extract metrics from provider result."""
        # Ollama-specific metadata
        if "metadata" in result:
            meta = result["metadata"]
            obs.load_duration_ms = meta.get("load_duration")
            if obs.load_duration_ms:
                obs.load_duration_ms = obs.load_duration_ms // 1_000_000  # ns to ms
            obs.prompt_eval_count = meta.get("prompt_eval_count")
            obs.prompt_eval_duration_ms = meta.get("prompt_eval_duration")
            if obs.prompt_eval_duration_ms:
                obs.prompt_eval_duration_ms = obs.prompt_eval_duration_ms // 1_000_000
            obs.eval_count = meta.get("eval_count")
            obs.eval_duration_ms = meta.get("eval_duration")
            if obs.eval_duration_ms:
                obs.eval_duration_ms = obs.eval_duration_ms // 1_000_000
            obs.total_duration_ms = meta.get("total_duration")
            if obs.total_duration_ms:
                obs.total_duration_ms = obs.total_duration_ms // 1_000_000
            
            # Fallback: if eval_duration missing, estimate from total - load - prompt_eval
            if (obs.eval_duration_ms is None or obs.eval_duration_ms == 0) and obs.total_duration_ms:
                load = obs.load_duration_ms or 0
                prompt = obs.prompt_eval_duration_ms or 0
                estimated = obs.total_duration_ms - load - prompt
                if estimated > 0:
                    obs.eval_duration_ms = estimated
            
            # Derived metrics
            if obs.eval_count and obs.eval_duration_ms and obs.eval_duration_ms > 0:
                obs.tokens_per_second = (obs.eval_count * 1000.0) / obs.eval_duration_ms
                obs.generation_duration_ms = obs.eval_duration_ms
            
            if obs.prompt_eval_count and obs.prompt_eval_duration_ms:
                obs.input_tokens = obs.prompt_eval_count
            
            if obs.eval_count:
                obs.output_tokens = obs.eval_count
            
            # Time to first token approximation
            if obs.load_duration_ms and obs.prompt_eval_duration_ms:
                obs.time_to_first_token_ms = obs.load_duration_ms + obs.prompt_eval_duration_ms
        
        # Tool call validation
        if obs.tool_call_requested:
            tool_valid, tool_evidence = self._validate_tool_call(result)
            obs.tool_call_valid = tool_valid
            obs.tool_call_evidence = tool_evidence
            if not obs.tool_call_valid:
                obs.tool_call_malformed = 1
        
        # Structured output validation
        if obs.structured_output_requested:
            obs.structured_output_valid = self._validate_structured_output(result)
        
        obs.total_duration_ms = wall_duration_ms
    
    def _validate_tool_call(self, result: dict[str, Any]) -> tuple[bool | None, str]:
        """Validate if tool call was well-formed. Returns (valid, evidence_type)."""
        # Check for tool_calls in response (native tool calling)
        if "tool_calls" in result:
            tool_calls = result["tool_calls"]
            if isinstance(tool_calls, list) and tool_calls:
                # Check each tool call has required fields
                for tc in tool_calls:
                    if not isinstance(tc, dict):
                        return False, TOOL_CONTENT_INTENT
                    if "name" not in tc and "function" not in tc:
                        return False, TOOL_CONTENT_INTENT
                return True, TOOL_NATIVE
        
        # Also check content for tool call patterns (some providers embed in content)
        content = result.get("content", "")
        if isinstance(content, str):
            # Pattern 1: explicit tool_call keyword
            if "tool_call" in content.lower():
                return True, TOOL_CONTENT_INTENT
            # Pattern 2: JSON with name/arguments structure (common for Ollama)
            import re
            if re.search(r'["\']name["\']\s*:\s*["\'][^"\']+["\']', content) and \
               re.search(r'["\']arguments["\']\s*:\s*\{', content):
                return True, TOOL_BRIDGE_STRUCTURED
            # Pattern 3: function calling format
            if "function" in content.lower() and "arguments" in content.lower():
                return True, TOOL_STRUCTURED_JSON
        
        return None, ""  # Unknown
    
    def _validate_structured_output(self, result: dict[str, Any]) -> bool | None:
        """Validate if response is valid JSON matching schema."""
        content = result.get("content", "")
        if not isinstance(content, str):
            return None
        
        # Try to extract JSON from markdown code blocks
        json_str = self._extract_json_from_markdown(content)
        if json_str is None:
            json_str = content
        
        try:
            data = json.loads(json_str)
            # Basic validation - check it's a dict
            return isinstance(data, dict)
        except json.JSONDecodeError:
            return False
    
    def _extract_json_from_markdown(self, content: str) -> str | None:
        """Extract JSON from markdown code blocks."""
        import re
        # Look for ```json ... ``` or ``` ... ``` blocks
        pattern = r'```(?:json)?\s*(\{.*?\})\s*```'
        matches = re.findall(pattern, content, re.DOTALL)
        if matches:
            return matches[0].strip()
        # Also try to find JSON object at start of content
        content = content.strip()
        if content.startswith('{') and content.endswith('}'):
            return content
        return None
    
    def _assess_quality(self, obs: BenchmarkObservation, test: BenchmarkTest) -> str:
        """Assess quality of the response."""
        if obs.error:
            return "failed"
        
        if obs.tool_call_requested:
            if obs.tool_call_valid is True:
                return "excellent"
            elif obs.tool_call_valid is False:
                return "poor"
        
        if obs.structured_output_requested:
            if obs.structured_output_valid is True:
                return "excellent"
            elif obs.structured_output_valid is False:
                return "poor"
        
        # For simple generation, check if response is reasonable
        if obs.output_tokens and obs.output_tokens > 0:
            return "good"
        
        return "acceptable"
    
    def run_model_benchmarks(
        self,
        model_id: str,
        tests: list[BenchmarkTest] | None = None,
        include_cold: bool = True,
    ) -> list[BenchmarkObservation]:
        """Run all benchmark tests for a model."""
        tests = tests or self._get_selected_tests()
        observations = []
        
        for test in tests:
            # Cold run (first run after potential model unload)
            if include_cold and not observations:
                obs = self.run_benchmark(model_id, test, STATE_COLD)
                observations.append(obs)
                # Brief pause between cold and warm
                time.sleep(2)
            
            # Warm runs
            for run_idx in range(self.profile.measurement_runs):
                warm_state = STATE_WARM if run_idx > 0 else (STATE_COLD if not include_cold else STATE_WARM)
                obs = self.run_benchmark(model_id, test, warm_state)
                observations.append(obs)
                
                if run_idx < self.profile.measurement_runs - 1:
                    time.sleep(1)  # Brief pause between runs
        
        return observations
    
    def _get_selected_tests(self) -> list[BenchmarkTest]:
        """Get tests based on profile configuration."""
        all_tests = {t.name: t for t in DEFAULT_BENCHMARK_TESTS}
        selected = []
        
        for test_name in self.profile.include_tests:
            if test_name in all_tests:
                selected.append(all_tests[test_name])
        
        return selected


def create_ollama_provider(endpoint: str = "http://127.0.0.1:11434"):
    """Factory to create Ollama provider for benchmarking."""
    from models.providers.ollama_provider import OllamaProvider
    return OllamaProvider(endpoint=endpoint)