# Aetherius Hybrid AI Cloud — Live Reconciliation Report

**Date:** 2026-10-08
**Scope:** Spec §56–142 + Execution Directive §1–26
**Method:** Live filesystem + runtime inspection of Agent-Bridge, Aetherius-OS, Genesis repositories; Ollama/Groq/OpenCode health probes.

## 1. Existing Canonical Architecture Discovered

### 1.1 Provider / Model Registries — **EXISTS_WORKING**
- `models/provider_adapter.py` (v0.7) — `ProviderAdapter` ABC: `discover`, `authenticate`, `list_models`, `model_info`, `capabilities`, `context_limit`, `generate`, `stream`, `tool_call`, `cancel`, `health`
- `models/provider_registry.py` (v0.7) — `ProviderRegistry` with `ProviderRecord` (provider_id, family, status, auth, local_or_remote, endpoint, capabilities, limitations)
- `models/model_registry.py` (v0.7) — `ModelRegistry` with `ModelRecord` (model_id, provider, capabilities, privacy_classification, capability_evidence, ram/vram, latency, tokens_per_second)
- `models/model_router.py` (v0.8) — `ModelRouter` with task-aware routing, privacy policy enforcement, fallback chains, fitness-based selection
- 10 provider adapters: Ollama, OpenAI, OpenAICompatible, Anthropic, Gemini, DeepSeek, Kimi, LM Studio, LlamaCpp, Copilot

### 1.2 Execution Environment Registry — **EXISTS_WORKING** (local-only)
- `execution_environment.py` — `ExecutionEnvironmentRegistry` discovers Windows native, PowerShell, CMD, Git Bash, WSL distros, Docker, Podman
- `machine_capability.py` — `MachineCapabilityRegistry`: CPU, RAM, GPU, tools, shells, virtualization

### 1.3 Compute Provider Registry — **EXISTS_PARTIAL**
- `compute/providers.py` — `ComputeRegistry` with `ComputeRecord` tracks: local-cpu, ollama, ternary-emu, sim-qpu
- **LIMITATION:** Only local providers. No cloud execution-target model with stable IDs, GPU/VRAM tracking, cost/free_quota, trust boundaries.

### 1.4 Orchestrator / Scheduler — **EXISTS_WORKING**
- `orchestrator.py` — `Orchestrator` with `OrchestratorTask`, `FREE_FIRST_STRICT` cost policy, `select_worker()`, retry/fallback, TaskCenter mirroring
- `task_dag.py` — `DurableTaskGraph` (dependency-ordered), `WorkQueue` (FIFO+lease), `WorkerRegistry`, `RetryPolicy`, `CheckpointManager`, `EvidenceLedger`
- `execution_contract.py` — `ExecutionContract` fail-closed lifecycle (§14 adaptive loop)
- `taskcenter.py` — `TaskCenter` hierarchical task store with progress roll-up, evidence append-only

### 1.5 Worker Runtime — **EXISTS_WORKING**
- `worker_runtime.py` — `SupervisedTask`: real OS process workers with lease/heartbeat/checkpoint/recovery
- `worker_adapters.py` — `OpenCodeAdapter`, `OllamaAdapter`, `BridgeAdapter` with least-privilege isolation
- `providers.py` (v0.3) — `ModelProvider` ABC + `OllamaProvider` (legacy, superseded by models/providers/ollama_provider.py)
- `routing.py` (v0.3) — `RoleRouter` / `SingleModelRouter` (legacy, superseded by model_router.py)

### 1.6 Model Lifecycle — **EXISTS_WORKING**
- `model_lifecycle.py` — `ModelRegistry`, `ModelDiscoveryManager`, `ModelCapabilityProfiler`, `ModelBenchmarkManager`, `ModelPlacementEngine`, `ModelLifecycleManager`, `HotModelPool`, `ModelFitness`, `SizeClass`, `ModelStatus`, `ModelState`

### 1.7 Routing Policy — **EXISTS_WORKING**
- `routing-policy.json` — privacy classification routing: SECRET_LOCAL_ONLY, PRIVATE, FREE_ONLY profiles
- `model_roles.py` — role-based model assignments for local hardware (i7-870, 16GB RAM, GTX 1050 Ti)

### 1.8 Live Runtime State (verified 2026-10-08)
| Component | Status | Evidence |
|-----------|--------|----------|
| Ollama daemon | RUNNING | http://localhost:11434/api/tags returns 17 models |
| Local models | 17 installed | qwen3:0.6b/1.7b/latest, qwen2.5-coder:3b, qwen3.5:2b, granite3.3:2b, granite4:3b, phi4-mini, moondream, nomic-embed-text, deepseek-coder, llama3.2:1b, etc. |
| OpenCode CLI | INSTALLED | v1.18.30 at /Users/jpowe/AppData/Roaming/npm/opencode |
| Docker | AVAILABLE | v29.7.2 |
| WSL | AVAILABLE | v2.7.14.0 |
| Provider model cache | 7 providers | copilot(53), openai-codex(8), openrouter(59), gemini(15), huggingface(136), xai(14), ollama-cloud(25) |

## 2. Duplicate Systems Avoided
- `providers.py` (v0.3, `ModelProvider`) is **SUPERSEDED** by `models/provider_adapter.py` (v0.7, `ProviderAdapter`). No new ABC created.
- `routing.py` (v0.3, `RoleRouter`) is **SUPERSEDED** by `models/model_router.py` (v0.8). No new router created.
- `compute/providers.py` `ComputeRegistry` is **EXTENDED** (not duplicated) for execution-target registry.

## 3. Control-Plane / Data-Plane Map

**CONTROL_PLANE (Aetherius-owned):**
- `ProviderRegistry` (models/provider_registry.py)
- `ModelRegistry` (models/model_registry.py)
- `ComputeRegistry` (compute/providers.py)
- `DurableTaskGraph` + `TaskCenter` (task_dag.py, taskcenter.py)
- `Orchestrator` with `FREE_FIRST_STRICT` (orchestrator.py)
- `RoutingPolicy` (routing-policy.json)

**DATA_PLANE (provider-specific):**
- OllamaProvider, OpenAIProvider, OpenAICompatibleProvider
- OpenCode CLI, Bridge workers

**GAP:** Missing canonical AI Gateway (§86) — applications route through ModelRouter directly rather than through a unified gateway with auth/privacy/budget/cost layers.

## 4. Gap Analysis — Missing P0 Components

| # | Component | Spec Section | Status | Blocker |
|---|-----------|-------------|--------|---------|
| 1 | Execution-target registry | §63, §9 | **MISSING** | No stable-ID registry for cloud execution targets |
| 2 | Canonical inference contract | §87 | **MISSING** | No `AetheriusInferenceRequest`/`Response` schema |
| 3 | AI Gateway | §86 | **MISSING** | No `/aetherius/v1/` gateway |
| 4 | Cost engine | §68, §128 | **MISSING** | No budget tracking (DAILY_MAX, MONTHLY_MAX) |
| 5 | Instance registry | §65 | **MISSING** | No tracking of running model instances |
| 6 | Provider adapter V2 | §88 | **PARTIAL** | Missing normalized error classes, prompt caching, reasoning controls |
| 7 | Credential vault | §70 | **PARTIAL** | credential-state.json tracks status but no vault |
| 8 | Free cloud provider credentials | §61, §83 | **BLOCKED_OWNER** | OpenRouter/GROQ/Gemini/HF keys flagged as exposed; rotation required |

## 5. Current Maturity Level
- **LEVEL 0 — SPECIFIED** ✅ (architecture exists)
- **LEVEL 1 — LOCAL VERIFIED** ✅ (Ollama + 17 models running, local inference proven)
- **LEVEL 2 — CLOUD VERIFIED** ❌ (no verified free cloud provider; credentials need rotation)
- **LEVEL 3–10** ❌ (blocked on cloud provider + gateway + cost engine)

## 6. Smallest Dependency-Ready Gap
Implement (no credential requirements):
1. **Execution-target registry** — extends `compute/providers.py` `ComputeRecord` to full cloud execution-target model
2. **Canonical inference contract** — `AetheriusInferenceRequest`/`Response`/etc. schemas
3. **Cost engine** — `FREE_FIRST_STRICT` enforcement with DAILY_MAX/MONTHLY_MAX

These three unlock: cloud worker registration, AI gateway, cost-aware routing, and failover.

## 7. Owner-Required Actions (surfaced)
- **Credential rotation**: OPENROUTER_API_KEY, GROQ_API_KEY, GEMINI_API_KEY, HF_TOKEN flagged as previously exposed — must be revoked and re-issued before cloud routing. (BLOCKED_OWNER)
