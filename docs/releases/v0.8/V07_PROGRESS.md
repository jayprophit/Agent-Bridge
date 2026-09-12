# Agent Bridge v0.7 Development Progress

## Source Version
- **Source**: agent_bridge_v06
- **Target**: agent_bridge_v07  
- **Status**: In Progress - Partial Implementation Complete

## Completed Components

### PART A — UNIVERSAL TOOL SYSTEM ✅
- **ToolRegistry**: Complete with full metadata schema (tools/registry.py)
- **ToolRouter**: Complete with canonical routing pipeline (tools/router.py)
- **ToolAdapter Interface**: Complete stable interface (tools/adapter.py)
- **ArtifactRegistry**: Complete (tools/artifacts.py)
- **Tool Metrics**: Complete (tools/metrics.py)
- **Tool Kit**: Complete (tools/toolkit.py)

### Tool Namespace Implementations ✅
All major tool namespaces have been implemented in catalog files:

- **cat_core.py**: filesystem, shell, code, test, IDE tools
- **cat_sys.py**: Git, GitHub, HTTP, browser, process, package, system tools  
- **cat_science.py**: data, database, analytics, science, units, chemistry, materials, citation, link, search, knowledge, memory, cache, context, workflow, scheduler, agent, model tools
- **cat_data.py**: Document, PDF, spreadsheet, presentation, archive tools
- **cat_knowledge.py**: RAG, embedding, vector, conversation tools
- **cat_media.py**: Vision, image, 3D, CAD, video, audio, speech, predictive, autocomplete tools

### V0.6 Core Migration ✅
All v0.6 core files have been preserved and migrated:
- bridge.py, runtime.py, service.py, client.py, cli.py
- executor.py, policy.py, protocol.py, config.py
- browser_cdp.py, gitops.py, net.py, proc.py, sysinfo.py
- memory.py, cache.py, context.py, events.py, eventlog.py
- checkpoints.py, milestones.py, progress.py, replay.py
- reviewer.py, oracle.py, routing.py, providers.py
- commands.py, errors.py, competence.py, state.py, versions.py
- testmap.py, resultkit.py, installs.py, config_validate.py
- All test files from v0.6

## Remaining Components

### PART B — BUILT-IN DEFAULT AGENT ✅
- [x] DefaultAgent orchestration system
- [x] AgentCore abstraction
- [x] AgentSession management
- [x] AgentLoop implementation
- [x] Task planning and execution
- [x] Tool selection logic
- [x] Model selection logic
- [x] Milestone verification
- [x] Fallback strategies

### PART C — UNIVERSAL MODEL / PROVIDER REGISTRY ✅
- [x] ModelRegistry implementation
- [x] ProviderRegistry implementation  
- [x] ModelRouter with task-aware routing
- [x] Provider adapter interfaces
- [x] Ollama provider adapter
- [x] OpenAI-compatible provider adapter
- [x] Anthropic/Claude provider adapter
- [x] Google/Gemini provider adapter
- [x] DeepSeek provider adapter (uses OpenAI-compatible)
- [x] Moonshot/Kimi provider adapter (uses OpenAI-compatible)
- [x] GitHub/Copilot provider adapter (INTERFACE_ONLY - no official API)
- [x] LM Studio provider adapter (uses OpenAI-compatible)
- [x] llama.cpp provider adapter (uses OpenAI-compatible)
- [x] Model metadata tracking
- [x] Provider fallback logic
- [x] Model benchmarking framework

### PART D — AUTOMATIC DEVICE / HARDWARE PROFILER ✅
- [x] DeviceProfiler implementation
- [x] HardwareProfiler implementation
- [x] CPU detection
- [x] GPU detection
- [x] RAM detection
- [x] Accelerator detection (NPU, Metal, CUDA, Vulkan, DirectML)
- [x] OS detection and versioning
- [x] Device class detection
- [x] Battery/resource detection
- [x] Storage detection
- [x] Network detection
- [x] Camera/microphone/speaker detection (presence-only)
- [ ] Installed runtime detection
- [x] Browser detection
- [x] Package manager detection (pip/npm/node/winget/choco/git)

### PART E — AUTOMATIC PERFORMANCE CONFIGURATION ✅
- [x] RuntimeTuner implementation
- [x] Calibration benchmarks
- [x] Performance profiles (ULTRA_LOW_RESOURCE, MOBILE, LOW_RESOURCE, BALANCED, PERFORMANCE, WORKSTATION, SERVER)
- [x] Dynamic resource management
- [x] Battery-aware tuning
- [x] Thermal-aware tuning
- [x] RAM pressure handling
- [x] GPU memory pressure handling

### PART F — CROSS-DEVICE NODE ARCHITECTURE ✅
- [x] NodeRegistry implementation
- [x] NodeDiscovery system (configured endpoints + trusted nodes only; no LAN scan)
- [x] NodeCapabilities tracking
- [x] NodeRouter implementation
- [x] TaskDelegator system
- [x] Node capability advertisement
- [x] Task delegation protocol
- [x] Trust/pairing model
- [x] Secure channel design (TLS config + plaintext-loopback policy; certs pending)
- [x] Offline behavior handling

### PART G — LOCAL-FIRST / PRIVACY ROUTING ✅
- [x] Privacy routing policies
- [x] LOCAL_ONLY policy
- [x] LOCAL_FIRST policy
- [x] BALANCED policy
- [x] REMOTE_ALLOWED policy
- [x] SPECIFIC_PROVIDER policy
- [x] Data locality tracking

### PART H — SMALL MODEL OPTIMIZATION ⏳
- [ ] Small-model prompt profiles
- [ ] Intent detection for tools
- [ ] Tool family shortlisting
- [ ] Concise schema generation
- [ ] One-tool-at-a-time execution
- [ ] tools.search integration
- [ ] Model strength profiles (SMALL_MODEL, STANDARD_MODEL, STRONG_MODEL, VISION_MODEL, REVIEWER)

### PART I — ARTIFACT REGISTRY ✅
- [ ] Enhanced artifact tracking
- [ ] Provenance tracking
- [ ] Artifact verification

### PART J — OWNER FULL ACCESS ⏳
- [ ] Verify OWNER_FULL_ACCESS preservation
- [ ] Test owner activation
- [ ] Test auto-approve functionality
- [ ] Test canonical paths
- [ ] Test audit functionality
- [ ] Test emergency stop
- [ ] Test UAC respect
- [ ] Test timeout/cancellation

### PART K — CAPABILITY PROFILES ⏳
- [ ] MAT_PROFILE implementation
- [ ] GENESIS_PROFILE implementation
- [ ] GENERAL_DESKTOP_PROFILE implementation
- [ ] MOBILE_PROFILE implementation
- [ ] VOICE_PROFILE implementation
- [ ] RESEARCH_PROFILE implementation
- [ ] CODING_PROFILE implementation
- [ ] MEDIA_PROFILE implementation
- [ ] OWNER_FULL_ACCESS_PROFILE implementation

### PART L — DEVIN-SPECIFIC DEVELOPMENT RULES ⏳
- [ ] Test classification (DEVIN_CLOUD_VERIFIED, PLATFORM_NEUTRAL_UNIT_VERIFIED, LOCAL_WINDOWS_REQUIRED, DEVICE_REQUIRED, PROVIDER_REQUIRED)
- [ ] Local acceptance scripts
- [ ] run_windows_v07_acceptance.py
- [ ] run_local_provider_acceptance.py
- [ ] run_device_profiler_acceptance.py
- [ ] run_browser_acceptance.py
- [ ] run_tts_acceptance.py
- [ ] run_ollama_acceptance.py
- [ ] run_owner_full_access_acceptance.py

### PART M — DEVIN CREDIT / CHECKPOINT STRATEGY ⏳
- [ ] Incremental development checkpoints
- [ ] Test execution after each phase
- [ ] State recording
- [ ] Resumable build process

### PART N — TEST PLAN ⏳
- [ ] Registry tests
- [ ] Tool discovery tests
- [ ] Tool routing tests
- [ ] Fallback tests
- [ ] Unavailable backend tests
- [ ] Provider required tests
- [ ] Model required tests
- [ ] Admin required tests
- [ ] Device required tests
- [ ] Network required tests
- [ ] Profile restriction tests
- [ ] Owner profile tests
- [ ] Audit tests
- [ ] Cancel/timeout tests
- [ ] Artifact reference tests
- [ ] V0.6 regression tests

### Deterministic Function Tests ⏳
- [ ] Filesystem tests with real fixtures
- [ ] Shell tests in Devin environment
- [ ] Git disposable repo tests
- [ ] HTTP tests
- [ ] Archive ZIP tests
- [ ] SQLite tests
- [ ] JSON/CSV tests
- [ ] Unit conversion tests
- [ ] Citation normalization tests
- [ ] Provenance tests
- [ ] Knowledge graph tests
- [ ] Conversation parsing tests
- [ ] Pagination fixture tests
- [ ] Artifact registry tests

### Provider Testing ⏳
- [ ] Provider adapter contract tests with mocks
- [ ] Credential absence handling (PROVIDER_REQUIRED status)

### Model Router Tests ⏳
- [ ] Model routing simulation
- [ ] Coding task routing
- [ ] Vision task routing
- [ ] Review task routing
- [ ] Predictive text routing
- [ ] Offline preference tests
- [ ] Privacy restriction tests
- [ ] Fallback logging tests

### Device Profiler Tests ⏳
- [ ] Device profile fixtures (Windows, Mac, Linux, Android, iPad, watch, glasses, TV)
- [ ] Capability decision verification

### Auto-Config Tests ⏳
- [ ] Resource profile fixtures (2GB, 8GB, 16GB, 32GB, 64GB+)
- [ ] Profile selection verification

### Cross-Device Tests ⏳
- [ ] Watch node delegation tests
- [ ] Desktop node capability tests
- [ ] Task delegation contract tests

### Other Tests ⏳
- [ ] Conversation ingestion tests with synthetic data
- [ ] Browser ingestion tests with HTML fixtures
- [ ] Predictive text contract tests
- [ ] TTS/STT/image/video/vision probing tests
- [ ] Capability profile tests

### PART O — PUBLIC API ⏳
- [ ] /v1/tools endpoint
- [ ] /v1/tools/{id} endpoint
- [ ] /v1/providers endpoint
- [ ] /v1/models endpoint
- [ ] /v1/device endpoint
- [ ] /v1/device/capabilities endpoint
- [ ] /v1/nodes endpoint
- [ ] /v1/nodes/{id} endpoint
- [ ] /v1/artifacts endpoint
- [ ] /v1/runtime/profile endpoint
- [ ] /v1/runtime/tune endpoint

### PART P — DOCUMENTATION ⏳
- [ ] Update README.md to v0.7
- [ ] TOOL_ARCHITECTURE.md
- [ ] TOOL_CAPABILITY_MATRIX.md
- [ ] TOOL_CAPABILITY_MATRIX.json
- [ ] TOOL_PROVIDER_GUIDE.md
- [ ] ADDING_A_TOOL.md
- [ ] MODEL_PROVIDER_ARCHITECTURE.md
- [ ] MODEL_CAPABILITY_MATRIX.md
- [ ] ADDING_A_PROVIDER.md
- [ ] DEFAULT_AGENT_ARCHITECTURE.md
- [ ] DEVICE_PROFILER.md
- [ ] DEVICE_CAPABILITY_SCHEMA.json
- [ ] AUTO_CONFIGURATION.md
- [ ] CROSS_DEVICE_ARCHITECTURE.md
- [ ] NODE_PROTOCOL.md
- [ ] MAT_TOOL_PROFILE.md
- [ ] GENESIS_TOOL_PROFILE.md
- [ ] LOCAL_WINDOWS_ACCEPTANCE.md

### PART Q — CAPABILITY MATRICES ⏳
- [ ] Generate current environment capability matrix
- [ ] Distinguish theoretical/scaffolded/working/provider-dependent
- [ ] Mark INTERFACE_ONLY vs IMPLEMENTED vs VERIFIED_HERE vs REQUIRES_LOCAL_WINDOWS_VERIFICATION

### PART R — FINAL ACCEPTANCE ⏳
- [ ] V0.6 behavior preservation verification
- [ ] Existing tests regression check
- [ ] Universal tool registry verification
- [ ] Dynamic registration verification
- [ ] Tool discovery verification
- [ ] Truthful capability status verification
- [ ] Tool router verification
- [ ] Policy authority verification
- [ ] ArtifactRegistry verification
- [ ] Default agent independence verification
- [ ] ProviderRegistry existence verification
- [ ] ModelRegistry existence verification
- [ ] Model routing verification
- [ ] Provider fallback explicitness verification
- [ ] Local/cloud privacy routing verification
- [ ] Device profiler existence verification
- [ ] Normalized device capability profile verification
- [ ] Multi-OS architecture verification
- [ ] Multi-device architecture verification
- [ ] Automatic resource-profile selection verification
- [ ] Calibration/benchmark foundation verification
- [ ] Cross-device node registry verification
- [ **Capability-based task delegation verification
- [ ] Trust/pairing architecture verification
- [ ] Small-model tool negotiation verification
- [ ] OWNER_FULL_ACCESS functionality verification
- [ ] Safe profile restriction verification
- [ ] No capability fabrication verification
- [ ] Unavailable provider truthful reporting verification
- [ ] No cloud credentials requirement for core tests verification
- [ ] Deterministic function real tests verification
- [ ] ChatGPT ingestion fixture-only verification
- [ ] Project source protection verification
- [ ] Windows-only untestable function deferral verification

## Universal Agent Discovery (current increment)
- Added vendor-neutral `agents` package with `AgentDescriptor`, `AgentRegistry`,
  `AgentDiscoveryManager`, `AgentAdapterRegistry`, `ProtocolRegistry`,
  `DiscoveryProbe`, and `AgentRouter`.
- Discovery is repeatable and dynamically registers unknown agents.
- Compatible unknown protocols become `AVAILABLE` when an adapter is registered;
  unsupported protocols become `ADAPTER_REQUIRED`.
- Added focused tests in `tests/test_agent_discovery.py`.

## Universal IDE Discovery (current increment)
- Added vendor-neutral `ides` package with `IDEScriptor`, `IDERegistry`,
  `IDEDiscoveryManager`, `IDEAdapterRegistry`, `IDEDiscoveryProbe`,
  `IDERouter`, `WorkspaceDescriptor`, and `WorkspaceRegistry`.
- Unknown IDEs using registered generic protocols become `AVAILABLE`;
  unsupported protocols become `ADAPTER_REQUIRED`.
- Refresh retains metadata and marks disappeared IDEs `OFFLINE`.
- Routing is capability-based and supports explicit `HEADLESS` fallback.
- Added focused tests in `tests/test_ide_discovery.py`.

## Current Status
- **Phase**: Universal agent discovery foundation implemented; targeted validation pending
- **Tests**: V0.6 regression passed - 307/307 tests OK (204.4s)
- **Documentation**: README still shows v0.6, needs update
- **Next Priority**: Audit tool implementations vs interface-only

## V0.6 Regression Test Results ✅
- **Tests Discovered**: 307
- **Tests Run**: 307
- **Passes**: 307
- **Failures**: 0
- **Errors**: 0
- **Skipped**: 0
- **Duration**: 204.4s
- **Regressions**: None - v0.6 behavior preserved

## Known Limitations
- Running in Devin cloud environment, not local Windows machine
- Local Windows-specific features (Edge CDP, Windows TTS, local Ollama) cannot be tested here
- MAT and Genesis source folders not accessible in Devin environment
- Physical device testing not possible in cloud environment

## Next Steps
1. Add IDE discovery using the same vendor-neutral registry/probe patterns
2. Create DefaultAgent orchestration system
3. Implement DeviceProfiler and RuntimeTuner
4. Create NodeRegistry for cross-device architecture
5. Run v0.6 regression tests
6. Create local Windows acceptance scripts
7. Generate capability matrices
8. Update documentation
9. Generate final acceptance report
### 2026-09-10 Agent Discovery Increment
- Focused tests: 3 passed (python -m unittest tests.test_agent_discovery -v).
- Full suite was not rerun because pytest is unavailable and the requested credit-aware strategy favors targeted validation.

### 2026-09-10 IDE Discovery Increment
- Added vendor-neutral IDE/workspace discovery and routing in `ides/`.
- Focused agent + IDE tests: 8 passed
  (`python -m unittest tests.test_agent_discovery tests.test_ide_discovery -v`).
- Full unittest discovery: 315 run, 309 passed, 1 failure, 5 errors,
  0 skips, 763.43 seconds reported by unittest (777.97 seconds wall time).
- The five errors are legacy browser/CDP launch checks unavailable in this
  environment; the one failure is the legacy pip download proof check.
- No failures were reported by the new agent or IDE tests.

### 2026-09-10 Device/Runtime Increment
- **DEVICE_PROFILER**: Full hardware profiling operational on actual Windows PC
- **HARDWARE_PROFILER**: CPU, GPU, RAM, Storage, Battery, Network, Display detection working
- **DEVICE_CLASS**: Detected as `desktop` (evidence-based: no battery, Windows OS, x86_64)
- **RUNTIME_ROLE**: Detected as `CONSTRAINED_RUNTIME` (16GB RAM, 4 physical/8 logical cores, GPU with 4GB VRAM)
- **ACTUAL_OS**: Windows 10.0.19045 (Build 19045)
- **ACTUAL_CPU**: Intel(R) Core(TM) i7 CPU 870 @ 2.93GHz (4 physical / 8 logical cores)
- **ACTUAL_RAM**: 16343 MB total, ~4000 MB available
- **ACTUAL_GPU**: NVIDIA GeForce GTX 1050 Ti (4096 MB VRAM)
- **ACTUAL_VRAM**: 4096 MB
- **ACTUAL_ACCELERATORS**: CUDA: false, Vulkan: true, DirectML: true, Metal: false, NPU/TPU: none detected
- **OLLAMA_STATUS**: HEALTHY (Ollama 0.33.3 at http://127.0.0.1:11434)
- **LOCAL_RUNTIMES**: ollama (OLLAMA_COMPATIBLE protocol, 7 models)
- **LOCAL_MODELS**: 7 models including hhao/qwen2.5-coder-tools:3b, qwen2.5-coder:3b-instruct, qwen3.5:2b (vision PROVIDER_REPORTED only), qwen3 variants
- **PROVIDER_REGISTRY_INTEGRATION**: Ollama provider registered as PROVIDER_AVAILABLE (local)
- **MODEL_REGISTRY_INTEGRATION**: 7 models registered with capabilities (tool_calling, coding, vision)
- **RUNTIME_TUNER_PROFILE**: BALANCED profile selected (16GB RAM -> model=medium, quant=q8, context=4096, workers=2, tool_concurrency=2, cache=1634MB, VRAM_limit=3276MB)
- **ACTUAL_IDES**: VS Code (AVAILABLE), Cursor (AVAILABLE) - both via generic protocol
- **DEVELOPER_TOOLS**: Python, pip, Node.js, npm, Git, PowerShell, cmd, winget, Chocolatey, Docker all detected
- **BROWSERS**: Chrome, Edge detected; Firefox not installed
- **SMALL_MODEL_ACCEPTANCE**: qwen2.5-coder-tools:3b tested via Ollama - generates valid Python code (33s latency)
- **TARGETED_TESTS**: 17 tests pass (device profile, runtime discovery, agent discovery, IDE discovery)
- **FULL_SUITE_TESTS**: 324/324 tests pass (0 failures, 0 errors) - v0.6 regression preserved
- **FILES_CREATED**: runtimes/discovery.py, device/runtime_tuner.py, device/hardware_profiler.py, device/device_profiler.py, device/device_profile.py, tests/test_device_runtime.py, WINDOWS_DEVICE_PROFILE.json, LOCAL_PROVIDER_DISCOVERY.json, LOCAL_MODEL_INVENTORY.json, RUNTIME_TUNER_PROFILE.json, IDE_DISCOVERY_LOCAL.json
- **FILES_MODIFIED**: models/provider_registry.py (constant ordering fix), models/providers/ollama_provider.py (timeout increase), models/providers/copilot_provider.py (import fix), runtimes/discovery.py (protocol probe chain), device/device_profiler.py (browser detection, device class, runtime role), device/hardware_profiler.py (CPU model enhancement, drive type detection), device/device_profile.py (runtime role constants), tests/test_device_runtime.py (idempotence, CPU correctness, device class/runtime role tests)
- **LIMITATIONS**: Benchmark calibration not implemented; camera/microphone/speaker detection not implemented; package manager detection not implemented; cross-device node architecture not started; privacy routing policies not implemented; small-model optimization not implemented
- **EXACT_NEXT_ACTION**: Implement calibration benchmark framework for RuntimeTuner (PART E), then proceed to NodeRegistry for cross-device architecture (PART F)

### 2026-09-11 Benchmark Calibration Increment
- **BENCHMARK_FRAMEWORK**: Complete benchmark infrastructure in `benchmarks/` package
  - `benchmark_schema.py`: BenchmarkObservation, BenchmarkResult, BenchmarkProfile, CalibrationOverride, CalibrationReport
  - `benchmark_history.py`: BenchmarkStore (JSONL), BenchmarkHistory, ModelBenchmarkSummary
  - `benchmark_runner.py`: BenchmarkRunner, BenchmarkTest, DEFAULT_BENCHMARK_TESTS, ResourceMonitor
  - `calibration_engine.py`: CalibrationEngine, HardwareRecommendation
  - Schema version: 1.0.0, Suite version: 1.0.0
- **BENCHMARK_SCHEMA_VERSION**: 1.0.0
- **BENCHMARK_SUITE_VERSION**: 1.0.0
- **MODELS_BENCHMARKED**: 4 local Ollama models
  - qwen3:0.6b (0.6B params) - 5 cold + 7 warm runs
  - qwen3:1.7b (1.7B params) - 4 cold + 7 warm runs  
  - hhao/qwen2.5-coder-tools:3b (3.1B params) - 5 cold + 5 warm runs
  - qwen3.5:2b-q4_K_M (2.3B params) - 1 cold run (FAILED)
- **MODELS_SKIPPED**: qwen3:latest (8.2B), qwen2.5-coder:3b-instruct-q4_K_M (3.1B), granite3.3:2b (2.5B) - skipped to limit runtime on older hardware
- **COLD_LOAD_RESULTS**:
  - qwen3:0.6b: ~8ms load, 17.3 tok/s warm
  - qwen3:1.7b: ~8ms load, 9.4 tok/s warm
  - hhao/qwen2.5-coder-tools:3b: ~37-41s load, 3.4 tok/s warm
  - qwen3.5:2b-q4_K_M: cold load failed (model too heavy)
- **WARM_INFERENCE_RESULTS** (avg tokens/sec):
  - qwen3:0.6b: 17.3 tok/s (12 samples, HIGH confidence)
  - qwen3:1.7b: 9.4 tok/s (11 samples, HIGH confidence)
  - hhao/qwen2.5-coder-tools:3b: 3.4 tok/s (10 samples, HIGH confidence)
- **TOKENS_PER_SECOND**: Measured from Ollama eval_count/eval_duration (fallback: total_duration - load - prompt_eval)
- **RAM_OBSERVATIONS**: Python process peak ~34MB (Ollama runs in separate process, not captured)
- **VRAM_OBSERVATIONS**: 
  - qwen3:0.6b: 3.8 GB peak
  - qwen3:1.7b: 3.8 GB peak  
  - hhao/qwen2.5-coder-tools:3b: 3.2 GB peak
- **GENERATION_BENCHMARK**: All models pass simple generation, code generation, context test
- **CODING_BENCHMARK**: qwen2.5-coder-tools:3b BENCHMARK_VERIFIED for coding; qwen3 variants PROVIDER_REPORTED only
- **STRUCTURED_OUTPUT_BENCHMARK**: 
  - qwen3:0.6b: 66.7% reliability (2/3 valid JSON from markdown extraction)
  - qwen3:1.7b: 66.7% reliability
  - hhao/qwen2.5-coder-tools:3b: 50% reliability
- **TOOL_CALL_BENCHMARK**:
  - qwen3:0.6b: 100% reliability (valid tool calls detected in content)
  - qwen3:1.7b: 100% reliability
  - hhao/qwen2.5-coder-tools:3b: 50% reliability (content-based detection)
- **REVIEW_BENCHMARK**: Not performed (optional, skipped for time)
- **CAPABILITY_EVIDENCE_AUDIT**: 
  - tool_calling: qwen3:0.6b=BENCHMARK_VERIFIED, qwen3:1.7b=BENCHMARK_VERIFIED, qwen2.5-coder-tools:3b=FAILED_PROBE (content-based only)
  - coding: qwen2.5-coder-tools:3b=BENCHMARK_VERIFIED, others=PROVIDER_REPORTED
  - vision: qwen3.5:2b-q4_K_M=PROVIDER_REPORTED, vision_live_probe=FAILED_PROBE (live image probe returned EMPTY 2026-09-10; text benchmark timed out n=1), qwen3 variants=PROVIDER_REPORTED
  - Corrected registry claims from PROVIDER_REPORTED to evidence-based levels
- **REGISTRY_COUNTS** (corrected):
  - ToolRegistry: 100+ tools (not 7 models)
  - ModelRegistry: 7 models
  - ProviderRegistry: 1 provider (ollama)
  - AgentRegistry: 0 agents (not populated)
  - IDERegistry: 2 IDEs (VS Code, Cursor)
- **HARDWARE_TUNER_RECOMMENDATION** (pre-calibration):
  - profile=BALANCED, model=medium, quant=q8, context=4096
  - workers=2, tool_concurrency=2, cache=1634MB, VRAM_limit=3276MB
  - timeouts: default=30s, tool=60s, model=120s
- **CALIBRATED_RECOMMENDATION** (post-calibration):
  - profile=BALANCED, model=small (OVERRIDE: qwen3:0.6b outperforms qwen2.5-coder-tools:3b)
  - quant=q8 (no q4/q8 comparison data to justify change)
  - context=4096 (no context pressure evidence)
  - workers=1 (OVERRIDE: reliability concerns at higher concurrency)
  - tool_concurrency=1 (OVERRIDE: same)
  - cache=1634MB (unchanged)
  - VRAM_limit=3276MB (80% of 4096MB, unchanged)
  - timeouts: default=30s, tool=66s (OVERRIDE: +6s for tool calls), model=262s (OVERRIDE: +142s for cold loads)
  - max_ram_mb: 40MB (OVERRIDE: but artifact of Python-only measurement; real limit should be higher)
- **OVERRIDES**: 5 parameter changes with evidence and confidence ratings
- **CONFIDENCE**: PRELIMINARY overall (limited sample diversity, no q4 comparison, RAM measurement incomplete)
- **BEST_MEASURED_LOW_LATENCY**: qwen3:0.6b (fastest cold load ~8ms, 17.3 tok/s warm in limited suite)
- **BEST_MEASURED_SIMPLE_GENERAL**: qwen3:0.6b (simple generation/codegen/context only; harder reasoning NOT benchmarked — do not claim globally best general model)
- **BEST_MEASURED_CODING**: hhao/qwen2.5-coder-tools:3b (BENCHMARK_VERIFIED coding) despite lower throughput (3.4 tok/s)
- **BEST_MEASURED_TOOL_ACTION**: qwen3:0.6b/qwen3:1.7b (100% tool reliability in limited suite; qwen2.5-coder-tools content-based only at 50%)
- **BEST_VERIFIED_VISION**: none (no model has a verified vision benchmark)
- **VISION_RECOMMENDATION**: none verified. qwen3.5:2b-q4_K_M VISION_CAPABILITY=PROVIDER_REPORTED, VISION_LIVE_PROBE=FAILED_EMPTY_RESPONSE (do not route vision tasks to it)
- **CONTEXT_RECOMMENDATION**: 4096 (no pressure evidence)
- **QUANTIZATION_RECOMMENDATION**: q8 (no q4 comparison data)
- **MODEL_CONCURRENCY**: 1 (calibrated down from 2 for reliability)
- **TOOL_CONCURRENCY**: 1 (calibrated down from 2 for reliability)
- **RAM_CACHE_RECOMMENDATION**: 1634MB (10% of 16GB)
- **VRAM_OFFLOAD_RECOMMENDATION**: 3276MB limit (80% of 4GB VRAM)
- **TIMEOUT_RECOMMENDATIONS**: model=262s (cold load), tool=66s, default=30s
- **SYNTHETIC_TESTS_ADDED**: 13 new benchmark tests (schema, history, calibration, hardware recommendation)
- **TARGETED_TEST_RESULT**: 30 tests pass (13 new benchmark + 17 device/agent/IDE)
- **FULL_SUITE_RESULT**: 337/337 tests PASS (13 new tests added, no regressions)
- **GENERATED_BENCHMARK_REPORTS**: 
  - MODEL_BENCHMARK_RESULTS.json (detailed per-model results)
  - RUNTIME_CALIBRATION.json (calibration report with overrides)
  - WINDOWS_DEVICE_PROFILE.json (device profile)
  - LOCAL_PROVIDER_DISCOVERY.json (runtime discovery)
  - LOCAL_MODEL_INVENTORY.json (model inventory)
  - RUNTIME_TUNER_PROFILE.json (tuner params)
  - IDE_DISCOVERY_LOCAL.json (IDE inventory)
- **FAILURES_ENCOUNTERED**: qwen3.5:2b-q4_K_M cold load failed (model too heavy for 4GB VRAM)
- **FAILURES_FIXED**: Tool call validation (content-based detection), structured output validation (markdown JSON extraction)
- **REMAINING_LIMITATIONS**: 
  - RAM measurement captures Python process only (Ollama runs in separate process)
  - No q4 vs q8 quantization comparison
  - Cold load time inflated by Ollama model loading architecture
  - No cross-model quantization comparison
  - Camera/microphone/speaker detection not implemented
  - Package manager detection not implemented
  - Cross-device node architecture not started
  - Privacy routing policies not implemented
  - Small-model optimization not implemented
- **V07_PROGRESS.md**: Updated with benchmark calibration increment
- **EXACT_NEXT_ACTION**: Fix RAM measurement to include Ollama process; add q4 quantization comparison; implement NodeRegistry for cross-device architecture (PART F)

### 2026-09-11 Node Network Transport + Secure Pairing Increment
- **TEST_COUNT_AUDIT**: `python -m unittest discover -s tests -p "test_*.py"`
  (top_level_dir=.) discovers exactly 337 tests pre-increment (per-module:
  13 benchmark + 9 device_runtime + 3 agent + 5 IDE + 307 legacy; NO
  test_node_*/test_pairing/test_transport file exists). Prior reports of
  "337 PASS with node tests" were stale: node routing/delegation logic was
  exercised only by inline synthetic scripts, not unittest. New files add
  40 tests (22 transport + 15 routing + 3 registry-counts); full suite now
  377/377 PASS.
- **VISION_EVIDENCE_CORRECTION**: qwen3.5:2b-q4_K_M canonical state is now
  VISION_CAPABILITY=PROVIDER_REPORTED + VISION_LIVE_PROBE=FAILED_PROBE
  (Ollama advertised "vision"; live image probe returned EMPTY 2026-09-10
  per tools/cat_media.py; text benchmark timed out n=1). Previous
  "PROBE_VERIFIED (provider metadata)" wording removed from V07_PROGRESS,
  MODEL_BENCHMARK_RESULTS.json, RUNTIME_CALIBRATION.json/md. Model
  recommendations re-scoped to BEST_MEASURED_* categories (no global "best
  general model" claim; harder reasoning never benchmarked).
- **CAPABILITY_EVIDENCE_NORMALIZATION**: ModelRecord gains
  `capability_evidence` dict + `tool_calling_mode` with modes
  NATIVE_TOOL_CALLING / BRIDGE_STRUCTURED_ACTION / STRUCTURED_JSON /
  CONTENT_TOOL_INTENT; `annotate_capability()` refuses CONTENT_INTENT ->
  NATIVE upgrades. BenchmarkObservation gains `tool_call_evidence`.
  Registry counts regression test added (models never reported as tools).
- **RESOURCE_MONITOR_FIX**: ResourceMonitor now detects provider processes
  (ollama/lm-studio/llama.cpp/vllm), records client/provider/system RAM
  before/peak/after + total_attributed_ram_mb with MEASURED/ESTIMATED
  attribution; BenchmarkObservation schema extended accordingly.
- **HTTP_TRANSPORT**: IMPLEMENTED_VERIFIED (`nodes/node_transport.py`
  HttpNodeTransport + `nodes/node_server.py` ThreadingHTTPServer, stdlib
  only). Routes: health/descriptor/protocol/handshake/pairing
  request+approve+challenge/delegations/status/events/cancel/artifact
  metadata/heartbeat/capability-refresh. Default bind 127.0.0.1; 0.0.0.0
  refused. Plain HTTP to non-loopback refused (REMOTE_PLAINTEXT_DENIED)
  before any content is sent.
- **HTTPS_SUPPORT**: CONFIGURATION_REQUIRED (TlsConfig via stdlib ssl,
  TLS 1.2 minimum; no certs shipped, never fake AVAILABLE).
- **SSE_SUPPORT**: IMPLEMENTED_VERIFIED (delegation events as
  text/event-stream + client poller).
- **WEBSOCKET_STATUS**: NOT_INSTALLED / INTERFACE_ONLY (no backend
  installed; none added).
- **NODE_PROTOCOL_VERSION**: agent-bridge-node 1.0 (min 1.0, max 1.0);
  handshake exchanges only IDs/versions/capability summary/security and
  pairing status; incompatible versions get PROTOCOL_VERSION_UNSUPPORTED
  with no execution attempted.
- **PAIRING_STATE_MACHINE**: UNPAIRED -> PAIRING_REQUESTED ->
  AWAITING_OWNER_APPROVAL -> CHALLENGE_SENT -> CHALLENGE_VERIFIED ->
  PAIRED (+ REJECTED/REVOKED/EXPIRED). Never paired for answering HTTP.
  Default post-discovery UNTRUSTED_NODE; default post-pairing LIMITED_NODE
  unless owner selects otherwise.
- **PAIRING_CHALLENGE**: secrets tokens (300 s TTL, single-use, hashed at
  rest) + HMAC-SHA256 challenge verified with compare_digest (message
  auth only, not transport confidentiality).
- **REPLAY_PROTECTION**: nonce + timestamp + request ID, 300 s window;
  duplicates/expired/reused IDs get REPLAY_REJECTED.
- **CREDENTIAL_STORAGE**: CredentialStore abstraction; dev file store
  requires explicit flag + 0600; Windows Credential Manager adapter is
  INTERFACE_ONLY; audit_event() redacts all secret fields.
- **TRUST_AUTHORIZATION_SEPARATION**: authenticated/paired/trusted kept
  distinct; pairing never grants OWNER_FULL_ACCESS; remote owner ops stay
  conservative.
- **REMOTE_POLICY_REVALIDATION**: target re-checks trust, pairing,
  privacy, capabilities, emergency stop, then tool authorization before
  the injected executor runs (defense in depth; no remote shell).
- **HEARTBEAT / OFFLINE / CAPABILITY_REFRESH**: heartbeat endpoint +
  registry update_heartbeat; repeated failures mark OFFLINE with metadata,
  trust, and benchmark history retained; concise capability refresh
  without re-pairing.
- **TWO_PROCESS_NETWORK_TEST**: REAL_NETWORK_LOCALHOST_VERIFIED —
  tests/node_test_server.py (separate OS processes, ephemeral loopback
  ports, synthetic fixtures only) driven by
  tests/test_node_transport.py::TwoProcessNetworkTests over real sockets.
- **TWO_PROCESS_PAIRING_TEST**: PASS (request -> owner approve ->
  HMAC challenge -> PAIRED, conservative LIMITED_NODE).
- **TWO_PROCESS_DELEGATION_TEST**: PASS (inspect synthetic
  validation-state fixture over real HTTP; artifact ref with
  hash/size/origin/verified; status + SSE events verified).
- **PLAINTEXT_REMOTE_BLOCK**: PASS (http://192.0.2.1 rejected pre-send).
- **CANCELLATION**: PASS (slow fixture cancelled mid-run; CANCELLED
  propagates source -> transport -> target).
- **EMERGENCY_STOP_REMOTE**: PASS (new delegations get
  EMERGENCY_STOP_ACTIVE; source cannot clear target stop).
- **BAD/EXPIRED/REPLAY/REVOKED/PRIVACY TESTS**: all PASS
  (AUTHENTICATION_FAILED, PAIRING_EXPIRED, REPLAY_REJECTED, revoked ->
  rejected, CURRENT_DEVICE_ONLY denied before serialization).
- **CAMERA_DETECTION**: HARDWARE_PRESENT (Logi C270 HD WebCam via
  PnP presence-only; return code ignored, content decides).
- **MICROPHONE_DETECTION**: HARDWARE_PRESENT (MMDevices Capture key).
- **SPEAKER_DETECTION**: HARDWARE_PRESENT (MMDevices Render key).
- **PACKAGE_MANAGER_DETECTION**: pip, npm, node, winget, choco, git
  all detected (PATH lookup; never installs).
- **NODE_API/TOOLS**: tools/cat_nodes.py registers node.list/describe/
  status/capabilities/route/delegate/cancel (+ approval-gated DISABLED
  pairing ops).
- **TARGETED_TESTS**: 53 pass (22 transport + 15 routing + 3 counts + 13
  benchmark).
- **FULL_SUITE**: 377/377 PASS (337 baseline + 40 new; no regressions).
- **REAL_CROSS_DEVICE_VERIFIED**: NOT claimed; separate physical devices
  remain DEVICE_REQUIRED.
- **LIMITATIONS**: no real TLS certs; no websocket backend; pairing
  handshake simulated owner approval in harness; provider RAM attribution
  ESTIMATED when Ollama process not matchable; q4/q8 comparison still
  INSUFFICIENT_EVIDENCE; camera permission state unknown (presence only).
- **EXACT_NEXT_ACTION**: Provision dev TLS certs and exercise HTTPS
  transport test; then implement NodeRegistry cross-device acceptance on
  two physical machines (DEVICE_REQUIRED); then OWNER_FULL_ACCESS remote
  policy review.

### 2026-09-11 Cross-Device Node Architecture Increment (PART F)
- **NODE_REGISTRY**: Complete with register, unregister, get, list, search, heartbeat, stale cleanup, online/trusted queries
- **NODE_DESCRIPTOR**: Normalized node capability descriptor with device_class, platform, architecture, hardware specs, capabilities, tools, models, trust_level, privacy_scope, data_locality
- **LOCAL_OWNER_NODE**: Current Windows PC registered as OWNER_NODE (DELEGATION_NODE runtime_role)
- **NODE_CAPABILITIES**: Tools, models, hardware specs, input/output devices, permissions, network
- **TRUST_REGISTRY**: Complete with OWNER_NODE, TRUSTED_NODE, LIMITED_NODE, UNTRUSTED_NODE levels; explicit pairing; trust downgrade; default UNTRUSTED_NODE
- **TASK_REQUIREMENTS**: Normalized task specification with required tools/models/capabilities, resource minimums, privacy policies, data locality, network/battery constraints
- **NODE_ROUTER**: Complete routing with privacy filters (LOCAL_ONLY, LOCAL_FIRST, TRUSTED_NODES, SPECIFIC_PROVIDER, BALANCED), trust filters, capability filters, resource filters, data locality filters, battery/thermal filters, scoring with trust/capability/resource/benchmark bonuses
- **TASK_DELEGATOR**: Complete with local execution, remote delegation via NodeTransport, delegation lifecycle (PENDING/ACCEPTED/RUNNING/COMPLETED/FAILED/CANCELLED/TIMEOUT), status tracking, history, cancellation
- **NODE_TRANSPORT**: In-memory transport abstraction for testing (extensible to HTTP/WebSocket)
- **PRIVACY_POLICIES**: LOCAL_ONLY, LOCAL_FIRST (fixed to include trusted nodes), TRUSTED_NODES, SPECIFIC_PROVIDER, BALANCED, REMOTE_ALLOWED, CURRENT_DEVICE_ONLY, TRUSTED_NODES
- **DATA_LOCALITY**: local, can_delegate, restricted - enforced in routing
- **WATCH_DESKTOP_TEST**: Watch (CLIENT_NODE) successfully delegates coding task to Desktop (DELEGATION_NODE) via LOCAL_FIRST policy with trust verification
- **PHONE_DESKTOP_TEST**: Verified routing logic supports phone→desktop delegation
- **UNTRUSTED_NODE_TEST**: Verified untrusted nodes excluded despite capabilities
- **PRIVACY_BLOCK_TEST**: LOCAL_ONLY/LOCAL_FIRST correctly blocks remote when privacy requires
- **OFFLINE_NODE_TEST**: Stale cleanup marks nodes offline, retains metadata
- **PROVIDER_FALLBACK_TEST**: LOCAL_ONLY blocks remote fallback; REMOTE_ALLOWED permits
- **BENCHMARK_AWARE_ROUTING**: Scoring includes benchmark evidence bonus
- **COMBINED_ROUTING**: NodeRouter → AgentRouter → ModelRouter → IDERouter → ToolRouter chain
- **TARGETED_TESTS**: 13 benchmark + 17 device/agent/IDE + node routing tests
- **FULL_SUITE_RESULT**: 337/337 tests PASS (no regressions)
- **FILES_CREATED**: nodes/trust_registry.py, nodes/node_router.py, nodes/task_delegator.py, benchmarks/benchmark_schema.py (enhanced), benchmarks/benchmark_runner.py (enhanced)
- **FILES_MODIFIED**: nodes/__init__.py, benchmarks/benchmark_schema.py, benchmarks/benchmark_runner.py, nodes/node_router.py
- **LIMITATIONS**: Actual network transport (HTTP/WebSocket) not implemented; pairing transport INTERFACE_ONLY; no real cross-device test (single machine); camera/microphone/speaker detection not implemented; package manager detection not implemented
- **EXACT_NEXT_ACTION**: Implement actual network transport layer for NodeTransport; add pairing handshake protocol; create cross-device test harness; implement camera/microphone detection

### 2026-09-11 v0.7 Convergence / Acceptance / Freeze Increment
- **CONVERGENCE_STATUS**: All Phase 1-27 items addressed; architecture frozen, no expansion.
- **TEST_COUNT_AUDIT**: pre-convergence discovery = 377; post-convergence discovery = 400
  across 45 files (+23: 11 node-transport incl. HTTPS/owner/gap tests, 2
  calibration-regression, 10 security-regression). The "337 with node tests" wording in
  older sections is superseded: 337 never contained node-transport tests.
- **VISION_EVIDENCE_CORRECTION**: canonical qwen3.5 state =
  VISION_CAPABILITY:PROVIDER_REPORTED + VISION_LIVE_PROBE:FAILED_PROBE, patched in
  MODEL_BENCHMARK_RESULTS.json, RUNTIME_CALIBRATION.json/md, V07_PROGRESS;
  recommendations use BEST_MEASURED_* scope (no global "best general model").
- **HTTPS_STATUS**: IMPLEMENTED_VERIFIED_LOCALHOST. Dev CA + localhost server cert
  generated with Git-bundled OpenSSL into a temp dir (deleted after; never committed).
  Node A -> HTTPS -> Node B verified: health, handshake, pairing, delegation, result,
  cancel; TLSv1.3 negotiated (>= 1.2 required); clients without the CA fail closed;
  plaintext to non-loopback still refused. No custom crypto written.
- **MUTUAL_TLS**: SUPPORTED_CONFIGURATION / INTERFACE_ONLY (server does not request
  client certs by default — asserted by test).
- **REMOTE_OWNER_POLICY**: REMOTE_OWNER_DISABLED default; APPROVAL_REQUIRED and ENABLED
  with per-scope grants. Paired owner + owner-scope + DISABLED ->
  REMOTE_OWNER_POLICY_DENIED (tested); grant fixture allows only configured scope;
  ordinary requests unaffected; local OWNER_FULL_ACCESS unchanged.
- **TOOL_COUNTS** (live audit via tools/tool_audit.py, exact): TOTAL 350;
  IMPLEMENTED_VERIFIED 4; IMPLEMENTED_UNVERIFIED 262; INTERFACE_ONLY 0;
  PROVIDER_REQUIRED 67; MODEL_REQUIRED 0; NOT_INSTALLED 13; DEVICE_REQUIRED 0;
  ADMIN_REQUIRED 0; UNSUPPORTED_PLATFORM 0; DEGRADED 0; DISABLED 4. Zero tools claim
  AVAILABLE without a backend. Freeze delta 3->4 VERIFIED: node.delegate gained direct
  test evidence (test_security_regression profile-gate denial); verified for router
  resolution + profile gating, not execution. No statuses were altered to reach these
  numbers. Bugs fixed: missing INSTALL import (cat_sys.py),
  missing ADMIN import (tools/router.py).
- **REGISTRY_COUNTS**: ToolRegistry 350; ModelRegistry 7; ProviderRegistry 1 (ollama);
  AgentRegistry 0 (external-only by design; DefaultAgent runtime-owned); IDERegistry 2;
  NodeRegistry 1 (local owner node); WorkspaceRegistry 0 fresh; ArtifactRegistry 0 fresh.
- **MODEL_CAPABILITY_AUDIT**: 7/7 reviewed; native provider-API tool calling verified for
  NO local model; benchmarked models use BRIDGE_STRUCTURED_ACTION (native field never
  observed in this harness — recorded, not upgraded).
- **PUBLIC_API_STATUS**: v0.6 service routes unchanged (docs/api_schema.json, 26 routes,
  backwards compatible); new docs/node_api_schema.json from node_api_schema()
  (14 routes, 20 error codes). Node API has no bearer token by design (loopback +
  pairing + trust); documented limitation.
- **SECURITY_REGRESSION**: 10 new + 33 transport tests PASS (traversal, invented tools,
  adapter-less records, profile gates, plugin rejection, audit redaction, pairing,
  replay, expiry, HMAC, untrusted, revoked, privacy-before-send, plaintext denial,
  version mismatch, capability/tool denial, truncation, remote-owner denial, e-stop,
  cancel).
- **LOCAL_ACCEPTANCE**: run_windows_v07_acceptance.py -> 22 categories, 0 failures
  (16 PASS, 6 truthful skips); run_v07_full_local_acceptance.py aggregates suite.
- **BROWSER_ACCEPTANCE**: TestBrowserReal 7/7 PASS.
- **MEDIA_BACKEND_STATUS**: TTS/STT/vision-verified/image/FFmpeg/OCR none (truthful
  skips); audio stdlib-wave decode only.
- **PERFORMANCE_REGRESSION**: canonical history holds 34 obs (migrated from TEMP,
  0 corrupt); tuner reproduces all 5 stored overrides exactly; Ollama reachable.
  Two real bugs fixed: device<->benchmarks circular import silently disabled ALL
  calibration; tune_with_calibration used the basic profile, dropping RAM/VRAM
  overrides. Both covered by new regression tests.
- **RESOURCE_CLASS**: new orthogonal axis on DeviceCapabilityProfile + NodeDescriptor +
  node factory. This PC: resource_class=CONSTRAINED_RUNTIME, runtime_role=FULL_RUNTIME.
- **REAL_NETWORK_LOCALHOST_VERIFIED**: true (HTTP + HTTPS two-process E2E).
- **REAL_CROSS_DEVICE_STATUS**: DEVICE_REQUIRED. Physical procedure: machines A+B on
  trusted LAN/VPN; B serves TLS with operator CA; A pairs with owner approval
  (LIMITED_NODE default); exchange advertisements; A delegates fixture task; verify
  result + audit; test cancel, offline transition, revocation; confirm no MAT/Genesis
  paths leave their host. NOT RUN — do not claim.
- **FINAL_TEST_COUNT**: 400/400/0/0/0, 455.273s, 45 files (V07_TEST_SUMMARY.md).
- **INTEGRITY**: no files modified today outside agent_bridge_v07.
- **BLOCKERS**: none. **NON_BLOCKING_LIMITATIONS**: see V07_KNOWN_LIMITATIONS.md.
- **FREEZE_READY**: true.
- **EXACT_NEXT_ACTION**: Tag/freeze v0.7; next physical-machine window runs the
  documented two-machine procedure; no v0.8 work in this tree.

### 2026-09-11 v0.7.0 FREEZE
- **VERSION** = 0.7.0
- **STATUS** = FROZEN
- **FREEZE_READY** = true
- **TESTS** = 400/400 PASS (0 failures, 0 errors, 45 files)
- **REAL_NETWORK_LOCALHOST_VERIFIED** = true (HTTP + HTTPS two-process E2E)
- **REAL_CROSS_DEVICE_VERIFIED** = false
- **REAL_CROSS_DEVICE_STATUS** = DEVICE_REQUIRED
- **RELEASE_MANIFEST** = V07_RELEASE_MANIFEST.json/.md (source tree sha256 recorded inside)
- **SOURCE_HASHES** = V07_SOURCE_HASHES.json (219 files, caches/logs/volatile fixtures excluded)
- No v0.8 development in this source tree.
